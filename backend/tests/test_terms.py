"""Mandate terms: plain-language choices become a full mandate version. Pure; no database."""

from __future__ import annotations

from datetime import date

from groundwork.policy import build_preset
from groundwork.policy.terms import MandateTerms, build_from_terms, diff_lines
from groundwork.schemas.action import Kind

AS_OF = date(2026, 11, 2)
CURRENT = build_preset("standard", issuer="you", approvers=["me"], valid_from=AS_OF)


def test_auto_is_the_autonomous_template_and_versions_count_up():
    new, notes = build_from_terms(CURRENT, MandateTerms(template="auto"), valid_from=AS_OF)
    assert new.preset == "autonomous" and new.version == CURRENT.version + 1 and notes == []
    msgs = next(r for r in new.auto if r.name == "routine_messages")
    assert msgs.direct_only is False


def test_spend_limits_and_routing_override_the_template():
    terms = MandateTerms(template="standard", spend_per_action_usd=500, spend_per_day_usd=1500, messages_further_along=True)
    new, _ = build_from_terms(CURRENT, terms, valid_from=AS_OF)
    spend = next(r for r in new.auto if r.name == "routine_spend").spend
    assert spend is not None and (spend.per_action_cents, spend.per_day_cents) == (50_000, 150_000)
    assert next(r for r in new.auto if r.name == "routine_messages").direct_only is False


def test_spend_limits_on_a_template_without_spend_are_reported_not_invented():
    new, notes = build_from_terms(CURRENT, MandateTerms(template="supervised", spend_per_action_usd=500), valid_from=AS_OF)
    assert not any(r.name == "routine_spend" for r in new.auto) and "spend" in notes[0]


def test_also_never_removes_the_kind_from_every_allow_rule():
    new, _ = build_from_terms(CURRENT, MandateTerms(template="standard", also_never=[Kind.commit]), valid_from=AS_OF)
    assert Kind.commit in new.never and all(Kind.commit not in r.kinds for r in new.auto)


def test_pause_asks_and_revoke_denies_everything():
    paused, _ = build_from_terms(CURRENT, MandateTerms(template="auto", pause=True), valid_from=AS_OF)
    assert paused.preset == "supervised"
    revoked, notes = build_from_terms(CURRENT, MandateTerms(template="standard", revoke=True), valid_from=AS_OF)
    assert revoked.auto == [] and set(revoked.never) == set(Kind) and "Revoked" in notes[0]


def test_expiry_and_the_plain_language_diff():
    new, _ = build_from_terms(CURRENT, MandateTerms(template="standard", valid_until=date(2027, 1, 31)), valid_from=AS_OF)
    d = diff_lines(CURRENT, new)
    assert "Valid until 2027-01-31." in d["added"] and "Valid until no end date." in d["removed"]
