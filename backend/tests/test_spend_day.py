"""Per-day spend headroom counts by the site's calendar day, not the UTC day the ledger stores."""

from datetime import date

from groundwork.service.pipeline import local_day


def test_evening_in_new_york_is_still_the_same_day():
    # 7:30 pm Eastern on Nov 1 is already Nov 2 in UTC.
    assert local_day("2026-11-02T00:30:00.000000Z", "America/New_York") == date(2026, 11, 1)


def test_the_day_turns_at_local_midnight():
    # Nov 10 is after daylight saving ends, so Eastern is UTC-5.
    assert local_day("2026-11-10T04:30:00.000000Z", "America/New_York") == date(2026, 11, 9)
    assert local_day("2026-11-10T05:30:00.000000Z", "America/New_York") == date(2026, 11, 10)
