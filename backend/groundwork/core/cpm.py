"""Critical path method over items and links, computed from an as-of date toward one target.

Vocabulary (generic on purpose):

* **Task**: a dated item of work or a dated point (a point has no planned start).
* **Link**: a dependency; FS (finish-to-start), SS (start-to-start) or FF (finish-to-finish),
  with a lag in business or calendar days.
* **Delay**: extra days an event adds to a task (from evidence, e.g. "re-review takes 6 weeks").
* **Adjustment**: a change a mitigation would make (shorter duration, shorter lag, overlap,
  earliest-possible date, or an added predecessor).
* **Target**: the task whose finish is the milestone being protected, with its target date.

Forward pass: incomplete work cannot happen before the as-of date; not-started tasks also
respect their planned start (start-no-earlier-than) and every predecessor link. Backward pass:
latest finishes that still meet the target date. Total float is in business days; the
critical path is the chain of minimum-float tasks that drives the target; the gating item is
the earliest incomplete task on it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

import networkx as nx

from groundwork.core.calendar import CalendarKind, WorkCalendar

Status = Literal["done", "in_progress", "not_started"]
LinkKind = Literal["FS", "SS", "FF"]
AdjustmentKind = Literal[
    "duration_reduction", "lag_reduction", "parallelize", "not_before", "new_predecessor"
]


class CycleError(ValueError):
    """The dependency graph has a cycle, so no schedule exists."""


@dataclass(frozen=True)
class Task:
    key: str
    status: Status
    planned_finish: date
    planned_start: date | None = None  # None = a dated point with zero duration
    calendar: CalendarKind = "business"
    actual_finish: date | None = None

    @property
    def is_point(self) -> bool:
        return self.planned_start is None


@dataclass(frozen=True)
class Link:
    pred: str
    succ: str
    kind: LinkKind = "FS"
    lag: int = 0
    lag_calendar: CalendarKind = "business"


@dataclass(frozen=True)
class Delay:
    key: str
    days: int
    calendar: CalendarKind = "calendar"
    label: str = ""


@dataclass(frozen=True)
class Adjustment:
    kind: AdjustmentKind
    item: str
    days: int = 0
    pred: str | None = None
    on: date | None = None
    label: str = ""


@dataclass(frozen=True)
class Target:
    key: str
    date: date


@dataclass(frozen=True)
class CalendarLoss:
    """Holidays that fall inside a critical-path lag or a critical task's own span."""

    pred: str | None  # None: inside ``succ``'s own span
    succ: str
    holidays: tuple[date, ...]


@dataclass
class TaskResult:
    key: str
    status: Status
    early_start: date
    work_start: date
    early_finish: date
    planned_finish: date
    late_start: date | None = None
    late_finish: date | None = None
    total_float: int | None = None  # business days; None when done or not on the target's path
    critical: bool = False
    near_critical: bool = False
    on_target_path: bool = False
    drivers: list[str] = field(default_factory=list)

    @property
    def finish_shift_days(self) -> int:
        return (self.early_finish - self.planned_finish).days


@dataclass
class Schedule:
    as_of: date
    tasks: dict[str, TaskResult]
    target: Target | None
    target_finish: date | None
    target_delta_days: int | None  # calendar days; positive = late against the target date
    min_float: int | None
    critical_path: list[str]
    gate: str | None
    near_critical: list[str]
    calendar_losses: list[CalendarLoss]

    def shifted(self) -> list[str]:
        """Incomplete tasks forecast to finish after their planned finish."""
        return [k for k, r in self.tasks.items() if r.status != "done" and r.finish_shift_days > 0]


def _check_keys(task_map: dict[str, Task], links: list[Link]) -> None:
    missing = sorted({k for ln in links for k in (ln.pred, ln.succ) if k not in task_map})
    if missing:
        raise ValueError(f"links reference unknown items: {', '.join(missing)}")


def schedule(
    tasks: Iterable[Task],
    links: Iterable[Link],
    *,
    as_of: date,
    calendar: WorkCalendar,
    target: Target | None = None,
    delays: Iterable[Delay] = (),
    adjustments: Iterable[Adjustment] = (),
    near_critical_bd: int = 3,
) -> Schedule:
    task_map = {t.key: t for t in tasks}
    link_list = list(links)
    adj = list(adjustments)
    for a in adj:
        if a.kind == "new_predecessor":
            if a.pred is None:
                raise ValueError("new_predecessor adjustment needs pred")
            link_list.append(Link(a.pred, a.item, "FS", a.days, "business"))
    _check_keys(task_map, link_list)
    if target is not None and target.key not in task_map:
        raise ValueError(f"target {target.key!r} is not an item")

    g = nx.DiGraph()
    g.add_nodes_from(task_map)
    for ln in link_list:
        if g.has_edge(ln.pred, ln.succ):
            raise ValueError(f"duplicate link {ln.pred} -> {ln.succ}")
        g.add_edge(ln.pred, ln.succ, link=ln)
    if not nx.is_directed_acyclic_graph(g):
        cycle = nx.find_cycle(g)
        raise CycleError("dependency cycle: " + " -> ".join(f"{u}" for u, _ in cycle) + f" -> {cycle[0][0]}")
    order = list(nx.lexicographical_topological_sort(g))

    extra_cal: dict[str, int] = defaultdict(int)
    extra_bd: dict[str, int] = defaultdict(int)
    for d in delays:
        if d.key not in task_map:
            raise ValueError(f"delay targets unknown item {d.key!r}")
        (extra_cal if d.calendar == "calendar" else extra_bd)[d.key] += d.days
    reduction: dict[str, int] = defaultdict(int)
    lag_delta: dict[tuple[str, str], int] = defaultdict(int)
    overlap_links: set[tuple[str, str]] = set()
    not_before: dict[str, date] = {}
    for a in adj:
        if a.item not in task_map:
            raise ValueError(f"adjustment targets unknown item {a.item!r}")
        if a.kind == "duration_reduction":
            reduction[a.item] += a.days
        elif a.kind in ("lag_reduction", "parallelize"):
            if a.pred is None or not g.has_edge(a.pred, a.item):
                raise ValueError(f"{a.kind} needs an existing link into {a.item!r}")
            lag_delta[(a.pred, a.item)] -= a.days
            if a.kind == "parallelize":
                overlap_links.add((a.pred, a.item))
        elif a.kind == "not_before":
            if a.on is None:
                raise ValueError("not_before adjustment needs a date")
            not_before[a.item] = max(not_before.get(a.item, a.on), a.on)

    def eff_lag(ln: Link) -> int:
        lag = ln.lag + lag_delta.get((ln.pred, ln.succ), 0)
        if (ln.pred, ln.succ) not in overlap_links:
            lag = max(lag, min(ln.lag, 0))  # a plain lag reduction never creates overlap
        return lag

    as_of_w = calendar.roll_forward(as_of)
    es_: dict[str, date] = {}
    ws_: dict[str, date] = {}
    ef_: dict[str, date] = {}
    span_: dict[str, int] = {}
    drv_: dict[str, list[str]] = {}

    for k in order:
        t = task_map[k]
        preds = [(p, g.edges[p, k]["link"]) for p in g.predecessors(k)]
        if t.status == "done":
            ef = t.actual_finish or t.planned_finish
            es = t.planned_start or ef
            es_[k], ws_[k], ef_[k], span_[k], drv_[k] = es, es, ef, 0, []
            continue
        kind = t.calendar
        if t.is_point:
            span = 0
        elif t.status == "in_progress":
            assert t.planned_start is not None
            span = max(1, calendar.count(max(as_of_w, t.planned_start), t.planned_finish, kind))
        else:
            assert t.planned_start is not None
            span = max(1, calendar.count(t.planned_start, t.planned_finish, kind))

        cons: list[tuple[date, str]] = []
        if t.status == "in_progress":
            cons.append((as_of_w, "@as_of"))
        else:
            cons.append((t.planned_finish if t.is_point else t.planned_start, "@planned"))  # type: ignore[arg-type]
            cons.append((as_of if t.is_point else as_of_w, "@as_of"))
        for p, ln in preds:
            lag = eff_lag(ln)
            if ln.kind == "FS":
                cons.append((calendar.next_start(ef_[p], lag, ln.lag_calendar), p))
            elif ln.kind == "SS":
                cons.append((calendar.offset(ws_[p], lag, ln.lag_calendar), p))
        if k in not_before:
            cons.append((not_before[k], "@not_before"))
        ws = max(c[0] for c in cons)
        if not t.is_point:
            ws = calendar.roll_forward(ws, kind)
        drivers = [src for d, src in cons if d == max(c[0] for c in cons) and not src.startswith("@")]

        ef = calendar.finish_from_start(ws, span, kind) if span > 0 else ws
        if extra_cal[k]:
            ef = calendar.roll_forward(ef + timedelta(days=extra_cal[k]), kind)
        if extra_bd[k]:
            ef = calendar.offset(ef, extra_bd[k], "business")
        if reduction[k]:
            ef = max(ws, calendar.offset(ef, -reduction[k], kind))
        ff = [
            (calendar.offset(ef_[p], eff_lag(ln), ln.lag_calendar), p) for p, ln in preds if ln.kind == "FF"
        ]
        if ff:
            ff_date = max(d for d, _ in ff)
            if ff_date > ef:
                ef = calendar.roll_forward(ff_date, kind)
                drivers = [p for d, p in ff if d == ff_date]

        es = t.planned_start if (t.status == "in_progress" and t.planned_start) else ws
        es_[k], ws_[k], ef_[k], drv_[k] = es, ws, ef, drivers
        span_[k] = 0 if t.is_point else calendar.count(ws, ef, kind)

    results = {
        k: TaskResult(
            key=k,
            status=task_map[k].status,
            early_start=es_[k],
            work_start=ws_[k],
            early_finish=ef_[k],
            planned_finish=task_map[k].actual_finish or task_map[k].planned_finish,
            drivers=drv_[k],
        )
        for k in order
    }

    if target is None or task_map[target.key].status == "done":
        return Schedule(
            as_of,
            results,
            target,
            ef_.get(target.key) if target else None,
            (ef_[target.key] - target.date).days if target else None,
            None,
            [],
            None,
            [],
            [],
        )

    tk = target.key
    anc = nx.ancestors(g, tk) | {tk}
    lf_: dict[str, date] = {}
    ls_: dict[str, date] = {}
    for k in reversed(order):
        if k not in anc or task_map[k].status == "done":
            continue
        t = task_map[k]
        if k == tk:
            lf = target.date
        else:
            bounds: list[date] = []
            for s in g.successors(k):
                if s not in ls_:
                    continue
                ln = g.edges[k, s]["link"]
                lag = eff_lag(ln)
                if ln.kind == "FS":
                    bounds.append(calendar.latest_pred_finish(ls_[s], lag, ln.lag_calendar))
                elif ln.kind == "SS":
                    ls_bound = calendar.offset(ls_[s], -lag, ln.lag_calendar)
                    bounds.append(
                        calendar.finish_from_start(ls_bound, span_[k], t.calendar) if span_[k] else ls_bound
                    )
                else:
                    bounds.append(calendar.offset(lf_[s], -lag, ln.lag_calendar))
            if not bounds:
                continue
            lf = min(bounds)
        lf_[k] = lf
        ls_[k] = calendar.start_from_finish(lf, span_[k], t.calendar) if span_[k] else lf

    # Float in business days. A finish on a non-working day effectively lands on the next working
    # day, and a latest finish on a non-working day must be met by the previous one.
    floats = {k: calendar.between(calendar.roll_forward(ef_[k]), calendar.roll_backward(lf_[k])) for k in lf_}
    for k, f in floats.items():
        r = results[k]
        r.late_finish, r.late_start, r.total_float, r.on_target_path = lf_[k], ls_[k], f, True

    min_float = floats[tk]
    critical_set = {k for k, f in floats.items() if f == min_float}
    path: list[str] = []
    cur: str | None = tk
    seen: set[str] = set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        path.append(cur)
        nxt = [p for p in drv_[cur] if p in critical_set]
        cur = max(nxt, key=lambda p: (ef_[p], p)) if nxt else None
    path.reverse()
    for k in critical_set:
        results[k].critical = True
    near = sorted(
        (k for k, f in floats.items() if k not in critical_set and f - min_float <= near_critical_bd),
        key=lambda k: (floats[k], ef_[k], k),
    )
    for k in near:
        results[k].near_critical = True
    gate = next((k for k in path if task_map[k].status != "done"), None)

    losses: list[CalendarLoss] = []
    for i, k in enumerate(path):
        if i > 0:
            p = path[i - 1]
            gap = calendar.holidays_between(ef_[p] + timedelta(days=1), ws_[k] - timedelta(days=1))
            if gap:
                losses.append(CalendarLoss(p, k, tuple(gap)))
        if task_map[k].calendar == "business" and span_[k]:
            inside = calendar.holidays_between(ws_[k], ef_[k])
            if inside:
                losses.append(CalendarLoss(None, k, tuple(inside)))

    return Schedule(
        as_of=as_of,
        tasks=results,
        target=target,
        target_finish=ef_[tk],
        target_delta_days=(ef_[tk] - target.date).days,
        min_float=min_float,
        critical_path=path,
        gate=gate,
        near_critical=near,
        calendar_losses=losses,
    )
