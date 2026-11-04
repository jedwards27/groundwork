"""A visitor's own Anthropic API key, sent with one Play from their browser tab: it plans that run
live, and it is never stored, not even inside an error message."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select, text

from groundwork.db import models as m
from groundwork.db.session import owner_session
from tests import test_api as _api

pytestmark = pytest.mark.db
client = _api.client  # fixture

KEY = "sk-ant-api03-" + "x" * 40


def test_the_key_reaches_only_that_runs_client_and_is_never_stored(client, monkeypatch):
    import groundwork.agent.claude as claude

    seen: list[str] = []

    def fake_client(api_key: str):
        seen.append(api_key)
        raise RuntimeError(f"could not reach Anthropic with {api_key}")

    monkeypatch.setattr(claude, "make_client", fake_client)
    r = client.post("/sites/lake-mariner/events", json={"event": "event-a"}, headers={"X-Anthropic-Api-Key": KEY})
    assert r.status_code == 202
    assert seen == [KEY]
    run = client.get(f"/runs/{r.json()['run_id']}").json()
    assert run["status"] == "failed" and KEY not in json.dumps(run) and "[your API key]" in run["error"]
    # Nowhere in the database: runs, plans, ledger records.
    with owner_session() as s:
        for table in ("run", "plan", "ledger_entry", "event"):
            dump = s.execute(text(f"SELECT coalesce(string_agg(t::text, ''), '') FROM {table} t")).scalar_one()
            assert KEY not in dump, table
        assert s.execute(select(m.Run)).first() is not None


def test_without_a_key_the_run_stays_simulated(client, monkeypatch):
    import groundwork.agent.claude as claude

    monkeypatch.setattr(claude, "make_client", lambda api_key: pytest.fail("no model without a key"))
    r = client.post("/sites/lake-mariner/events", json={"event": "event-a"})
    assert client.get(f"/runs/{r.json()['run_id']}").json()["status"] == "done"


def test_a_malformed_key_is_refused_before_anything_runs(client):
    r = client.post("/sites/lake-mariner/events", json={"event": "event-a"}, headers={"X-Anthropic-Api-Key": "not-a-key"})
    assert r.status_code == 400 and "sk-ant-" in r.json()["detail"]


def test_the_scripted_demo_message_keeps_its_written_plan_even_with_a_key(client, monkeypatch):
    import groundwork.agent.claude as claude

    monkeypatch.setattr(claude, "make_client", lambda api_key: pytest.fail("the demo message is scripted"))
    r = client.post("/sites/lake-mariner/events", json={"event": "demo-monday"}, headers={"X-Anthropic-Api-Key": KEY})
    assert client.get(f"/runs/{r.json()['run_id']}").json()["status"] == "done"
