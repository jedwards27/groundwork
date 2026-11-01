"""Read models returned by the API (and published in /openapi.json for the web client)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class SourceRef(BaseModel):
    provenance: str
    source: str = ""
    note: str = ""


class FactView(BaseModel):
    label: str
    value: str
    provenance: str
    source: str = ""


class PartyView(BaseModel):
    key: str
    name: str
    roles: list[str]
    role_class: str
    level: str
    reached_via: str | None
    path_from_principal: list[str]
    provenance: str
    source: str = ""
    note: str = ""


class PersonView(BaseModel):
    key: str
    party: str
    name: str
    title: str
    approver: bool


class MilestoneView(BaseModel):
    kind: str
    label: str
    headline: str
    item: str
    target_date: date
    forecast_finish: date | None
    forecast_low: date | None = None
    forecast_high: date | None = None
    delta_days: int | None
    days_remaining: int | None
    binding_agreement: str = ""
    provenance: str
    source: str = ""
    note: str = ""


class ItemView(BaseModel):
    key: str
    code: str
    title: str
    kind: str
    owner: str
    performer: str
    lane: str
    status: str
    planned_start: date | None
    planned_finish: date
    actual_finish: date | None
    calendar: str
    provenance: str
    source: str
    notes: str
    # computed
    early_start: date
    early_finish: date
    late_finish: date | None
    total_float: int | None
    critical: bool
    near_critical: bool
    on_target_path: bool
    finish_shift_days: int
    drivers: list[str]


class LinkView(BaseModel):
    pred: str
    succ: str
    kind: str
    lag: int
    lag_calendar: str


class LaneView(BaseModel):
    key: str
    label: str
    role: str


class CalendarLossView(BaseModel):
    pred: str | None
    succ: str
    holidays: list[date]
    sentence: str


class ImpactView(BaseModel):
    item: str
    low: int
    high: int
    calendar: str
    leg: str
    owner: str


class EventView(BaseModel):
    key: str
    kind: str
    title: str
    from_party: str
    forwarded_from: str | None
    received_at: datetime
    body: str
    links: list[str]
    impacts: list[ImpactView]
    status: str
    provenance: str
    source: str = ""
    note: str = ""


class ChainView(BaseModel):
    site: str
    as_of: date
    lanes: list[LaneView]
    items: list[ItemView]
    links: list[LinkView]
    milestone: MilestoneView
    gate: str | None
    critical_path: list[str]
    near_critical: list[str]
    min_float: int | None
    calendar_losses: list[CalendarLossView]
    applied_events: list[str]
    scenario_events: list[str]


class ReferenceRowView(BaseModel):
    key: str
    label: str
    measure: str
    value_days: float | None
    value_days_high: float | None
    source_url: str
    provenance: str
    note: str


class ReferenceView(BaseModel):
    item_code: str
    group: dict[str, str]
    n_points: int
    median: float | None
    q1: float | None
    q3: float | None
    illustrative: bool
    applied: bool
    headline: str
    rows: list[ReferenceRowView]


class ItemForecastView(BaseModel):
    key: str
    title: str
    planned_finish: date
    expected_finish: date
    low_finish: date
    high_finish: date
    reason: str
    reference: ReferenceView | None


class ForecastView(BaseModel):
    site: str
    as_of: date
    milestone: MilestoneView
    items: list[ItemForecastView]
    applied_events: list[str]
    scenario_events: list[str]
    method: str


class SiteView(BaseModel):
    key: str
    name: str
    location: str
    profile: str
    as_of: date
    principal: str
    asset: str
    capacity_mw: float | None
    attrs: dict[str, str]
    calendar_note: str
    holidays: list[date]
    facts: list[FactView]
    parties: list[PartyView]
    people: list[PersonView]
    milestones: list[MilestoneView]
    glossary: dict[str, str]


class SiteSummary(BaseModel):
    key: str
    name: str
    location: str
    asset: str
    milestone: MilestoneView
    gate: str | None
    gate_title: str | None


class RunView(BaseModel):
    id: str
    site: str
    event: str
    status: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    summary: dict[str, Any] | None
