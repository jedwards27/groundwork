"""Table-driven gateway tests: (executor x recipient role class x preset) -> decision, plus explicit
rows for every rule that forces a person. The gateway decides on context resolved from data;
nothing here depends on labels a planner wrote except the proposed autonomy (used only for delta)."""

from __future__ import annotations

import itertools
from datetime import date

import pytest

from groundwork.policy import RequestContext, build_preset, decide
from groundwork.schemas import ActionParams, Autonomy, ContentClass, Effect, Executor, Kind, ProposedAction

PRESETS = {
    name: build_preset(
        name,
        issuer="principal",
        approvers=["approver"],
        legal_approvers=["counsel"],
        valid_from=date(2026, 11, 2),
    )
    for name in ("supervised", "standard", "autonomous")
}

FULL_PARAMS = ActionParams(
    subject="Status",
    body="Please share the latest status report.",
    agenda="Weekly status",
    attendees=["me"],
    window_start="2026-11-10",
    amount_ref="quote-1",
    scope="Review",
    document_title="Status memo",
    package_title="Package",
    summary="Summary",
    decision="Re-plan",
    record_ref="r1",
    deposit_cents=0,
)


def action(executor: Executor, proposed: Autonomy = Autonomy.auto, **kw) -> ProposedAction:
    return ProposedAction(
        ref="a1",
        title="t",
        executor=executor,
        recipient=kw.pop("recipient", "party-x"),
        params=kw.pop("params", FULL_PARAMS),
        effect=kw.pop("effect", Effect()),
        proposed_autonomy=proposed,
        rationale="r",
        **kw,
    )


def ctx(role_class: str | None, **kw) -> RequestContext:
    base = dict(
        principal="principal",
        recipient_party="party-x" if role_class else None,
        recipient_known=role_class is not None,
        recipient_direct=role_class is not None,
        recipient_role_class=role_class,
        asks_party="party-x" if role_class else None,
        path=("party-x",) if role_class else (),
        content_class=ContentClass.none,
        amount_cents=1_850_000,
        amount_ref_valid=True,
        cancellation_terms_ok=True,
    )
    base.update(kw)
    return RequestContext(**base)


# --- the declarative table ---------------------------------------------------------------------
NEVER = {Executor.pay_invoice, Executor.sign_document, Executor.delete_record}
INTERNAL = {
    Executor.draft_document,
    Executor.schedule_internal,
    Executor.escalate_to_owner,
    Executor.record_decision,
}
MESSAGES = {Executor.send_email, Executor.request_meeting}
SPEND = {Executor.reserve_slot, Executor.commit_spend}
ROLE_CLASSES = ["regulator", "counterparty_binding", "counterparty_routine", "internal"]


def expected(executor: Executor, role_class: str, preset: str) -> Autonomy:
    if executor in NEVER:
        return Autonomy.refuse
    if executor in INTERNAL:
        return Autonomy.auto if role_class == "internal" else Autonomy.ask
    if executor == Executor.file_package:
        return Autonomy.ask  # file is record-bearing by kind
    if role_class in ("regulator", "counterparty_binding"):
        return Autonomy.ask  # record-bearing by recipient
    if role_class == "internal":
        return Autonomy.ask  # outbound with no known recipient
    if executor in MESSAGES or executor in SPEND:
        return Autonomy.ask if preset == "supervised" else Autonomy.auto
    raise AssertionError(executor)


TABLE = list(itertools.product(list(Executor), ROLE_CLASSES, list(PRESETS)))


@pytest.mark.parametrize(
    ("executor", "role_class", "preset"), TABLE, ids=[f"{e.value}-{r}-{p}" for e, r, p in TABLE]
)
def test_table(executor, role_class, preset):
    internal = executor in INTERNAL or executor in NEVER - {Executor.pay_invoice, Executor.sign_document}
    if role_class == "internal":
        a = action(executor, recipient=None)
        c = ctx(None, attendees_internal=True)
    else:
        a = action(executor)
        c = ctx(role_class)
    if internal and role_class != "internal":
        # Internal executors addressed outward: treat the recipient as an external attendee.
        c = ctx(
            role_class,
            attendees_internal=False,
            effect_allowed=executor != Executor.record_decision,
            content_class=ContentClass.legal_notice
            if executor == Executor.draft_document
            else ContentClass.none,
        )
    d = decide(a, c, PRESETS[preset])
    assert d.decision == expected(executor, role_class, preset), d.reason


# --- explicit rows -----------------------------------------------------------------------------
STD = PRESETS["standard"]
AUTO = PRESETS["autonomous"]


def test_never_list_holds_with_incomplete_context():
    bare = RequestContext(principal="principal")
    for ex in NEVER:
        d = decide(action(ex, recipient=None, params=ActionParams()), bare, AUTO)
        assert d.decision == Autonomy.refuse and d.rule == "never"


def test_never_proposal_is_flagged_as_over_reach():
    d = decide(action(Executor.pay_invoice, Autonomy.auto), ctx("counterparty_routine"), AUTO)
    assert d.decision == Autonomy.refuse and d.delta == "over_reach" and d.held


def test_proposing_refuse_on_never_matches():
    d = decide(action(Executor.pay_invoice, Autonomy.refuse), ctx("counterparty_routine"), STD)
    assert d.delta == "match"


def test_unknown_recipient_asks():
    d = decide(action(Executor.send_email), ctx("counterparty_routine", recipient_known=False), AUTO)
    assert (d.decision, d.rule) == (Autonomy.ask, "unknown_recipient")


def test_no_direct_channel_asks():
    c = ctx("counterparty_routine", recipient_direct=False, path=("lessee-x", "party-x"))
    d = decide(action(Executor.send_email), c, AUTO)
    assert (d.decision, d.rule) == (Autonomy.ask, "no_direct_channel")


def test_request_passed_along_needs_approval_under_standard_not_autonomous():
    c = ctx("counterparty_routine", asks_party="far-party", path=("party-x", "far-party"))
    assert decide(action(Executor.send_email), c, STD).decision == Autonomy.ask
    assert decide(action(Executor.send_email), c, AUTO).decision == Autonomy.auto


@pytest.mark.parametrize(
    "cc",
    [
        ContentClass.commits_money,
        ContentClass.accepts_terms,
        ContentClass.waives_rights,
        ContentClass.legal_notice,
        ContentClass.unknown,
    ],
)
def test_outbound_text_classes_force_a_person(cc):
    d = decide(action(Executor.send_email), ctx("counterparty_routine", content_class=cc), AUTO)
    assert (d.decision, d.rule) == (Autonomy.ask, "content")


def test_mislabel_attempt_benign_executor_harmful_text():
    # The planner calls it a routine email; the body commits money. Kind comes from the executor,
    # and the classifier class decides.
    a = action(
        Executor.send_email, params=FULL_PARAMS.model_copy(update={"body": "We will pay the $250,000 fee."})
    )
    d = decide(a, ctx("counterparty_routine", content_class=ContentClass.commits_money), AUTO)
    assert d.decision == Autonomy.ask and d.delta == "over_reach"


def test_legal_draft_is_kind_legal_and_asks():
    d = decide(
        action(Executor.draft_document, recipient=None),
        ctx(None, content_class=ContentClass.legal_notice),
        AUTO,
    )
    assert d.kind == Kind.legal and d.decision == Autonomy.ask and d.rule == "record_bearing"


def test_plain_draft_runs_alone_everywhere():
    for m in PRESETS.values():
        assert decide(action(Executor.draft_document, recipient=None), ctx(None), m).decision == Autonomy.auto


def test_chase_versus_send_comes_from_prior_thread():
    assert (
        decide(action(Executor.send_email), ctx("counterparty_routine", prior_thread=True), STD).kind
        == Kind.chase
    )
    assert decide(action(Executor.send_email), ctx("counterparty_routine"), STD).kind == Kind.send


def test_effect_on_uncontrolled_item_asks():
    a = action(
        Executor.record_decision, recipient=None, effect=Effect(kind="duration_reduction", item="x", days=5)
    )
    d = decide(
        a,
        ctx(None, effect_allowed=False, effect_reason="Effect on an item the principal does not control"),
        AUTO,
    )
    assert (d.decision, d.rule) == (Autonomy.ask, "effect")


def test_spend_without_structured_amount_asks():
    d = decide(action(Executor.commit_spend), ctx("counterparty_routine", amount_ref_valid=False), AUTO)
    assert (d.decision, d.rule) == (Autonomy.ask, "amount")


def test_zero_deposit_reservation_without_terms_asks():
    c = ctx("counterparty_routine", amount_cents=0, cancellation_terms_ok=False)
    d = decide(action(Executor.reserve_slot), c, AUTO)
    assert (d.decision, d.rule) == (Autonomy.ask, "reservation_terms")


def test_external_attendee_on_internal_hold_asks():
    d = decide(action(Executor.schedule_internal, recipient=None), ctx(None, attendees_internal=False), AUTO)
    assert (d.decision, d.rule) == (Autonomy.ask, "attendees")


@pytest.mark.parametrize(
    ("amount", "spent", "preset", "decision"),
    [
        (5_000_000, 0, "standard", Autonomy.auto),  # exactly at the per-action limit
        (5_000_001, 0, "standard", Autonomy.ask),  # one cent over
        (4_000_000, 7_000_000, "standard", Autonomy.ask),  # daily limit would be passed
        (4_000_000, 6_000_000, "standard", Autonomy.auto),  # daily limit exactly met
        (25_000_000, 0, "autonomous", Autonomy.auto),
        (25_000_001, 0, "autonomous", Autonomy.ask),
        (100, 0, "supervised", Autonomy.ask),  # supervised never spends alone
    ],
)
def test_spend_limits(amount, spent, preset, decision):
    c = ctx("counterparty_routine", amount_cents=amount, spent_today_cents=spent)
    d = decide(action(Executor.commit_spend), c, PRESETS[preset])
    assert d.decision == decision, d.reason


def test_incomplete_params_ask():
    d = decide(action(Executor.send_email), ctx("counterparty_routine", missing_params=("body",)), AUTO)
    assert (d.decision, d.rule) == (Autonomy.ask, "incomplete")


def test_over_caution_is_recorded():
    d = decide(action(Executor.record_decision, Autonomy.ask, recipient=None), ctx(None), STD)
    assert d.decision == Autonomy.auto and d.delta == "over_caution"
