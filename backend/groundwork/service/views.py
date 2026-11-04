"""Compute read models from a SiteState. Pure functions; no storage, no model calls."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import cast

from groundwork.core import Adjustment, Link, Schedule, Target, Task, WorkCalendar
from groundwork.core.forecast import Forecast, Measure, RangedDelay, ReferenceRow, forecast
from groundwork.core.profile import DomainProfile
from groundwork.domain import get_profile
from groundwork.ingest.site_loader import CLOSED, EventRow, ItemRow, MilestoneRow, PartyRow
from groundwork.schemas.views import (
    CalendarLossView,
    ChainView,
    EventView,
    FactView,
    ForecastView,
    ImpactView,
    ItemForecastView,
    ItemView,
    LaneView,
    LinkView,
    MilestoneView,
    PartyView,
    PersonView,
    ReferenceRowView,
    ReferenceView,
    SiteSummary,
    SiteView,
)
from groundwork.service.state import SiteState

ROLE_CLASS_ORDER = ("regulator", "counterparty_binding", "counterparty_routine", "internal")
LANE_ROLE_ORDER = (
    "to",
    "iso",
    "regulator",
    "agency",
    "ahj",
    "vendor",
    "epc",
    "landlord",
    "developer",
    "lender",
    "lessee",
    "offtaker",
    "investor",
    "operator",
    "ie",
    "community",
    "end_user",
)

METHOD = (
    "Critical path from the as-of date on the site's working calendar (business-day lags skip weekends and "
    "listed holidays). Applied events add their delays at the midpoint of their range; the low and high ends "
    "give the range. A reference class adjusts an estimate only when it has at least five single "
    "observations; published ranges and secondary figures are shown, never applied. Every number here is "
    "computed by code and reproducible; a model may explain a forecast but never writes one."
)


# --- parties -----------------------------------------------------------------------------------
def role_class(profile: DomainProfile, party: PartyRow) -> str:
    classes = [profile.role_class.get(r, "counterparty_routine") for r in party.roles]
    return min(classes, key=ROLE_CLASS_ORDER.index) if classes else "counterparty_routine"


def path_from_principal(state: SiteState, party_key: str) -> list[str]:
    """Hops from the principal to a party, following ``reached_via``. [] for the principal itself."""
    if party_key == state.principal:
        return []
    by_key = {p.key: p for p in state.parties}
    chain = [party_key]
    seen = {party_key}
    cur = by_key[party_key].reached_via
    while cur and cur not in seen:
        chain.append(cur)
        seen.add(cur)
        cur = by_key[cur].reached_via
    return list(reversed(chain))


def party_views(state: SiteState, profile: DomainProfile) -> list[PartyView]:
    return [
        PartyView(
            key=p.key,
            name=p.name,
            roles=list(p.roles),
            role_class=role_class(profile, p),
            level=p.level,
            reached_via=p.reached_via,
            path_from_principal=path_from_principal(state, p.key),
            provenance=p.provenance,
            source=p.source,
            note=p.note,
        )
        for p in state.parties
    ]


# --- engine inputs -----------------------------------------------------------------------------
def _task(i: ItemRow, as_of: date) -> Task:
    if i.status == "cancelled":
        # Out of scope: nothing waits on it, so the engine sees it as finished by today at the latest.
        start = i.planned_start or i.planned_finish
        return Task(i.key, "done", i.planned_finish, i.planned_start, i.calendar, min(start, as_of))  # type: ignore[arg-type]
    return Task(i.key, i.status, i.planned_finish, i.planned_start, i.calendar, i.actual_finish)  # type: ignore[arg-type]


def engine_inputs(state: SiteState) -> tuple[list[Task], list[Link], WorkCalendar, dict[str, str]]:
    tasks = [_task(i, state.as_of) for i in state.items]
    links = [Link(ln.pred, ln.succ, ln.kind, ln.lag, ln.lag_calendar) for ln in state.links]  # type: ignore[arg-type]
    return tasks, links, WorkCalendar.of(state.holidays), {i.key: i.code for i in state.items}


def event_delays(events: Sequence[EventRow]) -> list[RangedDelay]:
    return [
        RangedDelay(imp.item, imp.low, imp.high, imp.calendar, imp.leg)  # type: ignore[arg-type]
        for e in events
        for imp in e.impacts
    ]


def stale(state: SiteState) -> dict[str, int]:
    """Open steps past their planned finish with no message about them since: key -> days past."""
    heard: dict[str, date] = {}
    for e in state.events:
        if state.event_status.get(e.key) == "moved":
            continue
        for k in {*e.links, *(imp.item for imp in e.impacts)}:
            heard[k] = max(heard.get(k, date.min), e.received_at.date())
    return {
        i.key: (state.as_of - i.planned_finish).days
        for i in state.items
        if i.status not in CLOSED and i.planned_finish < state.as_of and heard.get(i.key, date.min) < i.planned_finish
    }


def stale_delays(state: SiteState) -> list[RangedDelay]:
    """The late case for a step past plan with no word: it slips as much again. The middle case
    leaves it starting today, which the engine already does."""
    return [RangedDelay(k, 0, days, "calendar", "past plan with no word", mid=0) for k, days in stale(state).items()]


def reference_rows(state: SiteState) -> list[ReferenceRow]:
    return [
        ReferenceRow(
            r.key,
            r.label,
            r.item_code,
            cast(Measure, r.measure),
            r.value_days,
            r.value_days_high,
            r.attrs,
            r.source_url,
            r.provenance,
            r.note,
        )
        for r in state.reference_rows
    ]


def primary_milestone(state: SiteState) -> MilestoneRow:
    return state.milestones[0]


def run_forecast(
    state: SiteState,
    *,
    scenario: Sequence[str] = (),
    adjustments: Sequence[Adjustment] = (),
    milestone: MilestoneRow | None = None,
    include_applied: bool = True,
) -> Forecast:
    profile = get_profile(state.profile)
    tasks, links, cal, codes = engine_inputs(state)
    ms = milestone or primary_milestone(state)
    events = (state.applied_events() if include_applied else []) + [
        state.event(k) for k in scenario if state.event_status.get(k) != "applied" or not include_applied
    ]
    return forecast(
        tasks,
        links,
        as_of=state.as_of,
        calendar=cal,
        target=Target(ms.item, ms.target_date),
        delays=event_delays(events) + stale_delays(state),
        adjustments=adjustments,
        reference_rows=reference_rows(state),
        codes=codes,
        site_attrs=state.attrs,
        reference_key=profile.reference_key,
    )


def _headline(state: SiteState, profile: DomainProfile, ms: MilestoneRow) -> str:
    tmpl = profile.milestone_headline.get(ms.kind, "{asset} milestone in")
    return tmpl.format(asset=state.asset_name)


def milestone_view(state: SiteState, profile: DomainProfile, ms: MilestoneRow, f: Forecast) -> MilestoneView:
    fin = f.mid.target_finish
    return MilestoneView(
        kind=ms.kind,
        label=ms.label,
        headline=_headline(state, profile, ms),
        item=ms.item,
        target_date=ms.target_date,
        forecast_finish=fin,
        forecast_low=f.low.target_finish,
        forecast_high=f.high.target_finish,
        delta_days=f.mid.target_delta_days,
        days_remaining=(fin - state.as_of).days if fin else None,
        binding_agreement=ms.binding_agreement,
        provenance=ms.provenance,
        source=ms.source,
        note=ms.note,
    )


# --- chain -------------------------------------------------------------------------------------
def lanes(state: SiteState) -> tuple[list[LaneView], dict[str, str]]:
    """One lane per performing party, except vendors, which share a lane."""
    by_key = {p.key: p for p in state.parties}
    lane_of: dict[str, str] = {}
    lane_meta: dict[str, tuple[str, str]] = {}
    for i in state.items:
        p = by_key[i.performer]
        primary = min(p.roles, key=lambda r: LANE_ROLE_ORDER.index(r) if r in LANE_ROLE_ORDER else 99)
        if primary == "vendor":
            lane_of[i.key] = "vendors"
            lane_meta["vendors"] = ("Equipment vendors", "vendor")
        else:
            lane_of[i.key] = p.key
            lane_meta[p.key] = (p.name, primary)
    order = sorted(
        lane_meta,
        key=lambda k: (
            LANE_ROLE_ORDER.index(lane_meta[k][1]) if lane_meta[k][1] in LANE_ROLE_ORDER else 99,
            k,
        ),
    )
    return [LaneView(key=k, label=lane_meta[k][0], role=lane_meta[k][1]) for k in order], lane_of


def _loss_sentence(state: SiteState, pred: str | None, succ: str, holidays: Sequence[date]) -> str:
    days = ", ".join(h.strftime("%b %-d") for h in holidays)
    n = len(holidays)
    noun = "holiday" if n == 1 else "holidays"
    if pred is None:
        where = f"inside '{state.item(succ).title}'"
    else:
        where = f"inside the wait between '{state.item(pred).title}' and '{state.item(succ).title}'"
    verb, effect = ("falls", "it pushes") if n == 1 else ("fall", "each pushes")
    return f"{n} {noun} ({days}) {verb} {where} on the critical path; {effect} the milestone one working day."


def chain_view(
    state: SiteState, *, scenario: Sequence[str] = (), adjustments: Sequence[Adjustment] = ()
) -> ChainView:
    profile = get_profile(state.profile)
    f = run_forecast(state, scenario=scenario, adjustments=adjustments)
    s: Schedule = f.mid
    lane_list, lane_of = lanes(state)
    items: list[ItemView] = []
    for i in state.items:
        r = s.tasks[i.key]
        items.append(
            ItemView(
                key=i.key,
                code=i.code,
                title=i.title,
                kind=i.kind,
                owner=i.owner,
                performer=i.performer,
                lane=lane_of[i.key],
                status=i.status,
                planned_start=i.planned_start,
                planned_finish=i.planned_finish,
                actual_finish=i.actual_finish,
                calendar=i.calendar,
                provenance=i.provenance,
                source=i.source,
                notes=i.notes,
                estimated=i.estimated,
                early_start=r.early_start,
                early_finish=r.early_finish,
                late_finish=r.late_finish,
                total_float=r.total_float,
                critical=r.critical,
                near_critical=r.near_critical,
                on_target_path=r.on_target_path,
                finish_shift_days=r.finish_shift_days,
                drivers=r.drivers,
            )
        )
    ms = primary_milestone(state)
    return ChainView(
        site=state.key,
        as_of=state.as_of,
        lanes=lane_list,
        items=items,
        links=[
            LinkView(pred=ln.pred, succ=ln.succ, kind=ln.kind, lag=ln.lag, lag_calendar=ln.lag_calendar)
            for ln in state.links
        ],
        milestone=milestone_view(state, profile, ms, f),
        gate=s.gate,
        critical_path=s.critical_path,
        near_critical=s.near_critical,
        min_float=s.min_float,
        calendar_losses=[
            CalendarLossView(
                pred=c.pred,
                succ=c.succ,
                holidays=list(c.holidays),
                sentence=_loss_sentence(state, c.pred, c.succ, c.holidays),
            )
            for c in s.calendar_losses
        ],
        applied_events=[e.key for e in state.applied_events()],
        scenario_events=list(scenario),
        stale=stale(state),
    )


# --- forecast ----------------------------------------------------------------------------------
def _reason(state: SiteState, f: Forecast, key: str, events: Sequence[EventRow]) -> str:
    item = state.item(key)
    r = f.mid.tasks[key]
    if item.status == "done":
        return f"Done on {item.actual_finish:%b %-d, %Y}."
    legs = [(e, imp) for e in events for imp in e.impacts if imp.item == key]
    if legs:
        parts = "; ".join(f"{imp.leg} (+{imp.low} to {imp.high} days)" for _, imp in legs)
        return f"'{legs[0][0].title}' adds delay here: {parts}."
    if r.finish_shift_days > 0 and r.drivers:
        names = ", ".join(f"'{state.item(d).title}'" for d in r.drivers)
        return f"Pushed {r.finish_shift_days} days by {names}."
    if r.finish_shift_days > 0:
        return f"Forecast {r.finish_shift_days} days after plan because remaining work cannot start before the as-of date."
    return "On plan: no applied event touches this item or anything upstream of it."


def _reference_view(summary) -> ReferenceView:  # type: ignore[no-untyped-def]
    return ReferenceView(
        item_code=summary.item_code,
        group=summary.group,
        n_points=summary.n_points,
        median=summary.median,
        q1=summary.q1,
        q3=summary.q3,
        illustrative=summary.illustrative,
        applied=summary.applied,
        headline=summary.headline,
        rows=[
            ReferenceRowView(
                key=x.key,
                label=x.label,
                measure=x.measure,
                value_days=x.value_days,
                value_days_high=x.value_days_high,
                source_url=x.source_url,
                provenance=x.provenance,
                note=x.note,
            )
            for x in summary.rows
        ],
    )


def forecast_view(state: SiteState, *, scenario: Sequence[str] = ()) -> ForecastView:
    profile = get_profile(state.profile)
    f = run_forecast(state, scenario=scenario)
    events = state.applied_events() + [state.event(k) for k in scenario]
    items = []
    for i in state.items:
        items.append(
            ItemForecastView(
                key=i.key,
                title=i.title,
                planned_finish=i.actual_finish or i.planned_finish,
                expected_finish=f.mid.tasks[i.key].early_finish,
                low_finish=f.low.tasks[i.key].early_finish,
                high_finish=f.high.tasks[i.key].early_finish,
                reason=_reason(state, f, i.key, events),
                reference=_reference_view(f.reference[i.key]) if i.key in f.reference else None,
            )
        )
    return ForecastView(
        site=state.key,
        as_of=state.as_of,
        milestone=milestone_view(state, profile, primary_milestone(state), f),
        items=items,
        applied_events=[e.key for e in state.applied_events()],
        scenario_events=list(scenario),
        method=METHOD,
    )


# --- site ----------------------------------------------------------------------------------------
def site_view(state: SiteState) -> SiteView:
    profile = get_profile(state.profile)
    milestones = []
    for ms in state.milestones:
        milestones.append(milestone_view(state, profile, ms, run_forecast(state, milestone=ms)))
    return SiteView(
        key=state.key,
        name=state.name,
        location=state.location,
        profile=state.profile,
        as_of=state.as_of,
        principal=state.principal,
        asset=state.asset_name,
        capacity_mw=state.capacity_mw,
        attrs=state.attrs,
        calendar_note=state.calendar_note,
        holidays=list(state.holidays),
        facts=[
            FactView(label=x.label, value=x.value, provenance=x.provenance, source=x.source)
            for x in state.facts
        ],
        parties=party_views(state, profile),
        people=[
            PersonView(key=x.key, party=x.party, name=x.name, title=x.title, approver=x.approver)
            for x in state.people
        ],
        milestones=milestones,
        glossary=dict(profile.glossary),
        archived_at=state.archived_at,
    )


def site_summary(state: SiteState) -> SiteSummary:
    c = chain_view(state)
    return SiteSummary(
        key=state.key,
        name=state.name,
        location=state.location,
        asset=state.asset_name,
        milestone=c.milestone,
        gate=c.gate,
        gate_title=state.item(c.gate).title if c.gate else None,
    )


def event_view(state: SiteState, e: EventRow) -> EventView:
    return EventView(
        key=e.key,
        kind=e.kind,
        title=e.title,
        from_party=e.from_party,
        forwarded_from=e.forwarded_from,
        received_at=e.received_at,
        body=e.body,
        links=list(e.links),
        impacts=[
            ImpactView(item=i.item, low=i.low, high=i.high, calendar=i.calendar, leg=i.leg, owner=i.owner)
            for i in e.impacts
        ],
        status=state.event_status.get(e.key, "available"),
        provenance=e.provenance,
        source=e.source,
        note=e.note,
        scripted=e.scripted,
    )
