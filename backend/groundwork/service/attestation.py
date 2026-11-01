"""The attestation: a signed statement of what the ledger shows, always genesis to head.

``violations`` counts executions that had no prior ``auto`` decision and no approval: zero means the
gateway was never bypassed. Model behaviour (over-reach, over-caution) is reported separately under
``proposal_deltas``, per arm, because it is a property of the model, not a compliance claim.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundwork.api.auth import key_id
from groundwork.config import get_settings
from groundwork.db import models as m
from groundwork.ledger import canonical, verify_chain

WHAT_THIS_DOES_NOT_PROVE = [
    "That the operator is honest: the operator holds the signing key in this build, so the signature shows "
    "integrity to a third party, not against the operator.",
    "That anything happened outside this system: executors run in dry run, so 'executed' means the action was "
    "cleared and recorded, not that a counterparty received it.",
    "That the chain was not rebuilt from scratch: compare head_hash with a copy published earlier.",
    "Who a demo persona really is: identity assurance is shown separately.",
]


def _attest_key(secret: str) -> bytes:
    return hashlib.sha256(("attestation:" + secret).encode()).digest()


def attestation(s: Session, site_key: str, mandate: Any) -> dict[str, Any]:
    cfg = get_settings()
    report = verify_chain(s)
    entries = list(s.execute(select(m.LedgerEntry).order_by(m.LedgerEntry.seq)).scalars())
    cleared: set[Any] = set()
    violations: list[int] = []
    counts: dict[str, int] = {}
    deltas: dict[str, dict[str, int]] = {
        "informed": {"match": 0, "over_reach": 0, "over_caution": 0},
        "blind": {"match": 0, "over_reach": 0, "over_caution": 0},
    }
    seen_first: set[Any] = set()
    for e in entries:
        counts[e.entry_type] = counts.get(e.entry_type, 0) + 1
        p = e.payload
        if e.entry_type == "decided":
            if p.get("decision") == "auto":
                cleared.add(e.action_id)
            if e.action_id not in seen_first and e.arm in deltas and p.get("delta") in deltas[e.arm]:
                deltas[e.arm][p["delta"]] += 1
                seen_first.add(e.action_id)
        elif e.entry_type == "approval" and p.get("verdict") == "approve":
            cleared.add(e.action_id)
        elif e.entry_type == "execution_requested" and e.action_id not in cleared:
            violations.append(e.seq)
    model_ids = sorted({p.model_id for p in s.execute(select(m.Plan)).scalars()})
    doc = {
        "type": "groundwork.attestation.v1",
        "site": site_key,
        "mandate": {
            "id": mandate.id,
            "version": mandate.version,
            "preset": mandate.preset,
            "issuer": mandate.issuer,
        },
        "ledger": {
            "from_seq": 1 if entries else 0,
            "head_seq": report.head_seq,
            "head_hash": report.head_hash,
            "entries": report.count,
            "chain_verified": report.ok,
            "problems": report.problems,
        },
        "counts": counts,
        "violations": {
            "count": len(violations),
            "seqs": violations,
            "definition": "executions with no prior auto decision and no approval",
        },
        "proposal_deltas": deltas,
        "model_ids": model_ids,
        "dry_run": cfg.dry_run,
        "identity_assurance": "demo personas (anyone with the link can act as them)"
        if cfg.groundwork_hosted
        else "dev tokens signed with the local secret",
        "signer": f"operator-dev-key:{key_id(cfg.groundwork_dev_hmac_secret) if cfg.groundwork_dev_hmac_secret else 'none'}",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "what_this_does_not_prove": WHAT_THIS_DOES_NOT_PROVE,
        "production_path": (
            "In production the signer is a key the app role cannot read (a KMS key held by the customer or by "
            "Anthropic as attester), the head hash is published out of band daily, and an auditor or insurer "
            "re-runs verification from an export."
        ),
    }
    sig = hmac.new(
        _attest_key(cfg.groundwork_dev_hmac_secret or "unsigned"), canonical(doc), hashlib.sha256
    ).hexdigest()
    return {"attestation": doc, "signature": {"alg": "HMAC-SHA256", "value": sig}}
