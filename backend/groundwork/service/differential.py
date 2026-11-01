"""The differential: what the plan changes on the milestone, computed by the scheduler.

Four lines, all on the same target:
  unmitigated      applied events, no mitigations
  now              + own-action effects of actions that ran (or were approved and ran)
  if_approved      + own-action effects of actions waiting for approval
  if_they_agree    + counterparty-dependent effects of actions that ran or wait, no earlier than the
                   response lag the profile assumes for every hop on the path
Effects the gateway could not credit (effect_allowed false) never count.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from groundwork.core import Adjustment
from groundwork.schemas.action import Effect, EffectKind, RealizedBy
from groundwork.service import views
from groundwork.service.context import not_before
from groundwork.service.state import SiteState

COUNTS_NOW = ("executed",)
COUNTS_PENDING = ("pending", "approved")


@dataclass(frozen=True)
class EffectInput:
    ref: str
    effect: Effect
    effect_allowed: bool
    response_lag_bd: int
    state: str  # executed | pending | approved | declined | refused | failed | executing


def _adjustments(state: SiteState, e: EffectInput) -> list[Adjustment]:
    eff = e.effect
    if eff.kind == EffectKind.none or not e.effect_allowed or not eff.item:
        return []
    # A counterparty-dependent effect cannot land before the counterparty can respond.
    floor = (not_before(state.as_of, e.response_lag_bd, state.holidays)
             if eff.realized_by == RealizedBy.counterparty_response else None)
    if eff.kind == EffectKind.duration_reduction:
        return [Adjustment("duration_reduction", eff.item, eff.days, label=e.ref, floor=floor)]
    if eff.kind == EffectKind.lag_reduction:
        return [Adjustment("lag_reduction", eff.item, eff.days, pred=eff.pred, label=e.ref, floor=floor)]
    return [Adjustment("parallelize", eff.item, eff.days, pred=eff.pred, label=e.ref, floor=floor)]


@dataclass
class Differential:
    target_date: date
    unmitigated: date | None
    now: date | None
    if_approved: date | None
    if_they_agree: date | None
    recovered_now: int
    recovered_if_approved: int
    recovered_if_they_agree: int
    contributions: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("target_date", "unmitigated", "now", "if_approved", "if_they_agree"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


def compute(state: SiteState, effects: list[EffectInput]) -> Differential:
    def finish(selected: list[EffectInput]) -> date | None:
        adj = [a for e in selected for a in _adjustments(state, e)]
        return views.run_forecast(state, adjustments=adj).mid.target_finish

    own = [e for e in effects if e.effect.realized_by == RealizedBy.own_action]
    cp = [e for e in effects if e.effect.realized_by == RealizedBy.counterparty_response]
    now_set = [e for e in own if e.state in COUNTS_NOW]
    approve_set = now_set + [e for e in own if e.state in COUNTS_PENDING]
    agree_set = approve_set + [e for e in cp if e.state in COUNTS_NOW + COUNTS_PENDING]
    base = finish([])
    f_now, f_appr, f_agree = finish(now_set), finish(approve_set), finish(agree_set)

    def rec(f: date | None) -> int:
        return max(0, (base - f).days) if base and f else 0

    contributions = []
    for e in effects:
        if e.effect.kind == EffectKind.none:
            continue
        alone = finish([e]) if e.effect_allowed else base
        contributions.append({"ref": e.ref, "state": e.state, "realized_by": e.effect.realized_by.value,
                              "credited": e.effect_allowed, "days_alone": rec(alone),
                              "response_lag_bd": e.response_lag_bd})
    return Differential(target_date=views.primary_milestone(state).target_date, unmitigated=base, now=f_now,
                        if_approved=f_appr, if_they_agree=f_agree, recovered_now=rec(f_now),
                        recovered_if_approved=rec(f_appr), recovered_if_they_agree=rec(f_agree),
                        contributions=contributions)
