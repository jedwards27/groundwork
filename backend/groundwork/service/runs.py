"""Runs: playing an event creates a run; its pipeline executes in the background.

Slice 1 pipeline: apply the event's delays to the site and record the before/after forecast.
Slice 2 adds the planners, gateway, ledger, executors and reports to the same run.
"""

from __future__ import annotations

import traceback
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundwork.db import models as m
from groundwork.db import repo
from groundwork.db.session import org_session, owner_session, require_org
from groundwork.service import views

STALE_AFTER = timedelta(minutes=10)


class RunConflict(ValueError):
    pass


def start_run(s: Session, site_key: str, event_key: str, person_id: uuid.UUID | None) -> uuid.UUID:
    org_id = require_org(s)
    state = repo.load_state(s, site_key)
    if event_key not in state.event_status:
        raise KeyError(event_key)
    if state.event_status[event_key] == "applied":
        raise RunConflict(f"event {event_key!r} has already been played; reset the site to play it again")
    run = m.Run(
        org_id=org_id,
        site_id=state.site_id,
        event_id=state.ids[f"event:{event_key}"],
        status="queued",
        created_by_person_id=person_id,
        summary={"steps": [_step(1, "queued", f"Event '{state.event(event_key).title}' received")]},
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


def execute_run(org_id: uuid.UUID, run_id: uuid.UUID) -> None:
    """Background entry point. Each phase commits, so a crash leaves a truthful partial record."""
    try:
        with org_session(org_id) as s:
            run = s.get(m.Run, run_id)
            assert run is not None
            run.status, run.started_at = "running", datetime.now(UTC)
            _append(s, run_id, "running", "Recomputing the critical path")
        with org_session(org_id) as s:
            run = s.get(m.Run, run_id)
            assert run is not None
            event = s.get(m.Event, run.event_id)
            site = s.get(m.Site, run.site_id)
            assert event is not None and site is not None
            before = views.chain_view(repo.load_state(s, site.key))
            repo.set_event_status(s, site.id, event.key, "applied")
            after_state = repo.load_state(s, site.key)
            after = views.chain_view(after_state)
            fc = views.forecast_view(after_state)
            ms_b, ms_a = before.milestone, after.milestone
            _append(
                s,
                run_id,
                "forecast",
                f"{ms_a.label}: {ms_b.forecast_finish} -> {ms_a.forecast_finish} "
                f"(range {ms_a.forecast_low} to {ms_a.forecast_high}); gate {after.gate}",
                before={"finish": str(ms_b.forecast_finish), "delta": ms_b.delta_days, "gate": before.gate},
                after={
                    "finish": str(ms_a.forecast_finish),
                    "low": str(ms_a.forecast_low),
                    "high": str(ms_a.forecast_high),
                    "delta": ms_a.delta_days,
                    "gate": after.gate,
                    "critical_path": after.critical_path,
                },
            )
            run = s.get(m.Run, run_id)
            assert run is not None
            summary = dict(run.summary or {})
            summary["milestone_before"] = ms_b.model_dump(mode="json")
            summary["milestone_after"] = fc.milestone.model_dump(mode="json")
            run.summary = summary
        with org_session(org_id) as s:
            run = s.get(m.Run, run_id)
            assert run is not None
            run.status, run.finished_at = "done", datetime.now(UTC)
            _append(s, run_id, "done", "Run complete")
    except Exception as exc:  # noqa: BLE001 - any failure must land on the run row
        with org_session(org_id) as s:
            run = s.get(m.Run, run_id)
            if run is not None:
                message = f"{type(exc).__name__}: {exc}"
                run.status, run.finished_at, run.error = "failed", datetime.now(UTC), message
                _append(s, run_id, "failed", message, trace=traceback.format_exc()[-2000:])


def sweep_interrupted(now: datetime | None = None) -> int:
    """Startup sweep (owner role, across orgs): runs left queued or running by a dead process."""
    cutoff = (now or datetime.now(UTC)) - STALE_AFTER
    with owner_session() as s:
        stale = list(
            s.execute(
                select(m.Run).where(m.Run.status.in_(("queued", "running")), m.Run.created_at < cutoff)
            ).scalars()
        )
        for run in stale:
            run.status, run.finished_at = "failed", datetime.now(UTC)
            run.error = "interrupted: the process restarted mid-run; replay or re-run"
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
