"""The mandate: a versioned, machine-readable grant of authority, stored and shown as JSON.

Three bands. ``never`` kinds are refused in every case. ``auto`` rules say what may run alone, for
which recipient role classes, on which channels, with which spend limits. Everything else is
``ask``, routed to named approvers. Record-bearing actions (by kind, or by the recipient's role
class) are never ``auto`` under any preset. Every mandate has an issuer, a subject, limits,
validity, and a version that every decision and approval cites.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from groundwork.schemas.action import Channel, Kind


class SpendLimit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    per_action_cents: int
    per_day_cents: int


class AutoRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    kinds: list[Kind]
    role_classes: list[str] = Field(
        description="Recipient role classes; 'internal' covers actions with no recipient"
    )
    channels: list[Channel] | None = None
    direct_only: bool = True  # the party that must act is the recipient itself, not someone further along
    spend: SpendLimit | None = None
    note: str = ""


class AskRouting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approvers: list[str]
    legal_approvers: list[str] = Field(default_factory=list)
    sla_hours: int = 24


class Mandate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: int
    preset: str
    issuer: str = Field(description="Party key of the principal granting authority")
    subject: str = Field(description="The agent the grant is for")
    valid_from: date
    valid_until: date | None = None
    dry_run: bool = True
    never: list[Kind]
    record_bearing_kinds: list[Kind]
    record_bearing_role_classes: list[str]
    auto: list[AutoRule]
    ask: AskRouting
    owner_goals: list[str] = Field(default_factory=list)

    def approvers_for(self, kind: Kind) -> list[str]:
        if kind == Kind.legal and self.ask.legal_approvers:
            return list(self.ask.legal_approvers)
        return list(self.ask.approvers)

    def plain_lines(self) -> list[str]:
        """The mandate in sentences, for prompts and the UI."""
        lines = [f"Never, in any case: {', '.join(k.value for k in self.never)}."]
        lines.append(
            "Always needs a person: anything record-bearing, meaning these kinds "
            f"({', '.join(k.value for k in self.record_bearing_kinds)}) or any message to a party whose role "
            f"class is {' or '.join(self.record_bearing_role_classes)}."
        )
        for r in self.auto:
            scope = ", ".join(r.role_classes)
            via = (
                "only when that recipient is the party that has to act"
                if r.direct_only
                else "including requests passed along to another party"
            )
            spend = (
                f"; up to ${r.spend.per_action_cents / 100:,.0f} per action and ${r.spend.per_day_cents / 100:,.0f} per day"
                if r.spend
                else ""
            )
            lines.append(
                f"May act alone: {', '.join(k.value for k in r.kinds)} to {scope} recipients, {via}{spend}."
            )
        lines.append(
            f"Everything else asks a named approver ({', '.join(self.ask.approvers)}; legal: "
            f"{', '.join(self.ask.legal_approvers) or 'same'}), answered within {self.ask.sla_hours} hours."
        )
        return lines
