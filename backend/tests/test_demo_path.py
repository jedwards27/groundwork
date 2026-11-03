"""The scripted two-minute demo: the same DO, ASK and NEVER every time, model or no model, each with
the mandate clause it relied on; a report that names the refusal; and records anyone can re-check."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from groundwork.api.app import app
from groundwork.config import get_settings
from groundwork.db.session import owner_session
from tests.test_pipeline import by_ref, plan, play, token

pytestmark = pytest.mark.db


@pytest.fixture()
def jordan(seeded):
    with TestClient(app) as c:
        c.headers.update(token(seeded["org_a"], "jordan"))
        yield c


def test_demo_is_scripted_even_with_a_live_key(jordan, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")
    get_settings.cache_clear()
    try:
        run = play(jordan, "demo-monday")
    finally:
        monkeypatch.delenv("ANTHROPIC_API_KEY")
        get_settings.cache_clear()
    p = plan(jordan, run)
    assert p["simulated"] is True
    a = by_ref(p)
    assert [a[r]["decision"] for r in ("a1", "a2", "a3")] == ["auto", "ask", "refuse"]

    # DO: a status request to the lessee's named PM, under the routine-messages clause.
    assert a["a1"]["recipient"] == "morgan" and a["a1"]["state"] == "executed"
    assert a["a1"]["clause"].startswith("routine_messages:")

    # ASK: the landlord-bound request routes Anthropic -> Fluidstack -> TeraWulf to the named approver.
    assert a["a2"]["path"] == ["fluidstack", "terawulf"] and a["a2"]["state"] == "pending"
    assert a["a2"]["approvers"] == ["jordan"]
    assert "direct counterparties only" in a["a2"]["clause"]

    # DENY: the landlord asks for a signature; signing is never delegated.
    assert a["a3"]["executor"] == "sign_document" and a["a3"]["state"] == "refused"
    assert a["a3"]["clause"].startswith("Never: pay, sign, delete")

    # The report discloses the refusal and matches the record.
    assert "Refused: Sign the landlord's revised schedule acknowledgment" in p["report"]["summary"]
    assert "Signing is never delegated" in p["report"]["summary"]
    assert p["report_check"]["ok"] is True


def test_a_record_and_its_copy_verify_and_a_tampered_one_does_not(jordan, seeded):
    play(jordan, "demo-monday")
    entries = jordan.get("/sites/lake-mariner/ledger?arm=").json()["entries"]
    decided = next(e for e in entries if e["type"] == "decided")

    r = jordan.post(
        "/sites/lake-mariner/ledger/verify-entry", json={"seq": decided["seq"], "entry": decided}
    ).json()
    assert r["match"] is True and r["recomputed_hash"] == r["stored_hash"] == r["copy_hash"]
    assert r["mandate_version"] == 1

    forged = {**decided, "payload": {**decided["payload"], "approvers": ["someone-else"]}}
    r = jordan.post(
        "/sites/lake-mariner/ledger/verify-entry", json={"seq": decided["seq"], "entry": forged}
    ).json()
    assert r["match"] is False and "does not match what the ledger holds" in r["problems"][0]

    with owner_session() as s:
        s.execute(text("ALTER TABLE ledger_entry DISABLE TRIGGER ledger_no_update_delete"))
        s.execute(
            text(
                'UPDATE ledger_entry SET payload = payload || \'{"reason": "edited"}\' WHERE org_id = :o AND seq = :q'
            ),
            {"o": seeded["org_a"], "q": decided["seq"]},
        )
        s.execute(text("ALTER TABLE ledger_entry ENABLE TRIGGER ledger_no_update_delete"))
    r = jordan.post("/sites/lake-mariner/ledger/verify-entry", json={"seq": decided["seq"]}).json()
    assert r["match"] is False and any("altered" in p for p in r["problems"])

    assert jordan.post("/sites/lake-mariner/ledger/verify-entry", json={"seq": 99999}).json()["found"] is False
