"""The gateway: a pure decision over a typed request.

Inputs are the planner's proposed action and a ``RequestContext`` that the caller resolves from
data (the party graph, evidence, the ledger), never from the model's own labels. The kind,
channel, effect class and record-bearing flag are derived here. The order of checks is the policy:
never-list first, then everything that forces a person, then the auto rules, then ask by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from groundwork.policy.mandate import AutoRule, Mandate
from groundwork.schemas.action import (
    AUTONOMY_RANK,
    EXECUTOR_CHANNEL,
    EXECUTOR_EFFECT_CLASS,
    NEVER_EXECUTORS,
    OUTBOUND_CLASSIFIED,
    OUTBOUND_EXECUTORS,
    Autonomy,
    Channel,
    ContentClass,
    EffectClass,
    Executor,
    Kind,
    ProposedAction,
)

SPEND_KINDS = (Kind.reserve, Kind.commit)


@dataclass(frozen=True)
class RequestContext:
    """Facts about a proposed action, resolved by the caller from data."""

    principal: str
    recipient_party: str | None = None
    recipient_known: bool = False
    recipient_direct: bool = False  # the principal has a direct channel to the recipient
    recipient_role_class: str | None = None
    asks_party: str | None = None
    path: tuple[str, ...] = ()  # hops from the principal to the party that must act
    content_class: ContentClass | None = None  # None when the executor's text is not classified
    classifier: str = ""
    prior_thread: bool = False  # the recipient's party has written to the principal
    amount_cents: int | None = None
    amount_ref_valid: bool = False
    cancellation_terms_ok: bool = False
    attendees_internal: bool = True
    effect_allowed: bool = True
    effect_reason: str = ""
    spent_today_cents: int = 0
    missing_params: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Decision:
    decision: Autonomy
    reason: str
    rule: str
    delta: str  # match | over_reach | over_caution
    kind: Kind
    effect_class: EffectClass
    channel: Channel
    record_bearing: bool
    amount_cents: int | None
    clause: str = ""  # the mandate clause the decision relied on, in plain words

    @property
    def held(self) -> bool:
        return self.delta == "over_reach"


def derive_kind(action: ProposedAction, ctx: RequestContext) -> Kind:
    ex = action.executor
    if ex == Executor.send_email:
        return (
            Kind.chase
            if ctx.prior_thread and ctx.recipient_role_class == "counterparty_routine"
            else Kind.send
        )
    if ex == Executor.draft_document:
        return Kind.legal if ctx.content_class == ContentClass.legal_notice else Kind.draft
    return {
        Executor.request_meeting: Kind.send,
        Executor.schedule_internal: Kind.schedule,
        Executor.reserve_slot: Kind.reserve,
        Executor.commit_spend: Kind.commit,
        Executor.file_package: Kind.file,
        Executor.escalate_to_owner: Kind.escalate,
        Executor.record_decision: Kind.record,
        Executor.pay_invoice: Kind.pay,
        Executor.sign_document: Kind.sign,
        Executor.delete_record: Kind.delete,
    }[ex]


def _delta(proposed: Autonomy, decided: Autonomy) -> str:
    p, d = AUTONOMY_RANK[proposed], AUTONOMY_RANK[decided]
    return "match" if p == d else "over_reach" if p > d else "over_caution"


def _money(cents: int) -> str:
    return f"${cents / 100:,.0f}"


def decide(action: ProposedAction, ctx: RequestContext, mandate: Mandate) -> Decision:
    ex = action.executor
    kind = derive_kind(action, ctx)
    effect_class = EXECUTOR_EFFECT_CLASS[ex]
    channel = EXECUTOR_CHANNEL.get(ex, Channel.none)
    role_class = ctx.recipient_role_class or "internal"
    record_bearing = kind in mandate.record_bearing_kinds or role_class in mandate.record_bearing_role_classes

    def out(decision: Autonomy, reason: str, rule: str, clause: str) -> Decision:
        return Decision(
            decision,
            reason,
            rule,
            _delta(action.proposed_autonomy, decision),
            kind,
            effect_class,
            channel,
            record_bearing,
            ctx.amount_cents,
            clause,
        )

    never_clause = f"Never: {', '.join(k.value for k in mandate.never)}. No one can approve these."

    # 1. The never-list, before anything else and regardless of context.
    if ex in NEVER_EXECUTORS or kind in mandate.never:
        return out(Autonomy.refuse, f"Never within authority: {kind.value}", "never", never_clause)

    # 2. Anything that forces a person.
    if ctx.missing_params:
        return out(
            Autonomy.ask,
            f"Incomplete request: missing {', '.join(ctx.missing_params)}",
            "incomplete",
            "Every request must name what its action needs; an incomplete one goes to a person.",
        )
    if ex in OUTBOUND_EXECUTORS and not ctx.recipient_known:
        return out(
            Autonomy.ask,
            "Unknown recipient: not a person or party on this site",
            "unknown_recipient",
            "Recipients must be people or parties on this site.",
        )
    if ex in OUTBOUND_EXECUTORS and not ctx.recipient_direct:
        route = " → ".join(ctx.path) if ctx.path else "an unknown path"
        return out(
            Autonomy.ask,
            f"No direct channel to {ctx.recipient_party}; the route is {route}",
            "no_direct_channel",
            "Outbound actions go only to parties the principal reaches directly.",
        )
    if ex in OUTBOUND_CLASSIFIED and ctx.content_class not in (ContentClass.none,):
        cc = (ctx.content_class or ContentClass.unknown).value
        why = (
            "the classifier could not confirm it commits nothing"
            if cc == "unknown"
            else f"its text reads as {cc.replace('_', ' ')}"
        )
        return out(
            Autonomy.ask,
            f"Outbound text needs a person: {why}",
            "content",
            "Outbound text that commits money, accepts terms, waives rights or gives notice needs a person.",
        )
    if record_bearing:
        why = (
            f"{kind.value} actions"
            if kind in mandate.record_bearing_kinds
            else f"messages to {role_class.replace('_', ' ')} parties"
        )
        return out(
            Autonomy.ask,
            f"Record-bearing: {why} always need a person",
            "record_bearing",
            f"Record-bearing: {', '.join(k.value for k in mandate.record_bearing_kinds)} actions, and messages to "
            f"{' or '.join(r.replace('_', ' ') for r in mandate.record_bearing_role_classes)} parties, "
            "always need a person.",
        )
    if not ctx.effect_allowed:
        return out(
            Autonomy.ask,
            ctx.effect_reason or "Effect on an item the principal does not control",
            "effect",
            "The agent may claim schedule effects only on items the principal controls.",
        )
    if kind in SPEND_KINDS:
        if not ctx.amount_ref_valid:
            return out(
                Autonomy.ask,
                "No structured amount: spend must cite a quote, PO line or fee in evidence",
                "amount",
                "Spend must cite a quote, PO line or fee on file.",
            )
        if kind == Kind.reserve and not (ctx.amount_cents or 0) and not ctx.cancellation_terms_ok:
            return out(
                Autonomy.ask,
                "Zero-deposit reservation without cancellation terms on file",
                "reservation_terms",
                "A reservation with no deposit needs cancellation terms on file.",
            )
    if ex == Executor.schedule_internal and not ctx.attendees_internal:
        return out(
            Autonomy.ask,
            "External attendee on an internal calendar hold",
            "attendees",
            "Internal holds are for the principal's own people only.",
        )

    # 3. The auto rules.
    direct = len(ctx.path) <= 1
    blocked: list[str] = []
    blocked_clause = ""
    for rule in mandate.auto:
        if kind not in rule.kinds or role_class not in rule.role_classes:
            continue
        if rule.channels is not None and channel != Channel.none and channel not in rule.channels:
            continue
        if rule.direct_only and not direct:
            blocked.append(
                f"it asks {ctx.asks_party} through {' → '.join(ctx.path)}, which the {mandate.preset} "
                f"mandate only allows with approval"
            )
            blocked_clause = blocked_clause or (
                f"{rule.name}: {rule.note} Under the {mandate.preset} mandate this covers direct "
                "counterparties only; asking a party further along the route needs a person."
            )
            continue
        if kind in SPEND_KINDS:
            if rule.spend is None:
                continue
            amount = ctx.amount_cents or 0
            if amount > rule.spend.per_action_cents:
                blocked.append(
                    f"{_money(amount)} exceeds the {_money(rule.spend.per_action_cents)} per-action limit"
                )
                blocked_clause = blocked_clause or _spend_clause(rule)
                continue
            if ctx.spent_today_cents + amount > rule.spend.per_day_cents:
                blocked.append(
                    f"{_money(amount)} would pass the {_money(rule.spend.per_day_cents)} daily limit "
                    f"({_money(ctx.spent_today_cents)} already committed today)"
                )
                blocked_clause = blocked_clause or _spend_clause(rule)
                continue
            return out(
                Autonomy.auto,
                f"{_money(amount)} is within the {_money(rule.spend.per_action_cents)} limit ({rule.name})",
                rule.name,
                _spend_clause(rule),
            )
        return out(
            Autonomy.auto,
            rule.note or f"Within authority ({rule.name})",
            rule.name,
            f"{rule.name}: {rule.note}",
        )

    # 4. Ask by default.
    if blocked:
        return out(Autonomy.ask, "Needs approval: " + "; ".join(blocked), "limit", blocked_clause)
    return out(
        Autonomy.ask,
        f"Not covered by the {mandate.preset} mandate's auto rules; routed to an approver",
        "default_ask",
        f"Ask by default: anything no clause of the {mandate.preset} mandate allows goes to a named approver.",
    )


def _spend_clause(rule: AutoRule) -> str:
    assert rule.spend is not None
    return (
        f"{rule.name}: {rule.note} Up to {_money(rule.spend.per_action_cents)} per action and "
        f"{_money(rule.spend.per_day_cents)} per day."
    )
