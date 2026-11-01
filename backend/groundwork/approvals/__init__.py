"""Typed approvals. The only way an ``ask`` becomes approved is ``approve()``, called by the API for
an authenticated person. No inbound message, of any content, reaches this module: ingestion has no
import path to it (import-linter), and ``link_inbound`` only links a message to pending asks for
display."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundwork.db import models as m
from groundwork.db.session import require_org
from groundwork.ledger import append


class ApprovalError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


def action_hash(row: m.Action) -> str:
    """Hash of the immutable proposal; approvals bind to it and executors check it."""
    body = {
        "ref": row.ref,
        "title": row.title,
        "executor": row.executor,
        "recipient": row.recipient,
        "asks_party": row.asks_party,
        "params": row.params,
        "effect": row.effect,
        "run_id": str(row.run_id),
        "plan_id": str(row.plan_id),
    }
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
    )


@dataclass(frozen=True)
class ApprovalResult:
    approval: m.Approval
    created: bool


def approve(
    s: Session,
    *,
    person_id: uuid.UUID,
    kid: str,
    action_id: uuid.UUID,
    verdict: str,
    idempotency_key: str,
    note: str,
    mandate_version: int,
    allowed_approvers: list[str],
    sla_hours: int,
    primary_plan: bool,
) -> ApprovalResult:
    org_id = require_org(s)
    if verdict not in ("approve", "decline"):
        raise ApprovalError(422, "verdict must be approve or decline")
    existing = s.execute(
        select(m.Approval).where(m.Approval.idempotency_key == idempotency_key)
    ).scalar_one_or_none()
    if existing is not None:
        if existing.action_id != action_id or existing.person_id != person_id:
            raise ApprovalError(409, "idempotency key was used for a different approval")
        return ApprovalResult(existing, created=False)
    action = s.get(m.Action, action_id)  # row-level security: another org's action is simply not found
    if action is None:
        raise ApprovalError(404, "no such action")
    if action.arm != "informed" or not primary_plan:
        raise ApprovalError(
            409, "only the user's plan (informed arm) can be approved; this action was for measurement"
        )
    person = s.get(m.Person, person_id)
    if person is None or person.org_id != org_id:
        raise ApprovalError(403, "unknown person")
    if not person.approver or person.key not in allowed_approvers:
        raise ApprovalError(
            403, f"{person.name} is not an approver for this action under mandate v{mandate_version}"
        )
    latest = (
        s.execute(
            select(m.Decision).where(m.Decision.action_id == action_id).order_by(m.Decision.created_at.desc())
        )
        .scalars()
        .first()
    )
    if latest is None or latest.decision != "ask":
        raise ApprovalError(
            409, f"action is not waiting for approval (decision: {latest.decision if latest else 'none'})"
        )
    if s.execute(
        select(m.Approval).where(m.Approval.action_id == action_id, m.Approval.person_id == person_id)
    ).first():
        raise ApprovalError(409, "this person has already decided this action")
    h = action_hash(action)
    if h != action.action_hash:
        raise ApprovalError(409, "action content no longer matches its recorded hash")
    now = datetime.now(UTC)
    row = m.Approval(
        org_id=org_id,
        action_id=action_id,
        action_hash=h,
        mandate_version=mandate_version,
        person_id=person_id,
        kid=kid,
        verdict=verdict,
        note=note,
        expires_at=now + timedelta(hours=sla_hours),
        idempotency_key=idempotency_key,
    )
    s.add(row)
    s.flush()
    append(
        s,
        "approval",
        {
            "ref": action.ref,
            "title": action.title,
            "verdict": verdict,
            "person": person.key,
            "person_name": person.name,
            "kid": kid,
            "action_hash": h,
            "mandate_version": mandate_version,
            "note": note,
        },
        run_id=action.run_id,
        action_id=action.id,
        arm="informed",
    )
    return ApprovalResult(row, created=True)
