"""Mandate terms: the few things a person changes when they write a mandate in plain words.

Claude drafts terms from what a person says ("chase vendors weekly, ask me before anything over
$500, never sign"). ``build_from_terms`` turns them into a full mandate from a template. That step
is pure; issuing a version is a named person's confirmation (groundwork.service.mandates.issue).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from groundwork.policy.mandate import Mandate, SpendLimit
from groundwork.policy.presets import build_preset
from groundwork.schemas.action import Kind

# Display name -> preset name. "Auto" matches Claude Code's auto mode; the stored name is unchanged.
TEMPLATES: dict[str, str] = {"supervised": "supervised", "standard": "standard", "auto": "autonomous"}
TEMPLATE_LABEL: dict[str, str] = {v: k.capitalize() for k, v in TEMPLATES.items()}


class MandateTerms(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: Literal["supervised", "standard", "auto"] = Field(
        description="Supervised: only internal work runs alone. Standard: routine messages to direct "
        "counterparties and small spend run alone. Auto: the same, wider spend, and routine messages "
        "may ask parties further along the route."
    )
    spend_per_action_usd: float | None = Field(
        default=None, description="Most the agent may commit alone in one action (templates with spend only)."
    )
    spend_per_day_usd: float | None = Field(
        default=None, description="Most the agent may commit alone in one day (templates with spend only)."
    )
    messages_further_along: bool | None = Field(
        default=None,
        description="True lets routine messages ask a party further along the route; False keeps them to "
        "direct counterparties. Leave empty to keep the template's choice.",
    )
    also_never: list[Kind] = Field(
        default_factory=list, description="Kinds of action to add to the never list (pay, sign, delete are always there)."
    )
    approvers: list[str] | None = Field(default=None, description="Person keys who may approve asks.")
    legal_approvers: list[str] | None = Field(default=None, description="Person keys for legal drafts.")
    valid_until: date | None = Field(default=None, description="Last day the mandate is valid.")
    goals: list[str] | None = Field(default=None, description="The owner's goals, in plain words.")
    pause: bool = Field(default=False, description="Everything outside the team asks a person.")
    revoke: bool = Field(default=False, description="Nothing runs alone and nothing can be approved.")


def build_from_terms(current: Mandate, terms: MandateTerms, *, valid_from: date) -> tuple[Mandate, list[str]]:
    """A new version (current.version + 1) and any notes about terms the template could not use."""
    notes: list[str] = []
    preset = "supervised" if terms.pause else TEMPLATES[terms.template]
    new = build_preset(
        preset,
        issuer=current.issuer,
        subject=current.subject,
        approvers=terms.approvers if terms.approvers is not None else list(current.ask.approvers),
        legal_approvers=(
            terms.legal_approvers if terms.legal_approvers is not None else list(current.ask.legal_approvers)
        ),
        sla_hours=current.ask.sla_hours,
        owner_goals=terms.goals if terms.goals is not None else list(current.owner_goals),
        valid_from=valid_from,
        version=current.version + 1,
        dry_run=current.dry_run,
    )
    auto = []
    spend_given = terms.spend_per_action_usd is not None or terms.spend_per_day_usd is not None
    for rule in new.auto:
        if rule.name == "routine_spend" and spend_given and rule.spend is not None:
            per_action = (
                round(terms.spend_per_action_usd * 100)
                if terms.spend_per_action_usd is not None
                else rule.spend.per_action_cents
            )
            per_day = (
                round(terms.spend_per_day_usd * 100)
                if terms.spend_per_day_usd is not None
                else max(rule.spend.per_day_cents, per_action)
            )
            rule = rule.model_copy(update={"spend": SpendLimit(per_action_cents=per_action, per_day_cents=per_day)})
        if rule.name == "routine_messages" and terms.messages_further_along is not None:
            rule = rule.model_copy(update={"direct_only": not terms.messages_further_along})
        kinds = [k for k in rule.kinds if k not in terms.also_never]
        if kinds:
            auto.append(rule.model_copy(update={"kinds": kinds}))
    if spend_given and not any(r.name == "routine_spend" for r in auto):
        notes.append(f"The {TEMPLATE_LABEL.get(preset, preset)} template lets nothing spend money alone, so the spend limits were not used.")
    never = sorted(set(new.never) | set(terms.also_never), key=lambda k: list(Kind).index(k))
    if terms.revoke:
        auto, never = [], list(Kind)
        notes.append("Revoked: every action is denied until a person issues a new version.")
    if terms.pause:
        notes.append("Paused: everything outside the team asks a person until a new version is issued.")
    return new.model_copy(update={"auto": auto, "never": never, "valid_until": terms.valid_until}), notes


def diff_lines(old: Mandate, new: Mandate) -> dict[str, list[str]]:
    """Plain-language lines added and removed between two versions."""
    before, after = old.plain_lines(), new.plain_lines()
    if old.valid_until != new.valid_until:
        before.append(f"Valid until {old.valid_until or 'no end date'}.")
        after.append(f"Valid until {new.valid_until or 'no end date'}.")
    return {
        "added": [x for x in after if x not in before],
        "removed": [x for x in before if x not in after],
    }
