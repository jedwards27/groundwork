"""The plan as Claude writes it: every field required, none nullable.

Structured outputs compile the schema into a grammar, and the API caps one request at 24 optional
and 16 union-typed fields. The domain ``Plan`` (one flat, nullable parameter bag shared by twelve
executors) has 28 and 19, so the API rejects it as too complex. The wire form says "does not
apply" with ``""``, ``[]`` or ``-1`` instead, and ``to_plan`` maps it back to the domain ``Plan``,
which the gateway validates exactly as before.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from groundwork.schemas.action import (
    ActionParams,
    Autonomy,
    Effect,
    EffectKind,
    Executor,
    ProposedAction,
    RealizedBy,
)
from groundwork.schemas.plan import Intent, Plan

NOT_APPLICABLE = (
    'Fill only what your executor uses; leave the rest "" ([] for attendees, -1 for deposit_cents).'
)


class WireParams(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"description": NOT_APPLICABLE})

    subject: str
    body: str
    agenda: str
    attendees: list[str] = Field(description="Person keys")
    window_start: str = Field(description="ISO date")
    window_end: str = Field(description="ISO date")
    amount_ref: str = Field(description="Evidence key of a quote, PO line or fee offer")
    deposit_cents: int
    cancellation_terms_ref: str
    scope: str
    document_title: str
    package_title: str
    summary: str
    decision: str
    record_ref: str


class WireEffect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: EffectKind
    item: str = Field(description='Item key the effect lands on; "" for kind none')
    pred: str = Field(description='Predecessor item key for lag_reduction and parallelize, else ""')
    days: int = Field(description="Business days; 0 for kind none")
    realized_by: RealizedBy


class WireAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(description="Short id unique within the plan, e.g. a1")
    title: str
    executor: Executor
    recipient: str = Field(description='Person or party key that receives this; "" if none')
    asks_party: str = Field(description='Party that ultimately has to act; "" for the recipient\'s party')
    params: WireParams
    effect: WireEffect
    proposed_autonomy: Autonomy
    rationale: str
    evidence: list[str] = Field(description="Evidence or event keys relied on")


class WireIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto: list[str]
    ask: list[str]
    refuse: list[str]


class WirePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment: str
    actions: list[WireAction]
    intent: WireIntent


def _opt(s: str) -> str | None:
    return s.strip() or None


def to_plan(w: WirePlan) -> Plan:
    actions = []
    for a in w.actions:
        p = a.params
        params = ActionParams(
            **{k: _opt(v) for k, v in p.model_dump().items() if isinstance(v, str)},
            attendees=p.attendees or None,
            deposit_cents=p.deposit_cents if p.deposit_cents >= 0 else None,
        )
        e = a.effect
        effect = Effect(
            kind=e.kind, item=_opt(e.item), pred=_opt(e.pred), days=e.days, realized_by=e.realized_by
        )
        actions.append(
            ProposedAction(
                ref=a.ref,
                title=a.title,
                executor=a.executor,
                recipient=_opt(a.recipient),
                asks_party=_opt(a.asks_party),
                params=params,
                effect=effect,
                proposed_autonomy=a.proposed_autonomy,
                rationale=a.rationale,
                evidence=a.evidence,
            )
        )
    return Plan(assessment=w.assessment, actions=actions, intent=Intent(**w.intent.model_dump()))


def from_plan(plan: Plan) -> WirePlan:
    """The inverse of ``to_plan``, for replays and fakes."""
    actions = []
    for a in plan.actions:
        p = a.params.model_dump()
        params = WireParams(
            **{k: (v or "") for k, v in p.items() if k not in ("attendees", "deposit_cents")},
            attendees=p["attendees"] or [],
            deposit_cents=-1 if p["deposit_cents"] is None else p["deposit_cents"],
        )
        e = a.effect
        actions.append(
            WireAction(
                ref=a.ref,
                title=a.title,
                executor=a.executor,
                recipient=a.recipient or "",
                asks_party=a.asks_party or "",
                params=params,
                effect=WireEffect(
                    kind=e.kind, item=e.item or "", pred=e.pred or "", days=e.days, realized_by=e.realized_by
                ),
                proposed_autonomy=a.proposed_autonomy,
                rationale=a.rationale,
                evidence=a.evidence,
            )
        )
    return WirePlan(
        assessment=plan.assessment, actions=actions, intent=WireIntent(**plan.intent.model_dump())
    )
