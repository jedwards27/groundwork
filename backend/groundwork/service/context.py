"""Resolve a RequestContext for the gateway from data: who the recipient really is, the path to the
party that must act, the amount on file, whether the effect is one the principal can claim, and the
classified text. Nothing here trusts a label the planner wrote."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from groundwork.core.profile import DomainProfile
from groundwork.policy import Mandate, RequestContext
from groundwork.policy.content_rules import classify_text, stricter
from groundwork.schemas.action import (
    CLASSIFIED_EXECUTORS,
    ContentClass,
    EffectKind,
    Executor,
    ProposedAction,
    RealizedBy,
    validate_params,
)
from groundwork.service import views
from groundwork.service.state import SiteState

RULES_CLASSIFIER = "rules-v1"


def classified_text(a: ProposedAction) -> str | None:
    if a.executor not in CLASSIFIED_EXECUTORS:
        return None
    p = a.params
    if a.executor == Executor.send_email:
        return f"Subject: {p.subject}\n\n{p.body}"
    if a.executor == Executor.request_meeting:
        return f"Meeting request: {p.agenda}"
    return f"Draft: {p.document_title}\n\n{p.scope or ''}"


def recipient_party(state: SiteState, ref: str | None) -> str | None:
    if not ref:
        return None
    person = next((p for p in state.people if p.key == ref), None)
    if person is not None:
        return person.party
    return ref if any(p.key == ref for p in state.parties) else None


def influence_chain(state: SiteState, party: str) -> list[str]:
    by_key = {p.key: p for p in state.parties}
    chain, cur, seen = [party], by_key[party].reached_via if party in by_key else None, {party}
    while cur and cur not in seen:
        chain.append(cur)
        seen.add(cur)
        cur = by_key[cur].reached_via
    return chain


def check_effect(state: SiteState, a: ProposedAction, actor: str | None) -> tuple[bool, str]:
    e = a.effect
    if e.kind == EffectKind.none:
        return True, ""
    items = {i.key: i for i in state.items}
    if not e.item or e.item not in items:
        return False, f"Effect names an unknown item ({e.item!r})"
    if e.days <= 0:
        return False, "Effect has no positive number of days"
    if e.kind in (EffectKind.lag_reduction, EffectKind.parallelize):
        if not e.pred or not any(ln.pred == e.pred and ln.succ == e.item for ln in state.links):
            return False, f"Effect names no existing link {e.pred!r} -> {e.item!r}"
    owner = items[e.item].owner
    if e.realized_by == RealizedBy.own_action:
        if owner != state.principal:
            return False, (f"Effect on an item the principal does not control: '{items[e.item].title}' belongs to "
                           f"{owner}; only that party (or one it answers to) can move it")
        return True, ""
    if actor is None or actor not in influence_chain(state, owner):
        return False, f"The party asked ({actor or 'none'}) cannot influence '{items[e.item].title}' (owned by {owner})"
    return True, ""


def response_lag_bd(state: SiteState, profile: DomainProfile, a: ProposedAction, path: list[str]) -> int:
    """Business days before a counterparty-dependent effect can land (assumptions in the profile)."""
    by_key = {p.key: p for p in state.parties}
    total = 0
    for hop in path:
        roles = by_key[hop].roles if hop in by_key else ()
        total += max((profile.response_lag_bd.get(r, 5) for r in roles), default=5)
    owners = [state.item(a.effect.item).owner] if a.effect.item else []
    if a.effect.pred:
        owners.append(state.item(a.effect.pred).owner)
    extra = 0
    for o in owners:
        roles = by_key[o].roles if o in by_key else ()
        extra = max([extra, *(profile.owner_extra_lag_bd.get(r, 0) for r in roles)])
    return total + extra


@dataclass(frozen=True)
class Resolved:
    ctx: RequestContext
    text: str | None
    lag_bd: int
    details: dict[str, Any]


def resolve(
    state: SiteState,
    profile: DomainProfile,
    mandate: Mandate,
    a: ProposedAction,
    *,
    spent_today_cents: int,
    model_class: ContentClass | None = None,
    model_name: str | None = None,
) -> Resolved:
    rp = recipient_party(state, a.recipient)
    parties = {p.key: p for p in state.parties}
    people = {p.key: p for p in state.people}
    missing = list(validate_params(a))
    asks = a.asks_party or rp
    if a.asks_party and a.asks_party not in parties:
        missing.append("asks_party (unknown party)")
        asks = rp
    path = tuple(views.path_from_principal(state, asks)) if asks else ()
    role_class = views.role_class(profile, parties[rp]) if rp else None
    evidence = {e.key: e for e in state.evidence}
    amount, amount_ok, cancel_ok = None, False, False
    if a.executor in (Executor.commit_spend, Executor.pay_invoice) and a.params.amount_ref in evidence:
        data = evidence[a.params.amount_ref].data
        if isinstance(data.get("amount_cents"), int):
            amount, amount_ok = int(data["amount_cents"]), True
    if a.executor == Executor.reserve_slot:
        if a.params.deposit_cents is not None:
            amount, amount_ok = a.params.deposit_cents, True
        ref = a.params.cancellation_terms_ref
        cancel_ok = bool(ref and ref in evidence and evidence[ref].data.get("cancellation_terms"))
    attendees_ok = True
    if a.executor == Executor.schedule_internal:
        attendees_ok = all(x in people and people[x].party == state.principal for x in (a.params.attendees or []))
    effect_ok, effect_reason = check_effect(state, a, asks)
    text = classified_text(a)
    cc: ContentClass | None = None
    classifier = ""
    if text is not None:
        cc = classify_text(text)
        classifier = RULES_CLASSIFIER
        if model_class is not None:
            cc = stricter(cc, model_class)
            classifier = f"{RULES_CLASSIFIER}+{model_name}"
    ctx = RequestContext(
        principal=state.principal, recipient_party=rp, recipient_known=rp is not None,
        recipient_direct=rp is not None and len(views.path_from_principal(state, rp)) == 1,
        recipient_role_class=role_class, asks_party=asks, path=path, content_class=cc, classifier=classifier,
        prior_thread=rp is not None and any(e.from_party == rp for e in state.events), amount_cents=amount,
        amount_ref_valid=amount_ok, cancellation_terms_ok=cancel_ok, attendees_internal=attendees_ok,
        effect_allowed=effect_ok, effect_reason=effect_reason, spent_today_cents=spent_today_cents,
        missing_params=tuple(missing),
    )
    lag = response_lag_bd(state, profile, a, list(path)) if a.effect.realized_by == RealizedBy.counterparty_response and a.effect.item else 0
    details = {"recipient_party": rp, "asks_party": asks, "path": list(path), "role_class": role_class,
               "amount_cents": amount, "effect_allowed": effect_ok, "effect_reason": effect_reason,
               "response_lag_bd": lag, "classifier": classifier, "content_class": cc.value if cc else None}
    return Resolved(ctx, text, lag, details)


def not_before(as_of: date, lag_bd: int, holidays: tuple[date, ...]) -> date:
    from groundwork.core import WorkCalendar

    return WorkCalendar.of(holidays).offset(as_of, lag_bd) if lag_bd else as_of + timedelta(days=0)
