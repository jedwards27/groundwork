"""Decide a whole plan against a mandate, purely (no database). Used by the run pipeline, the dial
preview, and the evals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from groundwork.domain import get_profile
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
        r = resolve(state, profile, mandate, a, spent_today_cents=spent, model_class=model_class, model_name=model_name)
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
            mismatched.append({"ref": d.action.ref, "intent": bucket.get(d.action.ref), "decided": d.decision.decision.value})
    return {**counts, "intent_mismatches": mismatched}
