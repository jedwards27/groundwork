"""Working-day arithmetic.

Two calendars: ``business`` (weekdays minus the site's holiday list) and ``calendar`` (every day).
Conventions used throughout the engine:

* An item occupies the inclusive date range [start, finish].
* A finish-to-start link with lag L means the successor may start on the (1 + L)-th working
  day after the predecessor's finish. Lag 0 = the next working day.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

import numpy as np

CalendarKind = Literal["business", "calendar"]


def _d64(d: date) -> np.datetime64:
    return np.datetime64(d, "D")


def _to_date(x: np.datetime64) -> date:
    return x.astype("datetime64[D]").astype(object)  # type: ignore[no-any-return]


@dataclass(frozen=True)
class WorkCalendar:
    holidays: tuple[date, ...] = ()
    _hol: np.ndarray = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_hol", np.array(sorted(self.holidays), dtype="datetime64[D]"))

    @classmethod
    def of(cls, holidays: Iterable[date]) -> WorkCalendar:
        return cls(tuple(sorted(set(holidays))))

    # -- primitives ---------------------------------------------------------------------------
    def is_workday(self, d: date, kind: CalendarKind = "business") -> bool:
        if kind == "calendar":
            return True
        return bool(np.is_busday(_d64(d), holidays=self._hol))

    def roll_forward(self, d: date, kind: CalendarKind = "business") -> date:
        if kind == "calendar":
            return d
        return _to_date(np.busday_offset(_d64(d), 0, roll="forward", holidays=self._hol))

    def roll_backward(self, d: date, kind: CalendarKind = "business") -> date:
        if kind == "calendar":
            return d
        return _to_date(np.busday_offset(_d64(d), 0, roll="backward", holidays=self._hol))

    def offset(self, d: date, n: int, kind: CalendarKind = "business") -> date:
        """Move ``n`` working days from ``d``; ``d`` is first rolled in the direction of travel."""
        if kind == "calendar":
            return d + timedelta(days=n)
        roll = "forward" if n >= 0 else "backward"
        return _to_date(np.busday_offset(_d64(d), n, roll=roll, holidays=self._hol))

    # -- spans --------------------------------------------------------------------------------
    def count(self, start: date, finish: date, kind: CalendarKind = "business") -> int:
        """Working days in the inclusive range [start, finish]; 0 if finish < start."""
        if finish < start:
            return 0
        if kind == "calendar":
            return (finish - start).days + 1
        return int(np.busday_count(_d64(start), _d64(finish + timedelta(days=1)), holidays=self._hol))

    def between(self, a: date, b: date, kind: CalendarKind = "business") -> int:
        """Signed working days from ``a`` to ``b`` (positive when b is later). between(d, d) == 0."""
        if b >= a:
            return self.count(a + timedelta(days=1), b, kind)
        return -self.count(b + timedelta(days=1), a, kind)

    def finish_from_start(self, start: date, duration: int, kind: CalendarKind = "business") -> date:
        if duration <= 0:
            return start
        return self.offset(self.roll_forward(start, kind), duration - 1, kind)

    def start_from_finish(self, finish: date, duration: int, kind: CalendarKind = "business") -> date:
        if duration <= 0:
            return finish
        return self.offset(self.roll_backward(finish, kind), -(duration - 1), kind)

    def next_start(self, pred_finish: date, lag: int, kind: CalendarKind = "business") -> date:
        """Earliest start of a successor after a predecessor that finishes on ``pred_finish``."""
        if kind == "calendar":
            return pred_finish + timedelta(days=1 + lag)
        return _to_date(np.busday_offset(_d64(pred_finish), 1 + lag, roll="backward", holidays=self._hol))

    def latest_pred_finish(self, succ_start: date, lag: int, kind: CalendarKind = "business") -> date:
        """Latest finish of a predecessor that still lets a successor start on ``succ_start``."""
        if kind == "calendar":
            return succ_start - timedelta(days=1 + lag)
        return _to_date(np.busday_offset(_d64(succ_start), -(1 + lag), roll="forward", holidays=self._hol))

    def holidays_between(self, start: date, finish: date) -> list[date]:
        """Holidays falling on weekdays inside the inclusive range."""
        return [h for h in self.holidays if start <= h <= finish and h.weekday() < 5]
