"""Command line: seed, token, inspect, demo, serve."""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

from groundwork.config import get_settings
from groundwork.ingest import LoadError, load_site
from groundwork.schemas.views import ChainView, ForecastView
from groundwork.service import views
from groundwork.service.state import SiteState

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Groundwork command line.")
console = Console(width=118)
DEFAULT_SITE = get_settings().groundwork_fixtures_dir / "lake-mariner"


def _d(d: date | None) -> str:
    return d.strftime("%a %b %-d, %Y") if d else "—"


def _short(d: date | None) -> str:
    return d.strftime("%b %-d") if d else "—"


def _org_for_site(site_key: str) -> uuid.UUID:
    from groundwork.db import models as m
    from groundwork.db.session import owner_session

    with owner_session() as s:
        site = s.execute(select(m.Site).where(m.Site.key == site_key)).scalars().first()
        if site is None:
            raise typer.BadParameter(f"site {site_key!r} is not in the database; run `groundwork seed` first")
        return site.org_id


def _load_db_state(site_key: str) -> SiteState:
    from groundwork.db import repo
    from groundwork.db.session import org_session

    with org_session(_org_for_site(site_key)) as s:
        return repo.load_state(s, site_key)


@app.command()
def seed(
    folder: Path = typer.Argument(DEFAULT_SITE, help="Site folder (site.yaml, schedule.csv, ...)"),
    test: bool = typer.Option(False, help="Seed the test database instead"),
) -> None:
    """Load a site folder into the database (owner role). Replaces the org's previous data."""
    from groundwork.db import repo
    from groundwork.db.session import engine_for, owner_session

    cfg = get_settings()
    bundle = load_site(folder)
    engine = engine_for(cfg.test_database_owner_url if test else cfg.database_owner_url)
    with owner_session(engine=engine) as s:
        org_id = repo.seed_bundle(s, bundle)
    console.print(
        f"[green]Seeded[/] {bundle.site_name} ({len(bundle.items)} items, {len(bundle.links)} links, "
        f"{len(bundle.events)} events) into org [bold]{bundle.org_name}[/] ({org_id})."
    )


@app.command()
def token(
    person: str = typer.Argument(..., help="Person key, e.g. dana"),
    hours: int = typer.Option(0, help="Lifetime in hours (default from settings)"),
) -> None:
    """Mint a dev bearer token for a seeded person. Anyone with the signing secret can do this."""
    from groundwork.api.auth import mint
    from groundwork.db import models as m
    from groundwork.db.session import owner_session

    cfg = get_settings()
    with owner_session() as s:
        rows = list(s.execute(select(m.Person).where(m.Person.key == person)).scalars())
    if not rows:
        raise typer.BadParameter(f"no person {person!r}; seeded people are listed in site.yaml")
    p = rows[0]
    typer.echo(
        mint(p.id, p.org_id, secret=cfg.groundwork_dev_hmac_secret, ttl_hours=hours or cfg.token_ttl_hours)
    )


@app.command()
def inspect(
    folder: Path = typer.Argument(..., help="A site folder: your own export in the documented layout"),
) -> None:
    """Validate a site folder and print its gating item, critical path and forecast. No database needed."""
    try:
        state = SiteState.from_bundle(load_site(folder))
    except LoadError as exc:
        console.print(f"[red]{len(exc.problems)} problem(s) in {folder}[/]")
        for p in exc.problems:
            console.print(f"  • {p}")
        raise typer.Exit(1) from exc
    from groundwork.core import validate_links
    from groundwork.domain import get_profile

    _print_baseline(state, views.chain_view(state), views.forecast_view(state))
    tasks, links, _, codes = views.engine_inputs(state)
    problems = validate_links(get_profile(state.profile), codes, links)
    if problems:
        console.print(
            Panel(
                "\n".join(f"• {p}" for p in problems),
                title="Sequencing rules this schedule breaks",
                border_style="yellow",
            )
        )


@app.command()
def demo(
    site: str = typer.Option("lake-mariner"),
    event: str = typer.Option("event-a"),
    offline: bool = typer.Option(False, help="Read the fixture folder directly; no database"),
    reset: bool = typer.Option(True, help="Reseed the site first so the demo is repeatable"),
) -> None:
    """Slice-1 demo: the paper chain, the gate, the critical path, then play an event as a run."""
    if offline:
        state = SiteState.from_bundle(load_site(get_settings().groundwork_fixtures_dir / site))
        _print_baseline(state, views.chain_view(state), views.forecast_view(state))
        _print_event(
            state,
            event,
            views.chain_view(state, scenario=[event]),
            views.forecast_view(state, scenario=[event]),
        )
        return
    if reset:
        seed(get_settings().groundwork_fixtures_dir / site, test=False)
    state = _load_db_state(site)
    _print_baseline(state, views.chain_view(state), views.forecast_view(state))

    from groundwork.db.session import org_session
    from groundwork.service import runs

    org_id = _org_for_site(site)
    with org_session(org_id) as s:
        dana = state.people[0].key if state.people else None
        person_id = state.ids.get(f"person:{dana}") if dana else None
        run_id = runs.start_run(s, site, event, person_id)
    console.rule(f"[bold]Playing {event} as run {str(run_id)[:8]}")
    runs.execute_run(org_id, run_id)
    with org_session(org_id) as s:
        rv = runs.run_view(s, run_id)
    for step in (rv.summary or {}).get("steps", []):
        console.print(f"  [dim]{step['i']:>2}[/] {step['kind']:<9} {step['text']}")
    after = _load_db_state(site)
    _print_event(after, event, views.chain_view(after), views.forecast_view(after))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Run the API."""
    import uvicorn

    uvicorn.run("groundwork.api.app:app", host=host, port=port, reload=reload)


# --- printing ----------------------------------------------------------------------------------
STATUS_STYLE = {"done": "green", "in_progress": "yellow", "not_started": "white"}


def _print_baseline(state: SiteState, c: ChainView, f: ForecastView) -> None:
    ms = c.milestone
    principal = state.party(state.principal)
    console.print(
        Panel.fit(
            f"[bold]{state.name}[/] · {state.location} · as of {_d(state.as_of)}\n"
            f"Working for [bold]{principal.name}[/] ({', '.join(principal.roles).replace('_', ' ')})",
            title="Groundwork",
            border_style="cyan",
        )
    )
    late = ms.delta_days or 0
    timing = f"{-late} days early" if late < 0 else f"[red]{late} days late[/]" if late > 0 else "on the day"
    console.print(
        f"\n[bold]{ms.headline} {ms.days_remaining} days[/] — forecast {_d(ms.forecast_finish)}; "
        f"target {_d(ms.target_date)} ({timing}); "
        f"{c.min_float} business days of float on the critical path\n"
    )
    titles = {i.key: i for i in c.items}
    if c.gate:
        g = titles[c.gate]
        console.print(
            f"[bold yellow]Gating item[/]  {g.title} · {state.party(g.owner).name} · due {_short(g.planned_finish)}"
        )
    console.print("[bold]Critical path[/]  " + " → ".join(c.critical_path))
    if c.near_critical:
        console.print(
            "[bold]Near-critical[/]  "
            + ", ".join(f"{k} ({titles[k].total_float} bd)" for k in c.near_critical)
        )
    if c.calendar_losses:
        console.print("\n[bold]Hidden in the calendar[/]")
        for x in c.calendar_losses:
            console.print(f"  • {x.sentence}")
    t = Table(
        title=f"The paper chain ({len(c.items)} items, {len(c.links)} links)",
        show_lines=False,
        header_style="bold",
    )
    for col in ("lane", "item", "status", "planned", "forecast", "float", ""):
        t.add_column(col)
    lane_label = {ln.key: ln.label for ln in c.lanes}
    order = {ln.key: n for n, ln in enumerate(c.lanes)}
    for i in sorted(c.items, key=lambda i: (order[i.lane], i.planned_finish)):
        flag = (
            "[bold red]GATE[/]"
            if i.key == c.gate
            else "[red]critical[/]"
            if i.critical
            else "[yellow]near[/]"
            if i.near_critical
            else ""
        )
        t.add_row(
            lane_label[i.lane][:28],
            f"{i.key}",
            f"[{STATUS_STYLE[i.status]}]{i.status.replace('_', ' ')}[/]",
            _short(i.actual_finish or i.planned_finish),
            _short(i.early_finish),
            "" if i.total_float is None else str(i.total_float),
            flag,
        )
    console.print(t)
    ref = next((x.reference for x in f.items if x.key == ms.item), None)
    if ref:
        console.print(f"Reference set for {ms.item} ({ref.item_code}): {ref.headline}")
    gate_ref = next((x.reference for x in f.items if x.key == c.gate), None) if c.gate else None
    if gate_ref:
        console.print(f"Reference set for the gate ({gate_ref.item_code}): {gate_ref.headline}")


def _print_event(state: SiteState, event: str, c: ChainView, f: ForecastView) -> None:
    e = state.event(event)
    ms = f.milestone
    via = f" (forwarding {state.party(e.forwarded_from).name})" if e.forwarded_from else ""
    frm = state.party(e.from_party).name if e.from_party != "public" else "public source"
    console.rule(f"[bold]Event: {e.title}")
    local = e.received_at.astimezone(ZoneInfo(state.timezone))
    console.print(f"From {frm}{via} · {local:%a %b %-d %H:%M %Z}")
    console.print(Panel(e.body or "(no message body)", border_style="dim"))
    console.print(
        f"[bold]{ms.label}[/]: forecast {_d(ms.forecast_finish)} "
        f"(range {_short(ms.forecast_low)} to {_short(ms.forecast_high)}) · "
        f"[red]{ms.delta_days} days late[/] against {_d(ms.target_date)}"
    )
    titles = {i.key: i for i in c.items}
    if c.gate:
        console.print(
            f"[bold yellow]Gate[/] {titles[c.gate].title} · critical path "
            + " → ".join(c.critical_path)
            + f" · float {c.min_float} bd"
        )
    for imp in e.impacts:
        console.print(f"  • {imp.item}: +{imp.low} to {imp.high} days — {imp.leg}")
    console.print(f"[dim]{f.method}[/]")


if __name__ == "__main__":
    app()
