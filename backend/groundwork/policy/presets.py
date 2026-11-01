"""Mandate presets, written over role classes so any vertical can use them.

Role classes: ``regulator`` (permit, grid and public bodies), ``counterparty_binding`` (parties whose
messages become part of a contract record), ``counterparty_routine`` (parties the principal works
with day to day), ``internal`` (the principal's own people and actions with no recipient).
"""

from __future__ import annotations

from datetime import date

from groundwork.policy.mandate import AskRouting, AutoRule, Mandate, SpendLimit
from groundwork.schemas.action import Channel, Kind

PRESETS = ("supervised", "standard", "autonomous")
INTERNAL_KINDS = [Kind.draft, Kind.schedule, Kind.record, Kind.escalate]


def build_preset(
    name: str,
    *,
    issuer: str,
    subject: str = "groundwork-agent",
    approvers: list[str],
    legal_approvers: list[str] | None = None,
    sla_hours: int = 24,
    owner_goals: list[str] | None = None,
    valid_from: date,
    version: int = 1,
    dry_run: bool = True,
) -> Mandate:
    if name not in PRESETS:
        raise ValueError(f"unknown preset {name!r}; choose one of {', '.join(PRESETS)}")
    auto = [
        AutoRule(
            name="internal",
            kinds=INTERNAL_KINDS,
            role_classes=["internal"],
            note="Drafting, scheduling the principal's own people, recording decisions, reporting.",
        )
    ]
    if name in ("standard", "autonomous"):
        direct_only = name == "standard"
        auto.append(
            AutoRule(
                name="routine_messages",
                kinds=[Kind.send, Kind.chase],
                role_classes=["counterparty_routine"],
                channels=[Channel.email, Channel.call],
                direct_only=direct_only,
                note="Status requests and coordination with routine counterparties; text must commit nothing.",
            )
        )
        limit = (
            SpendLimit(per_action_cents=5_000_000, per_day_cents=10_000_000)
            if name == "standard"
            else SpendLimit(per_action_cents=25_000_000, per_day_cents=50_000_000)
        )
        auto.append(
            AutoRule(
                name="routine_spend",
                kinds=[Kind.reserve, Kind.commit],
                role_classes=["counterparty_routine"],
                direct_only=True,
                spend=limit,
                note="Spend against a written quote or PO line, within the per-action and per-day limits.",
            )
        )
    return Mandate(
        id=f"mandate-{issuer}",
        version=version,
        preset=name,
        issuer=issuer,
        subject=subject,
        valid_from=valid_from,
        dry_run=dry_run,
        never=[Kind.pay, Kind.sign, Kind.delete],
        record_bearing_kinds=[Kind.legal, Kind.file, Kind.pay, Kind.sign, Kind.delete],
        record_bearing_role_classes=["regulator", "counterparty_binding"],
        auto=auto,
        ask=AskRouting(approvers=approvers, legal_approvers=legal_approvers or [], sla_hours=sla_hours),
        owner_goals=owner_goals or [],
    )
