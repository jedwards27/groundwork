"""Hash chain per org.

Each entry's hash is SHA-256 over the RFC 8785 canonical JSON of a fixed field list:
``org_id, seq, prev_hash, entry_type, run_id, action_id, arm, recorded_at, payload``. Amounts in
payloads are integer cents; timestamps are RFC 3339 strings written by the application, so the hash
does not depend on database defaults or clock formatting. Appends for one org are serialized by a
transaction-scoped advisory lock, so two concurrent writers cannot fork the chain; ``seq`` is unique
per org as a second guard.

What this protects against: editing, deleting or reordering any entry, or inserting one in the
middle, is detected by ``verify_chain``. Rewriting the whole chain from the start is not detectable
from the chain alone; the head hash must be exported (the attestation carries it) and compared.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import rfc8785
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from groundwork.db.models import LedgerEntry
from groundwork.db.session import require_org

GENESIS = "0" * 64
HASHED_FIELDS = (
    "org_id",
    "seq",
    "prev_hash",
    "entry_type",
    "run_id",
    "action_id",
    "arm",
    "recorded_at",
    "payload",
)


def _jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, float):
        if v.is_integer():
            return int(v)
        raise TypeError("ledger payloads use integer units (cents, days); got a float")
    if hasattr(v, "value") and isinstance(v.value, str):  # enums
        return v.value
    return v


def canonical(body: dict[str, Any]) -> bytes:
    return rfc8785.dumps(_jsonable(body))


def entry_hash(body: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(body)).hexdigest()


def _body(row_like: dict[str, Any]) -> dict[str, Any]:
    return {k: row_like[k] for k in HASHED_FIELDS}


def now_rfc3339() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _lock(s: Session, org_id: uuid.UUID) -> None:
    s.execute(text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"ledger:{org_id}"})


def head(s: Session) -> tuple[int, str]:
    require_org(s)
    row = s.execute(
        select(LedgerEntry.seq, LedgerEntry.hash).order_by(LedgerEntry.seq.desc()).limit(1)
    ).first()
    return (int(row[0]), str(row[1])) if row else (0, GENESIS)


def append(
    s: Session,
    entry_type: str,
    payload: dict[str, Any],
    *,
    org_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    action_id: uuid.UUID | None = None,
    arm: str | None = None,
    recorded_at: str | None = None,
) -> LedgerEntry:
    """Append one entry. Call inside an org-scoped transaction (or an owner session with org_id)."""
    oid = org_id or require_org(s)
    _lock(s, oid)
    row = s.execute(
        select(LedgerEntry.seq, LedgerEntry.hash)
        .where(LedgerEntry.org_id == oid)
        .order_by(LedgerEntry.seq.desc())
        .limit(1)
    ).first()
    seq, prev = (int(row[0]) + 1, str(row[1])) if row else (1, GENESIS)
    body = {
        "org_id": str(oid),
        "seq": seq,
        "prev_hash": prev,
        "entry_type": entry_type,
        "run_id": str(run_id) if run_id else None,
        "action_id": str(action_id) if action_id else None,
        "arm": arm,
        "recorded_at": recorded_at or now_rfc3339(),
        "payload": _jsonable(payload),
    }
    entry = LedgerEntry(
        org_id=oid,
        seq=seq,
        prev_hash=prev,
        hash=entry_hash(body),
        entry_type=entry_type,
        run_id=run_id,
        action_id=action_id,
        arm=arm,
        recorded_at=body["recorded_at"],
        payload=body["payload"],
    )
    s.add(entry)
    s.flush()
    return entry


@dataclass
class ChainReport:
    ok: bool
    count: int
    head_seq: int
    head_hash: str
    problems: list[str] = field(default_factory=list)


def _stored_body(e: LedgerEntry) -> dict[str, Any]:
    return {
        "org_id": str(e.org_id),
        "seq": e.seq,
        "prev_hash": e.prev_hash,
        "entry_type": e.entry_type,
        "run_id": str(e.run_id) if e.run_id else None,
        "action_id": str(e.action_id) if e.action_id else None,
        "arm": e.arm,
        "recorded_at": e.recorded_at,
        "payload": e.payload,
    }


def verify_chain(s: Session, org_id: uuid.UUID | None = None) -> ChainReport:
    """Walk the org's chain from seq 1: contiguity, links and recomputed hashes."""
    q = select(LedgerEntry).order_by(LedgerEntry.seq)
    if org_id is not None:
        q = q.where(LedgerEntry.org_id == org_id)
    else:
        require_org(s)
    rows = list(s.execute(q).scalars())
    problems: list[str] = []
    prev = GENESIS
    for expected_seq, e in enumerate(rows, start=1):
        if e.seq != expected_seq:
            problems.append(
                f"seq {e.seq} found where {expected_seq} was expected (an entry is missing or reordered)"
            )
        if e.prev_hash != prev:
            problems.append(f"seq {e.seq}: prev_hash does not match the hash of the entry before it")
        if entry_hash(_stored_body(e)) != e.hash:
            problems.append(f"seq {e.seq}: contents do not match its hash (the entry was altered)")
        prev = e.hash
    last = rows[-1] if rows else None
    return ChainReport(
        ok=not problems,
        count=len(rows),
        head_seq=last.seq if last else 0,
        head_hash=last.hash if last else GENESIS,
        problems=problems,
    )


def verify_entry(s: Session, seq: int, claimed: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check one record: recompute its hash, walk the chain up to it, and, when a copy of the record is
    supplied (pasted from a receipt or an export), recompute that copy's hash too. The copy matches
    only if it hashes to exactly what the chain holds at that seq."""
    require_org(s)
    rows = list(
        s.execute(select(LedgerEntry).where(LedgerEntry.seq <= seq).order_by(LedgerEntry.seq)).scalars()
    )
    target = rows[-1] if rows and rows[-1].seq == seq else None
    if target is None:
        return {"seq": seq, "found": False, "match": False, "problems": [f"no record {seq} in this ledger"]}
    problems: list[str] = []
    prev = GENESIS
    for expected_seq, e in enumerate(rows, start=1):
        if e.seq != expected_seq:
            problems.append(f"seq {e.seq} found where {expected_seq} was expected")
        if e.prev_hash != prev:
            problems.append(f"seq {e.seq}: prev_hash does not match the record before it")
        if entry_hash(_stored_body(e)) != e.hash:
            problems.append(f"seq {e.seq}: contents do not match its hash (the record was altered)")
        prev = e.hash
    computed = entry_hash(_stored_body(target))
    copy_hash = None
    if claimed is not None:
        copy = {
            "org_id": str(target.org_id),
            "seq": claimed.get("seq"),
            "prev_hash": claimed.get("prev_hash"),
            "entry_type": claimed.get("entry_type", claimed.get("type")),
            "run_id": claimed.get("run_id"),
            "action_id": claimed.get("action_id"),
            "arm": claimed.get("arm"),
            "recorded_at": claimed.get("recorded_at"),
            "payload": claimed.get("payload"),
        }
        copy_hash = entry_hash(copy)
        if copy_hash != target.hash:
            problems.append(f"the supplied copy of record {seq} does not match what the ledger holds")
    mandate_version = target.payload.get("mandate_version")
    if mandate_version is None and target.action_id is not None:
        decided = [e for e in rows if e.action_id == target.action_id and e.entry_type == "decided"]
        if decided:
            mandate_version = decided[-1].payload.get("mandate_version")
    return {
        "seq": seq,
        "found": True,
        "type": target.entry_type,
        "recorded_at": target.recorded_at,
        "stored_hash": target.hash,
        "recomputed_hash": computed,
        "copy_hash": copy_hash,
        "mandate_version": mandate_version,
        "match": not problems,
        "problems": problems,
    }
