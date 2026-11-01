"""The ledger: canonical hashing, append-only enforcement, tamper detection, no forks."""

import json
import threading

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from groundwork.db import models as m
from groundwork.db.session import org_session, owner_session
from groundwork.ledger import GENESIS, append, canonical, entry_hash, verify_chain

# Published test vector (docs/LEDGER.md): any verifier, in any language, must reproduce this hash.
VECTOR = {
    "org_id": "00000000-0000-0000-0000-000000000001",
    "seq": 1,
    "prev_hash": "0" * 64,
    "entry_type": "decided",
    "run_id": None,
    "action_id": None,
    "arm": "informed",
    "recorded_at": "2026-11-02T14:12:00.000000Z",
    "payload": {
        "decision": "auto",
        "amount_cents": 1850000,
        "reason": "Within the $50,000 limit",
        "title": "Café test ✓",
    },
}
VECTOR_HASH = "6bc8d240cfd8e2cf7a929221d00f98f3c8a4d9161f96483bd20112792de3f4d2"


def test_test_vector():
    assert entry_hash(VECTOR) == VECTOR_HASH
    # For bodies with integer numbers and string keys, RFC 8785 equals sorted compact UTF-8 JSON,
    # so a verifier written with any standard JSON library can check it.
    plain = json.dumps(VECTOR, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert canonical(VECTOR) == plain


def test_floats_are_rejected():
    with pytest.raises(TypeError):
        canonical({"x": 1.5})


pytestmark_db = pytest.mark.db


@pytest.mark.db
def test_chain_verifies_and_detects_tampering(seeded):
    org = seeded["org_a"]
    with org_session(org) as s:
        for i in range(3):
            append(s, "note", {"i": i})
        r = verify_chain(s)
    assert r.ok and r.count == 4 and r.head_seq == 4  # genesis mandate entry + 3
    with owner_session() as s:
        s.execute(text("ALTER TABLE ledger_entry DISABLE TRIGGER ledger_no_update_delete"))
        s.execute(
            text("UPDATE ledger_entry SET payload = '{\"i\": 99}' WHERE org_id = :o AND seq = 3"), {"o": org}
        )
        s.execute(text("ALTER TABLE ledger_entry ENABLE TRIGGER ledger_no_update_delete"))
    with org_session(org) as s:
        r = verify_chain(s)
    assert not r.ok and any("seq 3" in p and "altered" in p for p in r.problems)


@pytest.mark.db
def test_deleting_an_entry_is_detected(seeded):
    org = seeded["org_a"]
    with org_session(org) as s:
        for i in range(3):
            append(s, "note", {"i": i})
    with owner_session() as s:
        s.execute(text("ALTER TABLE ledger_entry DISABLE TRIGGER ledger_no_update_delete"))
        s.execute(text("DELETE FROM ledger_entry WHERE org_id = :o AND seq = 2"), {"o": org})
        s.execute(text("ALTER TABLE ledger_entry ENABLE TRIGGER ledger_no_update_delete"))
    with org_session(org) as s:
        r = verify_chain(s)
    assert not r.ok and any("missing or reordered" in p for p in r.problems)


@pytest.mark.db
def test_trigger_blocks_even_the_owner(seeded):
    with pytest.raises(DBAPIError, match="append-only"):
        with owner_session() as s:
            s.execute(
                text("UPDATE ledger_entry SET entry_type = 'x' WHERE org_id = :o"), {"o": seeded["org_a"]}
            )
    with pytest.raises(DBAPIError, match="append-only"):
        with owner_session() as s:
            s.execute(text("TRUNCATE ledger_entry"))


@pytest.mark.db
def test_app_role_cannot_update_or_delete(seeded):
    with pytest.raises(ProgrammingError, match="permission denied"):
        with org_session(seeded["org_a"]) as s:
            s.execute(text("DELETE FROM ledger_entry"))


@pytest.mark.db
def test_concurrent_appends_do_not_fork(seeded):
    org = seeded["org_a"]
    errors: list[Exception] = []

    def worker(n: int) -> None:
        try:
            for i in range(5):
                with org_session(org) as s:
                    append(s, "note", {"worker": n, "i": i})
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with org_session(org) as s:
        r = verify_chain(s)
        seqs = [x for (x,) in s.execute(select(m.LedgerEntry.seq).order_by(m.LedgerEntry.seq))]
    assert r.ok and seqs == list(range(1, 22))


@pytest.mark.db
def test_genesis_links_to_zero(seeded):
    with org_session(seeded["org_a"]) as s:
        first = s.execute(select(m.LedgerEntry).order_by(m.LedgerEntry.seq)).scalars().first()
    assert first is not None and first.prev_hash == GENESIS and first.entry_type == "mandate_issued"
