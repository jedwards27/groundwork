"""Decide a whole plan against a mandate, purely (no database), for the run pipeline, the dial
preview and the evals. Then record each decision: `record_decision` is the one place a decision
row and its ledger record are written, for a first decision and a re-decision alike."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from groundwork.db import models as m
from groundwork.domain import get_profile
from groundwork.ledger import append
from groundwork.policy import Decision, Mandate, decide
from groundwork.policy.gateway import SPEND_KINDS
from groundwork.schemas.action import Autonomy, ContentClass, ProposedAction
from groundwork.schemas.plan import Plan
from groundwork.service.context import Resolved, classified_text, resolve
from groundwork.service.state import SiteState


class TextClassifier(Protocol):
    model: str

    def classify(self, text: str) -> tuple[ContentClass, str, dict[str, Any]]: ...


@dataclass
class DecidedAction:
    action: ProposedAction
    resolved: Resolved
    decision: Decision
    classifier_reason: str = ""


def decide_plan(
    state: SiteState,
    mandate: Mandate,
    plan: Plan,
    *,
    spent_today_cents: int = 0,
    classifier: TextClassifier | None = None,
) -> list[DecidedAction]:
    profile = get_profile(state.profile)
    spent = spent_today_cents
    out: list[DecidedAction] = []
    for a in plan.actions:
        model_class, model_name, why = None, None, ""
        text = classified_text(a)
        if classifier is not None and text is not None:
            model_class, why, _ = classifier.classify(text)
            model_name = classifier.model
        r = resolve(
            state,
            profile,
            mandate,
            a,
            spent_today_cents=spent,
            model_class=model_class,
            model_name=model_name,
        )
        d = decide(a, r.ctx, mandate)
        if d.decision == Autonomy.auto and d.kind in SPEND_KINDS:
            spent += d.amount_cents or 0
        out.append(DecidedAction(a, r, d, why))
    return out


def intent_check(plan: Plan, decided: list[DecidedAction]) -> dict[str, Any]:
    """Compare the plan's own intent lists with the gateway's decisions."""
    bucket = {ref: k for k in ("auto", "ask", "refuse") for ref in getattr(plan.intent, k)}
    counts = {"match": 0, "over_reach": 0, "over_caution": 0}
    mismatched = []
    for d in decided:
        counts[d.decision.delta] += 1
        if bucket.get(d.action.ref) != d.decision.decision.value:
            mismatched.append(
                {
                    "ref": d.action.ref,
                    "intent": bucket.get(d.action.ref),
                    "decided": d.decision.decision.value,
                }
            )
    return {**counts, "intent_mismatches": mismatched}


def record_decision(s: Session, row: m.Action, d: DecidedAction, mandate: Mandate, **extra: Any) -> None:
    """Write one decision: its row and its "decided" ledger record, in one shape. `extra` adds
    fields to the record, such as a re-decision's previous decision."""
    dec = d.decision
    approvers = mandate.approvers_for(dec.kind) if dec.decision == Autonomy.ask else []
    context = {
        **d.resolved.details,
        "approvers": approvers,
        "clause": dec.clause,
        "classifier_reason": d.classifier_reason,
        "missing_params": list(d.resolved.ctx.missing_params),
    }
    s.add(
        m.Decision(
            org_id=row.org_id,
            action_id=row.id,
            mandate_version=mandate.version,
            decision=dec.decision.value,
            reason=dec.reason,
            rule=dec.rule,
            delta=dec.delta,
            kind=dec.kind.value,
            effect_class=dec.effect_class.value,
            channel=dec.channel.value,
            record_bearing=dec.record_bearing,
            content_class=context["content_class"],
            classifier=d.resolved.ctx.classifier,
            amount_cents=dec.amount_cents,
            context=context,
        )
    )
    append(
        s,
        "decided",
        {
            "ref": row.ref,
            "title": row.title,
            "decision": dec.decision.value,
            "reason": dec.reason,
            "rule": dec.rule,
            "clause": dec.clause,
            "delta": dec.delta,
            "kind": dec.kind.value,
            "record_bearing": dec.record_bearing,
            "content_class": context["content_class"],
            "classifier": d.resolved.ctx.classifier,
            "amount_cents": dec.amount_cents,
            "mandate_version": mandate.version,
            "path": context["path"],
            "effect_allowed": context["effect_allowed"],
            "approvers": approvers,
            **extra,
        },
        run_id=row.run_id,
        action_id=row.id,
        arm=row.arm,
    )
