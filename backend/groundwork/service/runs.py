"""Runs: playing an event creates a run; its pipeline executes in the background.

Slice 1 pipeline: apply the event's delays to the site and record the before/after forecast.
Slice 2 adds the planners, gateway, ledger, executors and reports to the same run.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundwork.config import get_settings
from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import owner_session, require_org
from groundwork.service import narration as say

STALE_AFTER = timedelta(minutes=2)


class RunConflict(ValueError):
    pass


class RunLimit(RuntimeError):
    """The org has used today's run allowance (GROUNDWORK_DAILY_RUN_CAP)."""


def start_run(s: Session, site_key: str, event_key: str, person_id: uuid.UUID | None) -> uuid.UUID:
    org_id = require_org(s)
    state = repo.load_state(s, site_key)
    if event_key not in state.event_status:
        raise KeyError(event_key)
    event_id = state.ids[f"event:{event_key}"]
    # Lock the message's row until this request commits, so a second Play of it waits here and then
    # sees the first one's run. Only a run that failed leaves the message free to play again.
    s.execute(select(m.Event.id).where(m.Event.id == event_id).with_for_update())
    taken = s.execute(
        select(m.Run.id).where(m.Run.event_id == event_id, m.Run.status != "failed").limit(1)
    ).first()
    if state.event_status[event_key] == "applied" or taken is not None:
        raise RunConflict(f"event {event_key!r} has already been played; reset the site to play it again")
    # Counted across every org (each hosted visitor has their own), so the cap bounds the database.
    cap = get_settings().groundwork_daily_run_cap
    if cap > 0 and not repo.claim_daily("runs", cap):
        raise RunLimit(
            f"this demo allows {cap} runs a day and they are used up; try again after midnight UTC"
        )
    run = m.Run(
        org_id=org_id,
        site_id=state.site_id,
        event_id=event_id,
        status="queued",
        created_by_person_id=person_id,
        summary={"steps": [_step(1, "queued", say.received(state.event(event_key).title))]},
    )
    s.add(run)
    s.flush()
    return run.id


def _step(i: int, kind: str, text: str, **extra: Any) -> dict[str, Any]:
    return {"i": i, "kind": kind, "text": text, "at": datetime.now(UTC).isoformat(), **extra}


def _append(s: Session, run_id: uuid.UUID, kind: str, text: str, **extra: Any) -> None:
    run = s.get(m.Run, run_id)
    assert run is not None
    summary = dict(run.summary or {})
    steps = list(summary.get("steps", []))
    steps.append(_step(len(steps) + 1, kind, text, **extra))
    summary["steps"] = steps
    run.summary = summary


def execute_run(org_id: uuid.UUID, run_id: uuid.UUID, api_key: str | None = None) -> None:
    """Background entry point; see groundwork.service.pipeline. `api_key` lives only in memory, for
    this run."""
    from groundwork.service.pipeline import execute_run as run_pipeline

    run_pipeline(org_id, run_id, api_key=api_key)


def sweep_interrupted(now: datetime | None = None, *, older_than: timedelta | None = None) -> int:
    """Startup sweep (owner role, across orgs): fail the runs a dead process left queued or running.

    The hosted demo is one process, and the only one that runs anything, so at its start every
    such run is a leftover and all of them are swept. On a laptop each Claude session starts its own
    Groundwork process, and another one may be mid-run, so runs younger than STALE_AFTER are spared
    until the next start. A run waiting for Claude's report is not stuck, so it is left alone."""
    if older_than is None:
        older_than = timedelta(0) if get_settings().groundwork_hosted else STALE_AFTER
    cutoff = (now or datetime.now(UTC)) - older_than
    with owner_session() as s:
        stale = list(
            s.execute(
                select(m.Run).where(m.Run.status.in_(("queued", "running")), m.Run.created_at <= cutoff)
            ).scalars()
        )
        for run in stale:
            run.status, run.finished_at = "failed", datetime.now(UTC)
            run.error = "Interrupted: Groundwork restarted during this run, so it stopped here."
            summary = dict(run.summary or {})
            steps = list(summary.get("steps", []))
            steps.append(_step(len(steps) + 1, "run_aborted", run.error))
            summary["steps"] = steps
            run.summary = summary
        return len(stale)


def run_view(s: Session, run_id: uuid.UUID):  # type: ignore[no-untyped-def]
    from groundwork.schemas.views import RunView

    require_org(s)
    run = s.get(m.Run, run_id)
    if run is None:
        raise KeyError(str(run_id))
    site = s.get(m.Site, run.site_id)
    event = s.get(m.Event, run.event_id)
    assert site is not None and event is not None
    return RunView(
        id=str(run.id),
        site=site.key,
        event=event.key,
        status=run.status,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        summary=run.summary,
    )
