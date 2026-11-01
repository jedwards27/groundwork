from datetime import date

import pytest

from groundwork.core import Adjustment, CycleError, Delay, Link, Target, Task, WorkCalendar, schedule

CAL = WorkCalendar()
AS_OF = date(2026, 11, 2)  # Monday


def chain():
    return [
        Task("a", "in_progress", date(2026, 11, 6), date(2026, 10, 26)),
        Task("b", "not_started", date(2026, 11, 13), date(2026, 11, 9)),
        Task("c", "not_started", date(2026, 11, 20), date(2026, 11, 16)),
        Task("side", "not_started", date(2026, 11, 10), date(2026, 11, 9)),
    ], [Link("a", "b"), Link("b", "c"), Link("side", "c")]


def test_baseline_meets_plan_and_names_gate():
    tasks, links = chain()
    s = schedule(tasks, links, as_of=AS_OF, calendar=CAL, target=Target("c", date(2026, 11, 24)))
    assert s.target_finish == date(2026, 11, 20)
    assert s.min_float == 2
    assert s.critical_path == ["a", "b", "c"]
    assert s.gate == "a"
    assert s.tasks["side"].total_float == 2 + 3
    assert s.shifted() == []


def test_delay_propagates_downstream():
    tasks, links = chain()
    s = schedule(
        tasks,
        links,
        as_of=AS_OF,
        calendar=CAL,
        target=Target("c", date(2026, 11, 24)),
        delays=[Delay("a", 7, "calendar")],
    )
    assert s.tasks["a"].early_finish == date(2026, 11, 13)
    assert s.target_finish == date(2026, 11, 27)
    assert s.target_delta_days == 3
    assert s.min_float < 0


def test_overdue_in_progress_cannot_finish_before_as_of():
    tasks = [Task("a", "in_progress", date(2026, 10, 20), date(2026, 10, 1))]
    s = schedule(tasks, [], as_of=AS_OF, calendar=CAL)
    assert s.tasks["a"].early_finish == AS_OF


def test_done_tasks_do_not_move_and_have_no_float():
    tasks = [
        Task("a", "done", date(2026, 10, 1), date(2026, 9, 1), actual_finish=date(2026, 10, 3)),
        Task("b", "not_started", date(2026, 11, 13), date(2026, 11, 9)),
    ]
    s = schedule(tasks, [Link("a", "b")], as_of=AS_OF, calendar=CAL, target=Target("b", date(2026, 11, 13)))
    assert s.tasks["a"].early_finish == date(2026, 10, 3)
    assert s.tasks["a"].total_float is None
    assert s.gate == "b"


def test_ff_link_constrains_finish():
    tasks = [
        Task("x", "in_progress", date(2026, 11, 12), date(2026, 7, 1), "calendar"),
        Task("y", "in_progress", date(2026, 11, 13), date(2026, 10, 5)),
    ]
    s = schedule(tasks, [Link("x", "y", "FF", 5)], as_of=AS_OF, calendar=CAL, delays=[Delay("x", 7)])
    assert s.tasks["x"].early_finish == date(2026, 11, 19)
    assert s.tasks["y"].early_finish == date(2026, 11, 26)
    assert s.tasks["y"].drivers == ["x"]


def test_ss_link_and_point_task():
    tasks = [
        Task("x", "not_started", date(2026, 11, 13), date(2026, 11, 9)),
        Task("y", "not_started", date(2026, 11, 20), date(2026, 11, 11)),
        Task("m", "not_started", date(2026, 11, 25)),
    ]
    s = schedule(
        tasks,
        [Link("x", "y", "SS", 2), Link("y", "m")],
        as_of=AS_OF,
        calendar=CAL,
        target=Target("m", date(2026, 11, 30)),
    )
    assert s.tasks["y"].work_start == date(2026, 11, 11)
    assert s.tasks["m"].early_finish == date(2026, 11, 25)


def test_cycle_is_reported():
    tasks = [
        Task("a", "not_started", date(2026, 11, 6), date(2026, 11, 2)),
        Task("b", "not_started", date(2026, 11, 13), date(2026, 11, 9)),
    ]
    with pytest.raises(CycleError):
        schedule(tasks, [Link("a", "b"), Link("b", "a")], as_of=AS_OF, calendar=CAL)


def test_unknown_link_key_is_reported():
    with pytest.raises(ValueError, match="unknown items: nope"):
        schedule(
            [Task("a", "not_started", date(2026, 11, 6), date(2026, 11, 2))],
            [Link("nope", "a")],
            as_of=AS_OF,
            calendar=CAL,
        )


def test_adjustments():
    tasks, links = chain()
    target = Target("c", date(2026, 11, 24))
    base = schedule(tasks, links, as_of=AS_OF, calendar=CAL, target=target, delays=[Delay("a", 14)])
    shorter = schedule(
        tasks,
        links,
        as_of=AS_OF,
        calendar=CAL,
        target=target,
        delays=[Delay("a", 14)],
        adjustments=[Adjustment("duration_reduction", "a", 3)],
    )
    assert (base.tasks["a"].early_finish - shorter.tasks["a"].early_finish).days >= 3
    overlap = schedule(
        tasks,
        links,
        as_of=AS_OF,
        calendar=CAL,
        target=target,
        delays=[Delay("a", 14)],
        adjustments=[Adjustment("parallelize", "b", 3, pred="a")],
    )
    assert overlap.tasks["b"].work_start < base.tasks["b"].work_start
    lag_floor = schedule(
        tasks,
        links,
        as_of=AS_OF,
        calendar=CAL,
        target=target,
        adjustments=[Adjustment("lag_reduction", "b", 5, pred="a")],
    )
    assert lag_floor.tasks["b"].work_start == date(2026, 11, 9)  # lag cannot go below zero
    later = schedule(
        tasks,
        links,
        as_of=AS_OF,
        calendar=CAL,
        target=target,
        adjustments=[Adjustment("not_before", "c", on=date(2026, 11, 23))],
    )
    assert later.tasks["c"].work_start == date(2026, 11, 23)
    added = schedule(
        tasks,
        links,
        as_of=AS_OF,
        calendar=CAL,
        target=target,
        adjustments=[Adjustment("new_predecessor", "side", 0, pred="b")],
    )
    assert added.tasks["side"].work_start == date(2026, 11, 16)


def test_calendar_loss_on_critical_lag():
    cal = WorkCalendar.of([date(2026, 11, 26), date(2026, 11, 27)])
    tasks = [
        Task("a", "in_progress", date(2026, 11, 13), date(2026, 10, 19)),
        Task("b", "not_started", date(2026, 12, 15), date(2026, 12, 9)),
    ]
    s = schedule(
        tasks, [Link("a", "b", "FS", 15)], as_of=AS_OF, calendar=cal, target=Target("b", date(2026, 12, 18))
    )
    assert s.calendar_losses[0].pred == "a"
    assert s.calendar_losses[0].holidays == (date(2026, 11, 26), date(2026, 11, 27))


def test_floor_limits_how_early_a_reduction_can_land():
    tasks = [Task("x", "in_progress", date(2026, 11, 30), date(2026, 10, 1))]
    plain = schedule(tasks, [], as_of=AS_OF, calendar=CAL, adjustments=[Adjustment("duration_reduction", "x", 10)])
    floored = schedule(tasks, [], as_of=AS_OF, calendar=CAL,
                       adjustments=[Adjustment("duration_reduction", "x", 10, floor=date(2026, 11, 25))])
    assert plain.tasks["x"].early_finish == date(2026, 11, 16)
    assert floored.tasks["x"].early_finish == date(2026, 11, 25)
    late_floor = schedule(tasks, [], as_of=AS_OF, calendar=CAL,
                          adjustments=[Adjustment("duration_reduction", "x", 10, floor=date(2026, 12, 15))])
    assert late_floor.tasks["x"].early_finish == date(2026, 11, 30)  # a floor never pushes a date later


def test_floor_on_overlap_caps_the_earlier_start():
    tasks, links = chain()
    target = Target("c", date(2026, 11, 24))
    overlap = schedule(tasks, links, as_of=AS_OF, calendar=CAL, target=target, delays=[Delay("a", 14)],
                       adjustments=[Adjustment("parallelize", "b", 5, pred="a", floor=date(2026, 11, 18))])
    base = schedule(tasks, links, as_of=AS_OF, calendar=CAL, target=target, delays=[Delay("a", 14)])
    assert overlap.tasks["b"].work_start == date(2026, 11, 18)
    assert base.tasks["b"].work_start == date(2026, 11, 23)
