"""HTTP API. Identity comes from a signed bearer token; every query runs in an org-scoped session."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from groundwork import __version__
from groundwork.api.auth import Identity
from groundwork.api.deps import db, identity
from groundwork.config import get_settings
from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import org_session, owner_session
from groundwork.schemas.views import (
    ChainView,
    EventView,
    ForecastView,
    RunView,
    SiteSummary,
    SiteView,
)
from groundwork.service import runs, views

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        n = await run_in_threadpool(runs.sweep_interrupted)
        if n:
            log.warning("startup_sweep", interrupted_runs=n)
    except Exception as exc:  # noqa: BLE001 - a missing owner role must not stop the API from serving reads
        log.error("startup_sweep_failed", error=str(exc))
    yield


app = FastAPI(
    title="Groundwork API",
    version=__version__,
    summary="Paper critical path, slip forecasts, and bounded action under an explicit mandate.",
    lifespan=lifespan,
)


class MeView(BaseModel):
    person: str
    name: str
    party: str
    approver: bool
    org: str
    kid: str
    dry_run: bool
    hosted: bool


class PlayEvent(BaseModel):
    event: str


class RunStarted(BaseModel):
    run_id: str
    stream: str


def _state(s: Session, site: str):  # type: ignore[no-untyped-def]
    try:
        return repo.load_state(s, site)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no site {site!r}") from exc


def _check_scenario(state, scenario: list[str]) -> list[str]:  # type: ignore[no-untyped-def]
    unknown = [k for k in scenario if k not in state.event_status]
    if unknown:
        raise HTTPException(422, f"unknown events: {', '.join(unknown)}")
    return scenario


@app.get("/health")
def health() -> dict[str, Any]:
    s = get_settings()
    return {"ok": True, "version": __version__, "dry_run": s.dry_run, "hosted": s.groundwork_hosted}


@app.get("/me", response_model=MeView)
def me(who: Identity = Depends(identity), s: Session = Depends(db)) -> MeView:
    person = s.get(m.Person, who.person_id)
    org = s.get(m.Org, who.org_id)
    if person is None or org is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token names a person or org that does not exist")
    party = s.get(m.Party, person.party_id)
    cfg = get_settings()
    return MeView(
        person=person.key,
        name=person.name,
        party=party.key if party else "",
        approver=person.approver,
        org=org.name,
        kid=who.kid,
        dry_run=cfg.dry_run,
        hosted=cfg.groundwork_hosted,
    )


@app.get("/sites", response_model=list[SiteSummary])
def list_sites(s: Session = Depends(db)) -> list[SiteSummary]:
    return [views.site_summary(repo.load_state(s, k)) for k in repo.list_site_keys(s)]


@app.get("/sites/{site}", response_model=SiteView)
def get_site(site: str, s: Session = Depends(db)) -> SiteView:
    return views.site_view(_state(s, site))


@app.get("/sites/{site}/chain", response_model=ChainView)
def get_chain(site: str, scenario: list[str] = Query(default=[]), s: Session = Depends(db)) -> ChainView:
    state = _state(s, site)
    return views.chain_view(state, scenario=_check_scenario(state, scenario))


@app.get("/sites/{site}/critical-path")
def get_critical_path(
    site: str, scenario: list[str] = Query(default=[]), s: Session = Depends(db)
) -> dict[str, Any]:
    state = _state(s, site)
    c = views.chain_view(state, scenario=_check_scenario(state, scenario))
    titles = {i.key: i.title for i in c.items}
    return {
        "milestone": c.milestone.model_dump(mode="json"),
        "gate": c.gate,
        "gate_title": titles.get(c.gate or ""),
        "critical_path": [{"key": k, "title": titles[k]} for k in c.critical_path],
        "near_critical": [{"key": k, "title": titles[k]} for k in c.near_critical],
        "min_float": c.min_float,
        "calendar_losses": [x.sentence for x in c.calendar_losses],
    }


@app.get("/sites/{site}/forecast", response_model=ForecastView)
def get_forecast(
    site: str, scenario: list[str] = Query(default=[]), s: Session = Depends(db)
) -> ForecastView:
    state = _state(s, site)
    return views.forecast_view(state, scenario=_check_scenario(state, scenario))


@app.get("/sites/{site}/events", response_model=list[EventView])
def list_events(site: str, s: Session = Depends(db)) -> list[EventView]:
    state = _state(s, site)
    return [views.event_view(state, e) for e in state.events]


@app.post("/sites/{site}/events", response_model=RunStarted, status_code=status.HTTP_202_ACCEPTED)
def play_event(
    site: str, body: PlayEvent, background: BackgroundTasks, who: Identity = Depends(identity)
) -> RunStarted:
    # The run row must be committed before the background task looks for it, so this handler opens
    # (and closes) its own transaction instead of using the request-scoped session.
    try:
        with org_session(who.org_id) as s:
            run_id = runs.start_run(s, site, body.event, who.person_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no event {body.event!r} at {site!r}") from exc
    except runs.RunConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    background.add_task(runs.execute_run, who.org_id, run_id)
    return RunStarted(run_id=str(run_id), stream=f"/runs/{run_id}/stream")


def _run_view(org_id: uuid.UUID, run_id: uuid.UUID) -> RunView:
    with org_session(org_id) as s:
        return runs.run_view(s, run_id)


@app.get("/runs/{run_id}", response_model=RunView)
def get_run(run_id: uuid.UUID, who: Identity = Depends(identity)) -> RunView:
    try:
        return _run_view(who.org_id, run_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such run") from exc


@app.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: uuid.UUID,
    request: Request,
    who: Identity = Depends(identity),
    last_event_id: str | None = Header(default=None),
) -> EventSourceResponse:
    """Server-sent events. Each step has an id; reconnect with Last-Event-ID to resume."""
    try:
        await run_in_threadpool(_run_view, who.org_id, run_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such run") from exc
    start_after = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0

    async def gen() -> AsyncIterator[dict[str, str]]:
        sent = start_after
        while True:
            if await request.is_disconnected():
                return
            rv = await run_in_threadpool(_run_view, who.org_id, run_id)
            steps = (rv.summary or {}).get("steps", [])
            for step in steps:
                if step["i"] > sent:
                    sent = step["i"]
                    yield {"id": str(step["i"]), "event": "step", "data": json.dumps(step)}
            if rv.status in ("done", "failed"):
                yield {"event": "end", "data": rv.model_dump_json()}
                return
            await asyncio.sleep(0.25)

    return EventSourceResponse(gen())


@app.post("/admin/reset")
def admin_reset(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Reload every site folder under the fixtures directory (owner role). Demo and test use only."""
    cfg = get_settings()
    if not cfg.groundwork_admin_token or x_admin_token != cfg.groundwork_admin_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin token required")
    from groundwork.ingest import load_site

    loaded = []
    with owner_session() as s:
        for folder in sorted(p for p in cfg.groundwork_fixtures_dir.iterdir() if (p / "site.yaml").exists()):
            repo.seed_bundle(s, load_site(folder))
            loaded.append(folder.name)
        orgs = [o.name for o in s.execute(select(m.Org)).scalars()]
    return {"reloaded": loaded, "orgs": orgs}
