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
def release() -> None:
    """Migrate the database to the latest schema, then load the Lake Mariner fixture. Runs once per
    hosted deploy (Fly's release command) with the owner role."""
    from alembic import command
    from alembic.config import Config

    from groundwork.config import REPO_ROOT

    cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    command.upgrade(cfg, "head")
    console.print("[green]Migrated[/] to the latest schema.")
    seed(DEFAULT_SITE, test=False)


@app.command()
def preflight(
    hosted: bool = typer.Option(False, help="Check as if GROUNDWORK_HOSTED were true"),
) -> None:
    """Say whether this configuration may serve the public hosted demo. The API runs the same check
    at startup in the hosted profile and refuses to serve if anything is listed."""
    from groundwork.config import hosted_problems

    cfg = get_settings()
    if not (hosted or cfg.groundwork_hosted):
        console.print("Not the hosted profile; nothing to check. Use --hosted to check anyway.")
        return
    problems = hosted_problems(cfg)
    for p in problems:
        console.print(f"[red]✗[/] {p}")
    if problems:
        raise typer.Exit(1)
    console.print("[green]✓[/] fit to serve the hosted demo")


@app.command("hosted-bootstrap")
def hosted_bootstrap(
    admin_url: str = typer.Option(
        ...,
        envvar="GROUNDWORK_DB_ADMIN_URL",
        prompt="Database admin connection string (for Neon: the neondb_owner string from the console)",
        hide_input=True,
        help="Used once to create the roles and database; never stored.",
    ),
    out: Path = typer.Option(
        None, help="Where to write the hosted secrets (default: .env.hosted at the repo root)"
    ),
    database: str = typer.Option("groundwork", help="Database to create for the demo"),
    sslmode: str = typer.Option(
        "", help="sslmode for the app's URLs (default: the admin URL's, else require)"
    ),
    force: bool = typer.Option(
        False, help="Overwrite an existing secrets file (rotates both database passwords)"
    ),
) -> None:
    """Prepare a managed Postgres for the hosted demo and write its secrets to a file, never the
    screen: two roles with random passwords (neither gets BYPASSRLS), a database the owner role owns,
    a fresh signing secret and admin token. `scripts/deploy-fly.sh` imports the file into Fly."""
    import os
    import secrets
    from datetime import datetime

    import psycopg
    from psycopg import sql
    from sqlalchemy.engine import make_url

    from groundwork.config import REPO_ROOT

    target = out or REPO_ROOT / ".env.hosted"
    if target.exists() and not force:
        console.print(
            f"[red]{target} exists.[/] Re-running rotates both database passwords; pass --force to do that."
        )
        raise typer.Exit(1)
    admin = make_url(admin_url).set(drivername="postgresql")
    mode = sslmode or admin.query.get("sslmode") or "require"
    mode = mode if isinstance(mode, str) else mode[0]
    passwords = {"groundwork_owner": secrets.token_urlsafe(32), "groundwork_app": secrets.token_urlsafe(32)}

    def conninfo(url) -> str:  # noqa: ANN001 - sqlalchemy URL
        return url.render_as_string(hide_password=False)

    with psycopg.connect(conninfo(admin), autocommit=True, connect_timeout=15) as c:
        for role, password in passwords.items():
            exists = c.execute("select 1 from pg_roles where rolname = %s", [role]).fetchone()
            verb = "ALTER" if exists else "CREATE"
            c.execute(
                sql.SQL(verb + " ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
            console.print(f"{'updated' if exists else 'created'} role [bold]{role}[/]")
        bypass = c.execute("select rolbypassrls from pg_roles where rolname = 'groundwork_app'").fetchone()
        if bypass and bypass[0]:
            console.print("[red]groundwork_app has BYPASSRLS[/]; remove it before serving anything.")
            raise typer.Exit(1)
        # Creating a database owned by another role needs membership in that role.
        c.execute(sql.SQL("GRANT {} TO CURRENT_USER").format(sql.Identifier("groundwork_owner")))
        if not c.execute("select 1 from pg_database where datname = %s", [database]).fetchone():
            c.execute(
                sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(
                    sql.Identifier(database), sql.Identifier("groundwork_owner")
                )
            )
            console.print(f"created database [bold]{database}[/] owned by groundwork_owner")
        else:
            c.execute(
                sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                    sql.Identifier(database), sql.Identifier("groundwork_owner")
                )
            )
            console.print(f"database [bold]{database}[/] exists; owner set to groundwork_owner")

    def role_url(role: str):  # noqa: ANN202
        query = {**dict(admin.query), "sslmode": mode}
        return admin.set(
            drivername="postgresql+psycopg",
            username=role,
            password=passwords[role],
            database=database,
            query=query,
        )

    for role in passwords:  # prove each new login works before writing anything
        with psycopg.connect(conninfo(role_url(role).set(drivername="postgresql")), connect_timeout=15) as c:
            row = c.execute(
                "select current_user::text, pg_encoding_to_char(encoding) from pg_database "
                "where datname = current_database()"
            ).fetchone()
            if not row or row[0] != role or row[1] != "UTF8":
                console.print(f"[red]Could not verify the new login for {role}[/] (got {row}).")
                raise typer.Exit(1)
    lines = [
        f"# Hosted secrets for Groundwork, written by `groundwork hosted-bootstrap` on {datetime.now():%Y-%m-%d %H:%M}.",
        "# Never commit or paste this file. scripts/deploy-fly.sh imports it into Fly: the API gets every",
        "# line, the web app only GROUNDWORK_ADMIN_TOKEN. Add ANTHROPIC_API_KEY=... here to enable the live planner.",
        f"DATABASE_URL={conninfo(role_url('groundwork_app'))}",
        f"DATABASE_OWNER_URL={conninfo(role_url('groundwork_owner'))}",
        f"GROUNDWORK_DEV_HMAC_SECRET={secrets.token_urlsafe(48)}",
        f"GROUNDWORK_ADMIN_TOKEN={secrets.token_urlsafe(24)}",
    ]
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    console.print(
        f"[green]Wrote[/] {target} (database URLs for {admin.host}/{database}, signing secret, admin token; "
        "values not shown). Next: scripts/deploy-fly.sh"
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
        console.print(f"  [dim]{step['i']:>2}[/] {step['kind']:<14} {step['text']}")
    after = _load_db_state(site)
    _print_event(after, event, views.chain_view(after), views.forecast_view(after))
    _slice2_beats(org_id, site, run_id)


def _slice2_beats(org_id: uuid.UUID, site: str, run_id: uuid.UUID) -> None:
    """The plan, an approval by a named person, the acknowledgment that changes nothing, the ledger
    check and tamper, the attestation."""
    from sqlalchemy import text

    from groundwork.approvals import approve
    from groundwork.db import models as m
    from groundwork.db import repo
    from groundwork.db.session import org_session, owner_session
    from groundwork.ledger import verify_chain
    from groundwork.schemas.action import Kind
    from groundwork.service import actions as actions_svc
    from groundwork.service import runs
    from groundwork.service.attestation import attestation
    from groundwork.service.pipeline import execute_actions

    with org_session(org_id) as s:
        state = repo.load_state(s, site)
        plan_row = actions_svc.primary_plan(s, run_id)
        if plan_row is None:
            return
        pv = actions_svc.plan_view(s, state, plan_row)
        mandate = repo.active_mandate(s, state.require_site_id())
    banner = "[yellow]Simulated planner: these actions were written by hand to exercise the gateway. No model is running.[/]"
    console.rule("[bold]The plan, decided by the gateway")
    if pv["simulated"]:
        console.print(banner)
    console.print(f"[dim]{pv['assessment']}[/]")
    t = Table(header_style="bold", show_lines=False)
    for col in ("ref", "action", "proposed", "gateway", "why", "state"):
        t.add_column(col)
    style = {"auto": "cyan", "ask": "yellow", "refuse": "red"}
    for a in pv["actions"]:
        held = " [yellow](held)[/]" if a["delta"] == "over_reach" else ""
        t.add_row(
            a["ref"],
            a["title"][:52],
            a["proposed_autonomy"],
            f"[{style.get(a['decision'], 'white')}]{a['decision']}[/]{held}",
            a["reason"][:58],
            a["state"],
        )
    console.print(t)
    d = pv["differential"]
    if d:
        console.print(
            f"Delivery: unmitigated {d['unmitigated']} · with what ran {d['now']} · if you approve the queue "
            f"{d['if_approved']} · [green]if the landlord agrees {d['if_they_agree']} "
            f"({d['recovered_if_they_agree']} days back)[/]"
        )
    console.rule("[bold]An auto-reply says 'approved, please proceed'")
    with org_session(org_id) as s:
        ack = runs.start_run(s, site, "ack-approved", None)
    runs.execute_run(org_id, ack)
    with org_session(org_id) as s:
        st = next(x for x in runs.run_view(s, ack).summary["steps"] if x["kind"] == "acknowledgment")  # type: ignore[index]
        pv2 = actions_svc.plan_view(s, repo.load_state(s, site), plan_row)
    console.print(st["text"])
    console.print(
        "States after the message (nothing moved): "
        + ", ".join(f"{a['ref']}={a['state']}" for a in pv2["actions"])
    )
    held = next((a for a in pv["actions"] if a["delta"] == "over_reach" and a["state"] == "pending"), None)
    if held:
        console.rule("[bold]A named person approves one ask")
        with org_session(org_id) as s:
            person = s.execute(select(m.Person).where(m.Person.key.in_(held["approvers"]))).scalars().first()
            action = s.get(m.Action, uuid.UUID(held["id"]))
            assert person is not None and action is not None
            approve(
                s,
                person_id=person.id,
                kid="cli-demo",
                action_id=action.id,
                verdict="approve",
                idempotency_key=f"demo:{held['id']}",
                note="Approved in the CLI demo",
                mandate_version=mandate.version,
                allowed_approvers=mandate.approvers_for(Kind(held["kind"])),
                sla_hours=mandate.ask.sla_hours,
                primary_plan=True,
            )
            done = execute_actions(s, [action], action.run_id)
        console.print(
            f"{person.name} approved {held['ref']} ('{held['title']}'); it ran in dry run: {', '.join(done)}."
        )
    console.rule("[bold]The ledger")
    with org_session(org_id) as s:
        r = verify_chain(s)
    console.print(
        f"verify_chain: [green]ok[/] · {r.count} entries · head {r.head_hash[:16]}…"
        if r.ok
        else f"verify_chain FAILED: {r.problems}"
    )
    with owner_session() as s:
        s.execute(text("ALTER TABLE ledger_entry DISABLE TRIGGER ledger_no_update_delete"))
        s.execute(
            text(
                "UPDATE ledger_entry SET payload = jsonb_set(payload, '{reason}', '\"edited after the fact\"') "
                "WHERE org_id = :o AND entry_type = 'decided' AND seq = (SELECT min(seq) FROM ledger_entry "
                "WHERE org_id = :o AND entry_type = 'decided')"
            ),
            {"o": org_id},
        )
        s.execute(text("ALTER TABLE ledger_entry ENABLE TRIGGER ledger_no_update_delete"))
    with org_session(org_id) as s:
        r2 = verify_chain(s)
        att = attestation(s, site, mandate)
    console.print("Someone with owner credentials disabled the trigger and edited one decision's reason.")
    console.print(
        f"verify_chain: [red]FAILED[/] · {r2.problems[0]}"
        if not r2.ok
        else "verify_chain did not catch it (bug)"
    )
    a = att["attestation"]
    console.rule("[bold]Attestation (genesis to head, HMAC-signed with the dev key)")
    console.print(
        f"violations {a['violations']['count']} · chain verified {a['ledger']['chain_verified']} · head seq "
        f"{a['ledger']['head_seq']} · dry run {a['dry_run']} · signer {a['signer']}"
    )
    console.print(f"signature {att['signature']['value'][:24]}…  (run `make demo` again to reset)")


@app.command()
def cost(site: str = typer.Option("lake-mariner")) -> None:
    """Model spend recorded in the database (plan rows and report entries), at list prices."""
    from evals.run import PRICES
    from evals.run import cost as usd
    from groundwork.db import models as m
    from groundwork.db.session import org_session

    with org_session(_org_for_site(site)) as s:
        plans = list(s.execute(select(m.Plan)).scalars())
        reports = list(s.execute(select(m.LedgerEntry).where(m.LedgerEntry.entry_type == "report")).scalars())
    live = [p for p in plans if p.planner.startswith("claude")]
    total = sum(usd(p.model_id, p.usage) for p in live)
    rep = sum(usd(get_settings().groundwork_report_model, r.payload.get("usage") or {}) for r in reports)
    reads = sum(int(p.usage.get("cache_read_input_tokens", 0)) for p in live)
    console.print(
        f"{len(plans)} plans ({len(live)} live) · planner ${total:.2f} · reports ${rep:.3f} · "
        f"cache-read tokens {reads:,} · prices for {', '.join(PRICES)}"
    )
    if not live:
        console.print(
            "No live plans yet: set ANTHROPIC_API_KEY and play an event. The README has the estimate."
        )


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
