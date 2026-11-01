"""SiteState: everything the engine and the views need about one site, independent of storage."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from groundwork.ingest.site_loader import (
    EventRow,
    FactRow,
    ItemRow,
    LinkRow,
    MilestoneRow,
    PartyRow,
    PersonRow,
    ReferenceRowIn,
    SiteBundle,
)


@dataclass(frozen=True)
class EvidenceLite:
    key: str
    kind: str
    title: str
    party: str | None
    data: dict[str, Any]
    provenance: str
    source: str


@dataclass
class SiteState:
    key: str
    name: str
    location: str
    profile: str
    as_of: date
    principal: str
    attrs: dict[str, str]
    holidays: tuple[date, ...]
    calendar_note: str
    asset_key: str
    asset_name: str
    capacity_mw: float | None
    milestones: list[MilestoneRow]
    parties: list[PartyRow]
    people: list[PersonRow]
    items: list[ItemRow]
    links: list[LinkRow]
    events: list[EventRow]
    event_status: dict[str, str]
    evidence: list[EvidenceLite]
    facts: list[FactRow]
    reference_rows: list[ReferenceRowIn]
    timezone: str = "UTC"
    org_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    ids: dict[str, uuid.UUID] = field(default_factory=dict)  # "party:key" / "item:key" / "person:key" -> id

    @classmethod
    def from_bundle(cls, b: SiteBundle) -> SiteState:
        return cls(
            key=b.site_key,
            name=b.site_name,
            location=b.location,
            profile=b.profile,
            as_of=b.as_of,
            principal=b.principal,
            attrs=dict(b.attrs),
            holidays=b.holidays,
            calendar_note=b.calendar_note,
            asset_key=b.asset_key,
            asset_name=b.asset_name,
            capacity_mw=b.capacity_mw,
            milestones=list(b.milestones),
            parties=list(b.parties),
            people=list(b.people),
            items=list(b.items),
            links=list(b.links),
            events=list(b.events),
            event_status={e.key: "available" for e in b.events},
            evidence=[
                EvidenceLite(e.key, e.kind, e.title, e.party, e.data, e.provenance, e.source)
                for e in b.evidence
            ],
            facts=list(b.facts),
            reference_rows=list(b.reference_rows),
            timezone=b.timezone,
        )

    def item(self, key: str) -> ItemRow:
        return next(i for i in self.items if i.key == key)

    def party(self, key: str) -> PartyRow:
        return next(p for p in self.parties if p.key == key)

    def event(self, key: str) -> EventRow:
        return next(e for e in self.events if e.key == key)

    def applied_events(self) -> list[EventRow]:
        return [e for e in self.events if self.event_status.get(e.key) == "applied"]
