"""Runs that can't finish: a restart fails the ones a dead process left behind, and the progress
stream never waits on a run forever."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

import groundwork.api.app as api_app
from groundwork.db import models as m
from groundwork.db.session import org_session, owner_session
from groundwork.service import runs
from tests import test_api as _api

pytestmark = pytest.mark.db
client = _api.client  # fixture


def _queued(org_id) -> object:
    with org_session(org_id) as s:
        return runs.start_run(s, "lake-mariner", "event-a", None)


def _set_status(run_id, status: str) -> None:
    with owner_session() as s:
        s.get(m.Run, run_id).status = status  # type: ignore[union-attr]


def _run(run_id) -> m.Run:
    with owner_session() as s:
        run = s.get(m.Run, run_id)
        assert run is not None
        s.expunge(run)
        return run


def test_startup_sweep_fails_runs_left_running_on_the_hosted_demo(seeded, env):
    queued, running = _queued(seeded["org_a"]), _queued(seeded["org_b"])
    _set_status(running, "running")
    env(GROUNDWORK_HOSTED="true")  # one process runs everything, so any run left at its start is a leftover
    assert runs.sweep_interrupted() >= 2
    for run_id in (queued, running):
        run = _run(run_id)
        assert run.status == "failed" and run.finished_at is not None
        assert run.error and "restarted" in run.error
        assert run.summary is not None and run.summary["steps"][-1]["kind"] == "run_aborted"


def test_on_a_laptop_the_sweep_spares_a_run_another_session_may_be_running(seeded):
    run_id = _queued(seeded["org_a"])
    runs.sweep_interrupted()
    assert _run(run_id).status == "queued"
    runs.sweep_interrupted(datetime.now(UTC) + runs.STALE_AFTER)
    assert _run(run_id).status == "failed"


def test_the_sweep_leaves_a_run_waiting_for_claudes_report(seeded):
    run_id = _queued(seeded["org_a"])
    _set_status(run_id, "waiting_model")
    runs.sweep_interrupted(datetime.now(UTC) + runs.STALE_AFTER)
    assert _run(run_id).status == "waiting_model"


def _end(body: str) -> dict:
    assert "event: end" in body, body
    return json.loads(body.split("event: end", 1)[1].split("data: ", 1)[1].split("\r\n", 1)[0].split("\n", 1)[0])


def test_the_stream_ends_for_a_run_waiting_on_claude_and_for_a_stuck_one(client, seeded, monkeypatch):
    run_id = _queued(seeded["org_a"])
    _set_status(run_id, "waiting_model")
    with client.stream("GET", f"/runs/{run_id}/stream") as r:
        assert _end("".join(r.iter_text()))["status"] == "waiting_model"
    _set_status(run_id, "running")
    monkeypatch.setattr(api_app, "STREAM_FOR", 0.5)
    with client.stream("GET", f"/runs/{run_id}/stream") as r:
        assert _end("".join(r.iter_text()))["status"] == "running"
