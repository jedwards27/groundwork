"""Double clicks: a message played twice runs once, and a draft confirmed twice is applied once."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select

from groundwork.db import models as m
from groundwork.db.session import org_session, owner_session
from groundwork.local import drafts, tools
from groundwork.local.confirm import decide
from groundwork.service import runs
from tests import test_local_plugin as _plugin
from tests import test_project_changes as _changes

pytestmark = pytest.mark.db
local = _plugin.local  # fixture


def _at_once(*calls: Callable[[], Any]) -> list[Any]:
    """Run the calls on their own threads, released together. Returns each result or exception."""
    gate = threading.Barrier(len(calls))
    out: list[Any] = [None] * len(calls)

    def go(n: int) -> None:
        gate.wait()
        try:
            out[n] = calls[n]()
        except Exception as exc:  # noqa: BLE001 - the test inspects it
            out[n] = exc

    threads = [threading.Thread(target=go, args=(n,)) for n in range(len(calls))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return out


def _runs_of(org_id, event_key: str) -> int:
    with owner_session() as s:
        return s.execute(
            select(func.count())
            .select_from(m.Run)
            .join(m.Event, m.Event.id == m.Run.event_id)
            .where(m.Run.org_id == org_id, m.Event.key == event_key)
        ).scalar_one()


def test_playing_the_same_event_twice_conflicts(seeded):
    org = seeded["org_a"]
    with org_session(org) as s:
        runs.start_run(s, "lake-mariner", "event-a", None)
    # The first run hasn't started yet, so the message isn't marked played; the run still holds it.
    with org_session(org) as s, pytest.raises(runs.RunConflict):
        runs.start_run(s, "lake-mariner", "event-a", None)
    assert _runs_of(org, "event-a") == 1


def test_two_plays_at_the_same_moment_make_one_run(seeded):
    org = seeded["org_a"]

    def play() -> Any:
        with org_session(org) as s:
            return runs.start_run(s, "lake-mariner", "event-b", None)

    out = _at_once(play, play)
    assert sum(isinstance(r, runs.RunConflict) for r in out) == 1, out
    assert _runs_of(org, "event-b") == 1


def test_a_failed_run_leaves_the_message_free_to_play_again(seeded):
    org = seeded["org_a"]
    with org_session(org) as s:
        run_id = runs.start_run(s, "lake-mariner", "event-a", None)
    with owner_session() as s:
        s.get(m.Run, run_id).status = "failed"  # type: ignore[union-attr]
    with org_session(org) as s:
        runs.start_run(s, "lake-mariner", "event-a", None)
    assert _runs_of(org, "event-a") == 2


def test_confirming_a_draft_twice_applies_it_once(local):  # noqa: ARG001 - the home folder it set
    tools.setup("Jude Test", "jude@example.test")
    key = _changes._create()
    out = tools.edit_steps(
        key, "The shop started hanging.", change=[tools.StepChange(key="hang", status="in_progress")]
    )
    results = _at_once(lambda: decide(out["draft"], "confirm"), lambda: decide(out["draft"], "confirm"))
    assert sorted(results, key=str).count("That draft is already confirmed.") == 1, results
    with org_session(tools._ref(key).org_id) as s:
        records = (
            s.execute(select(m.LedgerEntry).where(m.LedgerEntry.entry_type == "steps_changed"))
            .scalars()
            .all()
        )
    assert len(records) == 1
    assert drafts.get(out["draft"])["status"] == "confirmed"
    assert {x["item"]: x["status"] for x in tools.steps(key)["steps"]}["hang"] == "in_progress"
