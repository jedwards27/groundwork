"""HTTP API. Identity comes from a signed bearer token; every query runs in an org-scoped session."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from groundwork import __version__
from groundwork.api import limits
from groundwork.api.auth import Identity
from groundwork.api.deps import db, identity
from groundwork.api.home import router as home_router
from groundwork.api.projects import router as projects_router
from groundwork.api.viewer import Viewer, csrf_problem, lead, set_cookie, viewer, viewer_or_none
from groundwork.config import get_settings, hosted_problems
from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import org_session, owner_session
from groundwork.ledger import verify_chain, verify_entry
from groundwork.policy import PRESETS
from groundwork.schemas.views import (
    ChainView,
    EventView,
    ForecastView,
    RunView,
    SiteSummary,
    SiteView,
)
from groundwork.service import actions as actions_svc
from groundwork.service import mandates, overview, reset, runs, sandboxes, views
from groundwork.service.attestation import attestation
from groundwork.service.scorecard import scorecard

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    cfg = get_settings()
    if cfg.groundwork_hosted and (problems := hosted_problems(cfg)):
        raise RuntimeError("refusing to serve the hosted profile: " + "; ".join(problems))
    try:
        n = await run_in_threadpool(runs.sweep_interrupted)
        if n:
            log.warning("startup_sweep", interrupted_runs=n)
    except Exception as exc:  # noqa: BLE001 - a missing owner role must not stop the API from serving reads
        log.error("startup_sweep_failed", error=str(exc))
    nightly = None
    if 0 <= cfg.groundwork_nightly_reset_utc_hour <= 23:
        nightly = asyncio.create_task(reset.nightly(cfg.groundwork_nightly_reset_utc_hour))
    yield
    if nightly:
        nightly.cancel()


app = FastAPI(
    title="Groundwork API",
    version=__version__,
    summary="Paper critical path, slip forecasts, and bounded action under an explicit mandate.",
    lifespan=lifespan,
)
app.include_router(home_router)
app.include_router(projects_router)


@app.middleware("http")
async def refuse_cross_site(request: Request, call_next):  # type: ignore[no-untyped-def]
    """A browser sends the session cookie on its own; a state change riding on it must come from
    this app's own pages (``api/viewer.py``)."""
    problem = csrf_problem(request)
    if problem:
        return JSONResponse({"detail": problem}, status_code=status.HTTP_403_FORBIDDEN)
    return await call_next(request)


class MeView(BaseModel):
    person: str
    name: str
    party: str
    approver: bool
    org: str
    kid: str
    dry_run: bool
    hosted: bool
    # A hosted-demo sandbox: when this visitor's private copy of the demo is deleted.
    sandbox_expires_at: str | None = None


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
    return {
        "ok": True,
        "version": __version__,
        "dry_run": s.dry_run,
        "hosted": s.groundwork_hosted,
        "live_planner": bool(s.anthropic_api_key),
        "planner_model": s.groundwork_planner_model,
        "demo_login": s.groundwork_demo_login,
        "sandboxes": s.groundwork_demo_login and s.groundwork_sandboxes,
    }


@app.get("/me", response_model=MeView)
@app.get("/sites/{site}/me", response_model=MeView)
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
        sandbox_expires_at=org.expires_at.isoformat() if org.expires_at else None,
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


VISITOR_KEY = re.compile(r"^sk-ant-[A-Za-z0-9_\-]{20,300}$")


@app.post("/sites/{site}/events", response_model=RunStarted, status_code=status.HTTP_202_ACCEPTED)
def play_event(
    site: str,
    body: PlayEvent,
    background: BackgroundTasks,
    request: Request,
    who: Identity = Depends(identity),
    x_anthropic_api_key: str | None = Header(default=None, include_in_schema=False),
) -> RunStarted:
    """Play a message. A visitor may send their own model API key with the request to have
    Claude plan it live. The key is used for this run, in memory, and never stored or logged. It
    isn't accepted on a person's own computer, where Claude in their app does the planning."""
    key = (x_anthropic_api_key or "").strip() or None
    if key is not None:
        if get_settings().groundwork_local:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "On your own computer, Claude in the app plans; no key is needed.")
        if not VISITOR_KEY.match(key):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That doesn't look like a Claude API key (it starts with sk-ant-).")
    cfg = get_settings()
    if cfg.groundwork_hosted:
        limits.claim(request, "runs", cfg.groundwork_runs_per_ip, "You've played the demo's emails a lot today. Try again tomorrow.")
    # The run row must be committed before the background task looks for it, so this handler opens
    # (and closes) its own transaction instead of using the request-scoped session.
    try:
        with org_session(who.org_id) as s:
            run_id = runs.start_run(s, site, body.event, who.person_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no event {body.event!r} at {site!r}") from exc
    except runs.RunConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except runs.RunLimit as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    background.add_task(runs.execute_run, who.org_id, run_id, key)
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


STREAM_FOR = 300.0  # seconds; a live run with Claude planning and reporting takes one or two minutes


@app.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: uuid.UUID,
    request: Request,
    who: Identity = Depends(identity),
    last_event_id: str | None = Header(default=None),
) -> EventSourceResponse:
    """Server-sent events. Each step has an id; reconnect with Last-Event-ID to resume. The stream
    ends when the run does, when it waits for Claude's report, or after STREAM_FOR seconds, so a
    stuck run can't hold a connection open."""
    try:
        await run_in_threadpool(_run_view, who.org_id, run_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such run") from exc
    start_after = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
    deadline = asyncio.get_running_loop().time() + STREAM_FOR

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
            if rv.status in ("done", "failed", "waiting_model") or asyncio.get_running_loop().time() > deadline:
                yield {"event": "end", "data": rv.model_dump_json()}
                return
            await asyncio.sleep(0.25)

    return EventSourceResponse(gen())


class SetPreset(BaseModel):
    preset: str


class ApprovalIn(BaseModel):
    verdict: str
    idempotency_key: str
    note: str = ""


def _ledger_rows(
    s: Session, *, arm: str | None = None, run_id: uuid.UUID | None = None, limit: int = 500
) -> list[dict[str, Any]]:
    q = select(m.LedgerEntry).order_by(m.LedgerEntry.seq.desc()).limit(limit)
    if arm == "informed":
        q = q.where((m.LedgerEntry.arm.is_(None)) | (m.LedgerEntry.arm == "informed"))
    elif arm:
        q = q.where(m.LedgerEntry.arm == arm)
    if run_id is not None:
        q = q.where(m.LedgerEntry.run_id == run_id)
    rows = list(s.execute(q).scalars())
    ids = {e.action_id for e in rows if e.action_id is not None and e.entry_type in ("proposed", "executed")}
    params = {a.id: a.params for a in s.execute(select(m.Action).where(m.Action.id.in_(ids))).scalars()} if ids else {}
    out = []
    for e in reversed(rows):
        subject, body = overview.text_of(params[e.action_id]) if e.action_id is not None and e.action_id in params else ("", "")
        out.append(
            {
                "seq": e.seq,
                "type": e.entry_type,
                "arm": e.arm,
                "run_id": str(e.run_id) if e.run_id else None,
                "action_id": str(e.action_id) if e.action_id else None,
                "recorded_at": e.recorded_at,
                "payload": e.payload,
                "hash": e.hash,
                "prev_hash": e.prev_hash,
                # The action as it would have gone out, and whether it went (dry run: it did not).
                "subject": subject,
                "text": body,
                "dry_run": bool(e.entry_type == "executed" and e.payload.get("dry_run")),
            }
        )
    return out


@app.get("/sites/{site}/mandate")
def get_mandate(site: str, s: Session = Depends(db)) -> dict[str, Any]:
    state = _state(s, site)
    return mandates.mandate_view(s, state.require_site_id())


@app.put("/sites/{site}/mandate")
def put_mandate(site: str, body: SetPreset, who: Identity = Depends(identity)) -> dict[str, Any]:
    """Issue a new mandate version from a preset. Re-decides open actions; never re-plans."""
    if body.preset not in PRESETS:
        raise HTTPException(422, f"preset must be one of {', '.join(PRESETS)}")
    with org_session(who.org_id) as s:
        state = _state(s, site)
        person = s.get(m.Person, who.person_id)
        if person is None or not person.approver:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "only an approver can change the mandate")
        return mandates.set_preset(s, state, body.preset, who.person_id, person.key)


@app.get("/sites/{site}/mandate/compare")
def compare_mandates(site: str, s: Session = Depends(db)) -> dict[str, Any]:
    """The latest plan under every preset, without writing anything (the dial preview)."""
    state = _state(s, site)
    plan_row = mandates.latest_primary_plan(s, state.require_site_id())
    if plan_row is None:
        return {"plan_id": None, "presets": []}
    return {"plan_id": str(plan_row.id), "presets": mandates.compare_presets(s, state, plan_row)}


@app.get("/sites/{site}/ledger")
def get_ledger(
    site: str,
    arm: str | None = Query(default="informed"),
    limit: int = Query(default=500, le=5000),
    s: Session = Depends(db),
) -> dict[str, Any]:
    _state(s, site)
    return {"entries": _ledger_rows(s, arm=arm, limit=limit)}


@app.get("/sites/{site}/ledger/verify")
def verify_ledger(site: str, s: Session = Depends(db)) -> dict[str, Any]:
    _state(s, site)
    r = verify_chain(s)
    return {
        "ok": r.ok,
        "count": r.count,
        "head_seq": r.head_seq,
        "head_hash": r.head_hash,
        "problems": r.problems,
    }


class VerifyEntryIn(BaseModel):
    seq: int
    entry: dict[str, Any] | None = None


@app.post("/sites/{site}/ledger/verify-entry")
def verify_ledger_entry(site: str, body: VerifyEntryIn, s: Session = Depends(db)) -> dict[str, Any]:
    """Recompute one record's hash and the chain up to it; compare a supplied copy if there is one."""
    _state(s, site)
    return verify_entry(s, body.seq, body.entry)


@app.get("/sites/{site}/runs")
def list_runs(site: str, s: Session = Depends(db)) -> list[RunView]:
    state = _state(s, site)
    rows = s.execute(
        select(m.Run).where(m.Run.site_id == state.site_id).order_by(m.Run.created_at.desc())
    ).scalars()
    return [runs.run_view(s, r.id) for r in rows]


@app.get("/runs/{run_id}/plans")
def get_run_plans(run_id: uuid.UUID, s: Session = Depends(db)) -> list[dict[str, Any]]:
    run = s.get(m.Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such run")
    site = s.get(m.Site, run.site_id)
    assert site is not None
    state = repo.load_state(s, site.key)
    rows = s.execute(select(m.Plan).where(m.Plan.run_id == run_id).order_by(m.Plan.created_at)).scalars()
    return [actions_svc.plan_view(s, state, p) for p in rows]


@app.get("/sites/{site}/latest-plan")
def latest_plan(site: str, s: Session = Depends(db)) -> dict[str, Any] | None:
    state = _state(s, site)
    plan_row = mandates.latest_primary_plan(s, state.require_site_id())
    return actions_svc.plan_view(s, state, plan_row) if plan_row else None


@app.get("/sites/{site}/actions/pending")
def pending_actions(site: str, s: Session = Depends(db)) -> list[dict[str, Any]]:
    state = _state(s, site)
    out: list[dict[str, Any]] = []
    for r in s.execute(
        select(m.Run).where(m.Run.site_id == state.site_id).order_by(m.Run.created_at)
    ).scalars():
        p = actions_svc.primary_plan(s, r.id)
        if p is not None:
            out += [
                a | {"run_id": str(r.id)}
                for a in actions_svc.plan_view(s, state, p)["actions"]
                if a["state"] == "pending"
            ]
    return out


@app.post("/actions/{action_id}/approvals")
def post_approval(
    action_id: uuid.UUID, body: ApprovalIn, who: Identity = Depends(identity)
) -> dict[str, Any]:
    """A typed approval or decline by the token's person. On approve, the action runs (dry run)."""
    from groundwork.approvals import ApprovalError, approve
    from groundwork.service.pipeline import execute_actions

    with org_session(who.org_id) as s:
        action = s.get(m.Action, action_id)
        if action is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such action")
        run = s.get(m.Run, action.run_id)
        assert run is not None
        mandate = repo.active_mandate(s, run.site_id)
        latest = (
            s.execute(
                select(m.Decision)
                .where(m.Decision.action_id == action_id)
                .order_by(m.Decision.created_at.desc())
            )
            .scalars()
            .first()
        )
        kind = latest.kind if latest else "send"
        from groundwork.schemas.action import Kind

        try:
            result = approve(
                s,
                person_id=who.person_id,
                kid=who.kid,
                action_id=action_id,
                verdict=body.verdict,
                idempotency_key=body.idempotency_key,
                note=body.note,
                mandate_version=mandate.version,
                allowed_approvers=mandate.approvers_for(Kind(kind)),
                sla_hours=mandate.ask.sla_hours,
                primary_plan=actions_svc.is_primary(s, action),
            )
        except ApprovalError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        executed: list[str] = []
        if result.created and body.verdict == "approve":
            executed = execute_actions(s, [action], action.run_id)
        return {
            "approval_id": str(result.approval.id),
            "created": result.created,
            "verdict": result.approval.verdict,
            "executed": executed,
            "action_hash": result.approval.action_hash,
            "mandate_version": result.approval.mandate_version,
        }


@app.get("/sites/{site}/scorecard")
def get_scorecard(site: str, s: Session = Depends(db)) -> dict[str, Any]:
    _state(s, site)
    return scorecard(s)


@app.get("/sites/{site}/attestation")
def get_attestation(site: str, s: Session = Depends(db)) -> dict[str, Any]:
    state = _state(s, site)
    return attestation(s, site, repo.active_mandate(s, state.require_site_id()))


@app.get("/runs/{run_id}/replay")
def replay_run(run_id: uuid.UUID, s: Session = Depends(db)) -> dict[str, Any]:
    """A recorded run, step by step, from the run row and its ledger entries (for replay on stage)."""
    run = s.get(m.Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such run")
    return {
        "run": runs.run_view(s, run_id).model_dump(mode="json"),
        "ledger": _ledger_rows(s, arm=None, run_id=run_id),
    }


class DemoSignIn(BaseModel):
    # With sandboxes: start over in a new sandbox (the current one is deleted).
    fresh: bool = False


def _demo_org_id() -> uuid.UUID:
    cfg = get_settings()
    if not cfg.groundwork_demo_login:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "demo sign-in is disabled")
    with owner_session() as s:
        org = s.execute(select(m.Org).where(m.Org.name == cfg.groundwork_demo_org)).scalar_one_or_none()
        if org is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "demo org not seeded")
        return org.id


def _demo_sign_in(request: Request, fresh: bool) -> dict[str, Any]:
    """A token for the demo project's lead: the one person a visitor is in the demo, followed by
    any projects of their own they created here. With sandboxes on, a visitor without a live sandbox
    gets a new one; a visitor who has one stays in it; `fresh` starts over in a new one and deletes
    the old one (their own projects stay)."""
    from groundwork.api.auth import mint_many

    cfg = get_settings()
    org_id = _demo_org_id()
    current_viewer = viewer_or_none(request)
    ids = list(current_viewer.identities) if current_viewer and not current_viewer.local else []
    # A visitor is "me" in the projects they created, and the demo's lead in its copy.
    with owner_session() as s:
        mine = set(s.execute(select(m.Person.id).where(m.Person.id.in_([i.person_id for i in ids]), m.Person.key == "me")).scalars())
    own = [i for i in ids if i.person_id in mine]
    demo = [i for i in ids if i.person_id not in mine]
    if cfg.groundwork_sandboxes:
        current = demo[0].org_id if demo and sandboxes.live(demo[0].org_id) else None
        if current is None or fresh:
            if cfg.groundwork_hosted:
                limits.claim(request, "sandboxes", cfg.groundwork_sandboxes_per_ip, "You've started the demo over a lot today. Try again tomorrow.")
            try:
                org_id = sandboxes.create()
            except sandboxes.SandboxLimit as exc:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
            if current is not None:
                sandboxes.discard(current)
        else:
            org_id = current
    with owner_session() as s:
        person = lead(s, org_id)
        if person is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "the demo project has no lead approver")
        pid, key, name = person.id, person.key, person.name
    pairs = [(pid, org_id)] + [(i.person_id, i.org_id) for i in own]
    return {
        "token": mint_many(pairs, secret=cfg.groundwork_dev_hmac_secret, ttl_hours=cfg.token_ttl_hours),
        "person": key,
        "name": name,
        "ttl_hours": cfg.token_ttl_hours,
        "sandbox": cfg.groundwork_sandboxes,
    }


@app.post("/auth/demo-login")
def demo_login(request: Request, body: DemoSignIn | None = None) -> dict[str, Any]:
    """A bearer token for the demo project's lead, for scripts. Browsers use POST /session."""
    return _demo_sign_in(request, bool(body and body.fresh))


@app.get("/session")
def get_session(request: Request) -> dict[str, Any]:
    """Who this browser is, if anyone, and how the server runs. Never an error."""
    v = viewer_or_none(request)
    you = None
    if v is not None and v.identities:
        with owner_session() as s:
            people = [(i, s.get(m.Person, i.person_id)) for i in v.identities]
            # On a person's computer they are "me"; a visitor is first of all the demo's lead.
            mine = [(i, p) for i, p in people if p is not None and p.key == "me"]
            ident, person = mine[0] if v.local and mine else people[0]
            org = s.get(m.Org, ident.org_id)
            if person is not None and org is not None:
                you = {
                    "name": person.name,
                    "email": person.email,
                    "person": person.key,
                    "approver": person.approver,
                    # In the demo you act as its fictional lead; the app says so.
                    "demo_lead": person.key != "me",
                    "sandbox_expires_at": org.expires_at.isoformat() if org.expires_at else None,
                }
    return {
        "signed_in": v is not None,
        "local": bool(v and v.local),
        "you": you,
        "projects": len(v.orgs) if v else 0,
        "health": health(),
    }


@app.post("/session")
def start_session(request: Request, response: Response, body: DemoSignIn | None = None) -> dict[str, Any]:
    """Sign this browser in to the demo (a cookie). Only where demo sign-in is on."""
    out = _demo_sign_in(request, bool(body and body.fresh))
    set_cookie(request, response, out.pop("token"), out["ttl_hours"])
    return out


def _demo_identity(v: Viewer) -> Identity:
    """The viewer's identity in the demo project (their sandbox, or the shared demo org). A visitor's
    token names it first; on a person's computer it is the org the fixture was loaded into."""
    if not v.local and v.identities:
        return v.identities[0]
    with owner_session() as s:
        demo = s.execute(select(m.Org.id).where(m.Org.name == get_settings().groundwork_demo_org)).scalars().all()
    found = next((i for i in v.identities if i.org_id in demo), None)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "the demo project is not on this computer")
    return found


def _require_approver(who: Identity) -> None:
    with owner_session() as s:
        person = s.get(m.Person, who.person_id)
    if person is None or not person.approver:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only an approver can reset the demo or edit its ledger")


@app.post("/demo/reset")
def demo_reset(request: Request, response: Response, v: Viewer = Depends(viewer)) -> dict[str, Any]:
    """Start the demo over. Hosted with sandboxes: a fresh private copy. Otherwise the demo
    project is reloaded from its fixture (the approver's own projects are never touched)."""
    cfg = get_settings()
    if cfg.groundwork_sandboxes and not v.local:
        return start_session(request, response, DemoSignIn(fresh=True))
    _require_approver(_demo_identity(v))
    result = reset.reset_fixtures()
    if not v.local:
        # Reloading gives every person a new id, so this browser's token needs replacing.
        out = _demo_sign_in(request, False)
        set_cookie(request, response, out.pop("token"), out["ttl_hours"])
    return result


def _tamper(org_id: uuid.UUID) -> int:
    from sqlalchemy import text

    with owner_session() as s:
        seq = s.execute(
            text("SELECT min(seq) FROM ledger_entry WHERE org_id = :o AND entry_type = 'decided'"),
            {"o": org_id},
        ).scalar()
        if seq is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "play a message first: there is no decision to edit")
        s.execute(text("ALTER TABLE ledger_entry DISABLE TRIGGER ledger_no_update_delete"))
        s.execute(
            text(
                "UPDATE ledger_entry SET payload = jsonb_set(payload, '{reason}', '\"edited after the fact\"') "
                "WHERE org_id = :o AND seq = :q"
            ),
            {"o": org_id, "q": seq},
        )
        s.execute(text("ALTER TABLE ledger_entry ENABLE TRIGGER ledger_no_update_delete"))
    return int(seq)


@app.post("/demo/tamper")
def demo_tamper(v: Viewer = Depends(viewer)) -> dict[str, Any]:
    """Local and development only: edit one decision in the demo project's ledger the way someone
    holding owner credentials could (trigger disabled, row edited, trigger re-enabled).
    Verification then fails. Reset the demo to restore a clean chain. Refused when hosted."""
    if get_settings().groundwork_hosted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "never available in the hosted demo")
    who = _demo_identity(v)
    _require_approver(who)
    return {"edited_seq": _tamper(who.org_id)}


@app.get("/sites/{site}/evidence/{key}")
def get_evidence(site: str, key: str, s: Session = Depends(db)) -> dict[str, Any]:
    state = _state(s, site)
    ev = next((e for e in state.evidence if e.key == key), None)
    if ev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such evidence")
    return {
        "key": ev.key,
        "kind": ev.kind,
        "title": ev.title,
        "party": ev.party,
        "data": ev.data,
        "provenance": ev.provenance,
        "source": ev.source,
    }


@app.post("/admin/tamper")
def admin_tamper(request: Request, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Scripts and tests: the same edit as /demo/tamper with the admin token. It edits the caller's
    org when a valid token comes along, else the demo org. Refused in the hosted profile."""
    cfg = get_settings()
    if cfg.groundwork_hosted or not cfg.groundwork_admin_token or x_admin_token != cfg.groundwork_admin_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin token required; never available when hosted")
    v = viewer_or_none(request)
    if v is not None and not v.local and v.identities:
        return {"edited_seq": _tamper(v.identities[0].org_id)}
    with owner_session() as s:
        org = s.execute(select(m.Org).where(m.Org.name == cfg.groundwork_demo_org)).scalar_one_or_none()
        if org is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "demo org not seeded")
        org_id = org.id
    return {"edited_seq": _tamper(org_id)}


@app.post("/admin/reset")
def admin_reset(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    """Reload every site folder under the fixtures directory (owner role). Demo and test use only."""
    cfg = get_settings()
    if not cfg.groundwork_admin_token or x_admin_token != cfg.groundwork_admin_token:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin token required")
    return reset.reset_fixtures()
