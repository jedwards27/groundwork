"""Deterministic forecast: the schedule under an event's low, mid and high delays, plus the
reference set behind each item, shown with its size and provenance.

A reference class is *applied* to the estimate only when it has at least ``min_n`` single
observations of slip. Published ranges and secondary figures are shown, never applied. The
model never writes an estimate; it may only explain one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np

from groundwork.core.calendar import CalendarKind, WorkCalendar
from groundwork.core.cpm import Adjustment, Delay, Link, Schedule, Target, Task, schedule

Measure = Literal["duration", "slip"]


@dataclass(frozen=True)
class ReferenceRow:
    key: str
    label: str
    item_code: str
    measure: Measure
    value_days: float | None
    value_days_high: float | None = None  # set when the source gives a range
    attrs: Mapping[str, str] = field(default_factory=dict)
    source_url: str = ""
    provenance: str = "assumption_to_verify"
    note: str = ""

    @property
    def is_point(self) -> bool:
        return self.value_days is not None and self.value_days_high is None


@dataclass
class ReferenceSummary:
    item_code: str
    group: dict[str, str]
    rows: list[ReferenceRow]
    n_points: int
    median: float | None
    q1: float | None
    q3: float | None
    illustrative: bool
    applied: bool

    @property
    def headline(self) -> str:
        if not self.rows:
            return "no comparable items yet"
        if self.n_points == 0:
            ranges = [r for r in self.rows if r.value_days is not None]
            if ranges:
                r = ranges[0]
                hi = f"–{r.value_days_high:g}" if r.value_days_high is not None else ""
                return f"{len(self.rows)} source(s), no single observations; e.g. {r.value_days:g}{hi} days ({r.provenance})"
            return f"{len(self.rows)} source(s), none with a value yet"
        tag = "illustrative" if self.illustrative else "applied" if self.applied else "shown"
        return f"N={self.n_points}, median {self.median:g} d, IQR {self.q1:g}–{self.q3:g} d ({tag})"


def summarize(
    rows: Iterable[ReferenceRow],
    *,
    item_code: str,
    site_attrs: Mapping[str, str],
    key: Sequence[str],
    measure: Measure = "slip",
    min_n: int = 5,
) -> ReferenceSummary:
    group = {c: site_attrs.get(c, "") for c in key if c != "item_code"}
    matching = [
        r
        for r in rows
        if r.item_code == item_code and all(r.attrs.get(c, "") in ("", v) for c, v in group.items())
    ]
    points = [float(r.value_days) for r in matching if r.is_point and r.measure == measure]  # type: ignore[arg-type]
    if points:
        q1, med, q3 = (float(x) for x in np.percentile(points, [25, 50, 75]))
    else:
        q1 = med = q3 = None
    illustrative = len(points) < min_n
    return ReferenceSummary(
        item_code=item_code,
        group=group,
        rows=matching,
        n_points=len(points),
        median=med,
        q1=q1,
        q3=q3,
        illustrative=illustrative,
        applied=(not illustrative) and measure == "slip",
    )


@dataclass(frozen=True)
class RangedDelay:
    key: str
    low: int
    high: int
    calendar: CalendarKind = "calendar"
    label: str = ""
    mid: int | None = None  # the middle case, when it isn't halfway between low and high

    def at(self, which: Literal["low", "mid", "high"]) -> Delay:
        middle = round((self.low + self.high) / 2) if self.mid is None else self.mid
        days = {"low": self.low, "high": self.high, "mid": middle}[which]
        return Delay(self.key, days, self.calendar, self.label)


@dataclass
class Forecast:
    low: Schedule
    mid: Schedule
    high: Schedule
    reference: dict[str, ReferenceSummary]

    @property
    def target_range(self) -> tuple[date | None, date | None, date | None]:
        return self.low.target_finish, self.mid.target_finish, self.high.target_finish


def forecast(
    tasks: Sequence[Task],
    links: Sequence[Link],
    *,
    as_of: date,
    calendar: WorkCalendar,
    target: Target | None,
    delays: Sequence[RangedDelay] = (),
    adjustments: Sequence[Adjustment] = (),
    reference_rows: Sequence[ReferenceRow] = (),
    codes: Mapping[str, str] | None = None,
    site_attrs: Mapping[str, str] | None = None,
    reference_key: Sequence[str] = ("item_code",),
    min_n: int = 5,
) -> Forecast:
    codes = codes or {}
    site_attrs = site_attrs or {}
    reference: dict[str, ReferenceSummary] = {}
    applied: list[Delay] = []
    for t in tasks:
        code = codes.get(t.key)
        if not code:
            continue
        summary = summarize(
            reference_rows, item_code=code, site_attrs=site_attrs, key=reference_key, min_n=min_n
        )
        reference[t.key] = summary
        if summary.applied and summary.median and t.status != "done":
            applied.append(Delay(t.key, round(summary.median), "calendar", f"reference class {code}"))

    def run(which: Literal["low", "mid", "high"]) -> Schedule:
        return schedule(
            tasks,
            links,
            as_of=as_of,
            calendar=calendar,
            target=target,
            delays=[d.at(which) for d in delays] + applied,
            adjustments=adjustments,
        )

    return Forecast(low=run("low"), mid=run("mid"), high=run("high"), reference=reference)
