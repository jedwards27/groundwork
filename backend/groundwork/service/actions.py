"""Read side for plans and actions: derive each action's state from decisions, approvals and the
ledger (the action row itself never changes), and assemble the views the API returns."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundwork.db import models as m
from groundwork.db.session import require_org
from groundwork.schemas.action import Effect
from groundwork.service.differential import EffectInput, compute
from groundwork.service.state import SiteState


def ledger_types_by_action(s: Session, action_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[m.LedgerEntry]]:
    rows = s.execute(select(m.LedgerEntry).where(m.LedgerEntry.action_id.in_(action_ids))
                     .order_by(m.LedgerEntry.seq)).scalars() if action_ids else []
    out: dict[uuid.UUID, list[m.LedgerEntry]] = defaultdict(list)
    for r in rows:
        if r.action_id:
            out[r.action_id].append(r)
    return out


def entry_types(entries: list[m.LedgerEntry]) -> list[str]:
    types = []
    for e in entries:
        if e.entry_type == "decided":
            types.append(f"decided:{e.payload.get('decision')}")
        else:
            types.append(e.entry_type)
    return types


def derive_state(latest: m.Decision | None, approvals: list[m.Approval], types: list[str]) -> str:
    if "execution_failed" in types:
        return "failed"
    if "executed" in types:
        return "executed"
    if latest is None:
        return "proposed"
    if latest.decision == "refuse":
        return "refused"
    if any(a.verdict == "decline" for a in approvals):
        return "declined"
    if any(a.verdict == "approve" for a in approvals):
        return "approved"
    if latest.decision == "ask":
        return "pending"
    return "executing"


def primary_plan(s: Session, run_id: uuid.UUID) -> m.Plan | None:
    return s.execute(select(m.Plan).where(m.Plan.run_id == run_id, m.Plan.arm == "informed",
                                          ~m.Plan.planner.like("%:compare"))
                     .order_by(m.Plan.created_at)).scalars().first()


def is_primary(s: Session, action: m.Action) -> bool:
    p = primary_plan(s, action.run_id)
    return p is not None and p.id == action.plan_id


def plan_view(s: Session, state: SiteState, plan: m.Plan) -> dict[str, Any]:
    require_org(s)
    actions = list(s.execute(select(m.Action).where(m.Action.plan_id == plan.id).order_by(m.Action.created_at)).scalars())
    ids = [a.id for a in actions]
    decisions: dict[uuid.UUID, list[m.Decision]] = defaultdict(list)
    for d in s.execute(select(m.Decision).where(m.Decision.action_id.in_(ids)).order_by(m.Decision.created_at)).scalars() if ids else []:
        decisions[d.action_id].append(d)
    approvals: dict[uuid.UUID, list[m.Approval]] = defaultdict(list)
    for ap in s.execute(select(m.Approval).where(m.Approval.action_id.in_(ids))).scalars() if ids else []:
        approvals[ap.action_id].append(ap)
    people = {p.id: p for p in s.execute(select(m.Person)).scalars()}
    names = {x.key: x.name for x in state.people} | {p.key: p.name for p in state.parties}
    ledger = ledger_types_by_action(s, ids)
    out_actions, effects = [], []
    for a in actions:
        latest = decisions[a.id][-1] if decisions[a.id] else None
        types = entry_types(ledger[a.id])
        st = derive_state(latest, approvals[a.id], types)
        ctx = latest.context if latest else {}
        executed = next((e for e in ledger[a.id] if e.entry_type == "executed"), None)
        failed = next((e for e in ledger[a.id] if e.entry_type == "execution_failed"), None)
        out_actions.append({
            "id": str(a.id), "ref": a.ref, "title": a.title, "executor": a.executor,
            "kind": latest.kind if latest else None, "recipient": a.recipient,
            "recipient_name": names.get(a.recipient or "", None), "asks_party": a.asks_party,
            "path": ctx.get("path", []), "params": a.params, "effect": a.effect,
            "effect_allowed": ctx.get("effect_allowed", True), "effect_reason": ctx.get("effect_reason", ""),
            "response_lag_bd": ctx.get("response_lag_bd", 0), "proposed_autonomy": a.proposed_autonomy,
            "rationale": a.rationale, "evidence": a.evidence,
            "decision": latest.decision if latest else None, "reason": latest.reason if latest else "",
            "rule": latest.rule if latest else "", "delta": latest.delta if latest else "",
            "record_bearing": latest.record_bearing if latest else False,
            "content_class": latest.content_class if latest else None,
            "classifier": latest.classifier if latest else "", "amount_cents": latest.amount_cents if latest else None,
            "mandate_version": latest.mandate_version if latest else None,
            "approvers": ctx.get("approvers", []), "state": st, "action_hash": a.action_hash,
            "approvals": [{"person": people[ap.person_id].key, "person_name": people[ap.person_id].name,
                           "verdict": ap.verdict, "at": ap.created_at.isoformat(), "kid": ap.kid, "note": ap.note}
                          for ap in approvals[a.id] if ap.person_id in people],
            "external_ref": executed.payload.get("external_ref") if executed else None,
            "execution_detail": (executed.payload.get("detail") if executed else
                                 failed.payload.get("error") if failed else None),
            "ledger": [{"seq": e.seq, "type": e.entry_type} for e in ledger[a.id]],
        })
        effects.append(EffectInput(a.ref, Effect.model_validate(a.effect), bool(ctx.get("effect_allowed", True)),
                                   int(ctx.get("response_lag_bd", 0)), st))
    report = s.execute(select(m.LedgerEntry).where(m.LedgerEntry.run_id == plan.run_id,
                                                   m.LedgerEntry.entry_type == "report",
                                                   m.LedgerEntry.arm == plan.arm)
                       .order_by(m.LedgerEntry.seq.desc())).scalars().first()
    mismatch = s.execute(select(m.LedgerEntry).where(m.LedgerEntry.run_id == plan.run_id,
                                                     m.LedgerEntry.entry_type == "report_mismatch",
                                                     m.LedgerEntry.arm == plan.arm)).scalars().first()
    diff = compute(state, effects).as_dict() if plan.arm == "informed" else None
    return {
        "run_id": str(plan.run_id), "plan_id": str(plan.id), "arm": plan.arm, "planner": plan.planner,
        "model_id": plan.model_id, "simulated": plan.planner == "simulated",
        "assessment": plan.content.get("assessment", ""), "intent": plan.content.get("intent", {}),
        "actions": out_actions, "usage": plan.usage, "created_at": plan.created_at.isoformat(),
        "report": report.payload if report else None,
        "report_check": (mismatch.payload if mismatch else {"ok": True, "omission": [], "fabrication": [], "inversion": []})
        if report else None,
        "differential": diff,
    }
