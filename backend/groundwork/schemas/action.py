"""The shared Action contract: what a planner may propose.

The planner chooses an executor, a recipient, parameters and an effect. Everything the gateway
decides on is *derived* from those choices (kind, channel, effect class, record-bearing, the path
to the party that must act), never accepted from the model. ``params`` is a flat object of
optional fields so the structured-output grammar sees no deep unions; each executor's required
fields are checked server-side by ``validate_params``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Executor(StrEnum):
    send_email = "send_email"
    request_meeting = "request_meeting"
    schedule_internal = "schedule_internal"
    reserve_slot = "reserve_slot"
    commit_spend = "commit_spend"
    draft_document = "draft_document"
    file_package = "file_package"
    escalate_to_owner = "escalate_to_owner"
    record_decision = "record_decision"
    pay_invoice = "pay_invoice"
    sign_document = "sign_document"
    delete_record = "delete_record"


class EffectClass(StrEnum):
    none = "none"
    internal = "internal"
    external_nonbinding = "external_nonbinding"
    external_binding = "external_binding"


class Kind(StrEnum):
    draft = "draft"
    send = "send"
    chase = "chase"
    file = "file"
    schedule = "schedule"
    reserve = "reserve"
    commit = "commit"
    legal = "legal"
    escalate = "escalate"
    record = "record"
    pay = "pay"
    sign = "sign"
    delete = "delete"


class Channel(StrEnum):
    email = "email"
    call = "call"
    portal = "portal"
    none = "none"


class ContentClass(StrEnum):
    none = "none"
    commits_money = "commits_money"
    accepts_terms = "accepts_terms"
    waives_rights = "waives_rights"
    legal_notice = "legal_notice"
    unknown = "unknown"


class Autonomy(StrEnum):
    auto = "auto"
    ask = "ask"
    refuse = "refuse"


AUTONOMY_RANK = {Autonomy.refuse: 0, Autonomy.ask: 1, Autonomy.auto: 2}


class EffectKind(StrEnum):
    none = "none"
    duration_reduction = "duration_reduction"
    lag_reduction = "lag_reduction"
    parallelize = "parallelize"


class RealizedBy(StrEnum):
    own_action = "own_action"
    counterparty_response = "counterparty_response"


EXECUTOR_EFFECT_CLASS: dict[Executor, EffectClass] = {
    Executor.record_decision: EffectClass.internal,
    Executor.escalate_to_owner: EffectClass.internal,
    Executor.draft_document: EffectClass.internal,
    Executor.schedule_internal: EffectClass.internal,
    Executor.send_email: EffectClass.external_nonbinding,
    Executor.request_meeting: EffectClass.external_nonbinding,
    Executor.reserve_slot: EffectClass.external_binding,
    Executor.commit_spend: EffectClass.external_binding,
    Executor.file_package: EffectClass.external_binding,
    Executor.pay_invoice: EffectClass.external_binding,
    Executor.sign_document: EffectClass.external_binding,
    Executor.delete_record: EffectClass.external_binding,
}

EXECUTOR_CHANNEL: dict[Executor, Channel] = {
    Executor.send_email: Channel.email,
    Executor.request_meeting: Channel.call,
    Executor.file_package: Channel.portal,
}

# Executors that exist only so a proposal can be refused deterministically.
NEVER_EXECUTORS: frozenset[Executor] = frozenset(
    {Executor.pay_invoice, Executor.sign_document, Executor.delete_record}
)

# Executors that send something to another party, and so need a resolvable recipient.
OUTBOUND_EXECUTORS: frozenset[Executor] = frozenset(
    {
        Executor.send_email,
        Executor.request_meeting,
        Executor.reserve_slot,
        Executor.commit_spend,
        Executor.file_package,
        Executor.pay_invoice,
        Executor.sign_document,
    }
)

# Executors whose text is read by the content classifier. Outbound text can only lower autonomy;
# a draft's classification decides whether it is a legal draft (which always asks).
CLASSIFIED_EXECUTORS: frozenset[Executor] = frozenset(
    {Executor.send_email, Executor.request_meeting, Executor.draft_document}
)
OUTBOUND_CLASSIFIED: frozenset[Executor] = frozenset({Executor.send_email, Executor.request_meeting})

REQUIRED_PARAMS: dict[Executor, tuple[str, ...]] = {
    Executor.send_email: ("subject", "body"),
    Executor.request_meeting: ("agenda",),
    Executor.schedule_internal: ("attendees", "window_start"),
    Executor.reserve_slot: ("window_start",),
    Executor.commit_spend: ("amount_ref", "scope"),
    Executor.draft_document: ("document_title",),
    Executor.file_package: ("package_title",),
    Executor.escalate_to_owner: ("summary",),
    Executor.record_decision: ("decision",),
    Executor.pay_invoice: ("amount_ref",),
    Executor.sign_document: ("document_title",),
    Executor.delete_record: ("record_ref",),
}


class ActionParams(BaseModel):
    """Flat parameter bag. Which fields are required depends on the executor."""

    model_config = ConfigDict(extra="forbid")

    subject: str | None = None
    body: str | None = None
    agenda: str | None = None
    attendees: list[str] | None = Field(default=None, description="Person keys")
    window_start: str | None = Field(default=None, description="ISO date")
    window_end: str | None = Field(default=None, description="ISO date")
    amount_ref: str | None = Field(default=None, description="Evidence key of a quote, PO line or fee offer")
    deposit_cents: int | None = None
    cancellation_terms_ref: str | None = None
    scope: str | None = None
    document_title: str | None = None
    package_title: str | None = None
    summary: str | None = None
    decision: str | None = None
    record_ref: str | None = None


class Effect(BaseModel):
    """What the action would change on the schedule if it works. The forecaster computes days."""

    model_config = ConfigDict(extra="forbid")

    kind: EffectKind = EffectKind.none
    item: str | None = Field(default=None, description="Item key the effect lands on")
    pred: str | None = Field(
        default=None, description="Predecessor item key, for lag_reduction and parallelize"
    )
    days: int = Field(default=0, description="Business days")
    realized_by: RealizedBy = RealizedBy.own_action


class ProposedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(description="Short id unique within the plan, e.g. a1")
    title: str
    executor: Executor
    recipient: str | None = Field(default=None, description="Person or party key that receives this")
    asks_party: str | None = Field(
        default=None, description="Party that ultimately has to act; defaults to the recipient's party"
    )
    params: ActionParams = Field(default_factory=ActionParams)
    effect: Effect = Field(default_factory=Effect)
    proposed_autonomy: Autonomy
    rationale: str
    evidence: list[str] = Field(default_factory=list, description="Evidence or event keys relied on")


def validate_params(action: ProposedAction) -> list[str]:
    """Missing required parameters for the chosen executor (empty when complete)."""
    missing = [f for f in REQUIRED_PARAMS[action.executor] if not getattr(action.params, f)]
    if action.executor in OUTBOUND_EXECUTORS and not action.recipient:
        missing.append("recipient")
    return missing
