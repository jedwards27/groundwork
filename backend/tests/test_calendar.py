from datetime import date

from groundwork.core import WorkCalendar

THANKSGIVING = WorkCalendar.of([date(2026, 11, 26), date(2026, 11, 27)])


def test_next_start_is_next_working_day():
    assert THANKSGIVING.next_start(date(2026, 11, 13), 0) == date(2026, 11, 16)  # Fri -> Mon


def test_business_lag_crosses_holiday_week():
    # 15 working days after Fri Nov 13, skipping Thanksgiving and the day after.
    assert THANKSGIVING.next_start(date(2026, 11, 13), 15) == date(2026, 12, 9)
    assert WorkCalendar().next_start(date(2026, 11, 13), 15) == date(2026, 12, 7)


def test_latest_pred_finish_inverts_next_start():
    succ = THANKSGIVING.next_start(date(2026, 11, 13), 15)
    assert THANKSGIVING.latest_pred_finish(succ, 15) == date(2026, 11, 13)


def test_count_and_between():
    cal = WorkCalendar()
    assert cal.count(date(2026, 11, 2), date(2026, 11, 6)) == 5
    assert cal.count(date(2026, 11, 6), date(2026, 11, 2)) == 0
    assert cal.between(date(2026, 11, 6), date(2026, 11, 9)) == 1
    assert cal.between(date(2026, 11, 9), date(2026, 11, 6)) == -1
    assert cal.between(date(2026, 11, 9), date(2026, 11, 9)) == 0
    assert cal.count(date(2026, 11, 1), date(2026, 11, 30), "calendar") == 30


def test_finish_from_start_round_trip():
    cal = THANKSGIVING
    f = cal.finish_from_start(date(2026, 11, 23), 5)
    assert f == date(2026, 12, 1)
    assert cal.start_from_finish(f, 5) == date(2026, 11, 23)


def test_holidays_between_ignores_weekend_holidays():
    cal = WorkCalendar.of([date(2026, 11, 28), date(2026, 11, 26)])  # Saturday is ignored
    assert cal.holidays_between(date(2026, 11, 20), date(2026, 11, 30)) == [date(2026, 11, 26)]
