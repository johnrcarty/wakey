"""Tests for the pure occurrence math.

No Home Assistant involved — this is where the DST behaviour is pinned down.
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from custom_components.wakey import occurrence

NY = ZoneInfo("America/New_York")

WEEKDAYS = [0, 1, 2, 3, 4]


def _utc(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=NY).astimezone(timezone.utc)


# --- DST -------------------------------------------------------------------


def test_spring_forward_gap_fires_at_transition():
    """02:30 does not exist on 2026-03-08; fire at 03:00, never at 01:30."""
    result = occurrence.to_utc(datetime(2026, 3, 8, 2, 30), NY)
    local = result.astimezone(NY)
    assert (local.hour, local.minute) == (3, 0)
    assert local.utcoffset().total_seconds() == -4 * 3600  # EDT


def test_fall_back_ambiguous_uses_first_pass():
    """01:30 happens twice on 2026-11-01; take the earlier (EDT) one."""
    result = occurrence.to_utc(datetime(2026, 11, 1, 1, 30), NY)
    local = result.astimezone(NY)
    assert (local.hour, local.minute) == (1, 30)
    assert local.utcoffset().total_seconds() == -4 * 3600  # EDT, not EST


def test_fall_back_does_not_double_fire():
    """The most likely correctness bug in an alarm clock.

    After ringing at the first 01:30 on fall-back night, the next occurrence
    must be the following day — not the second 01:30 an hour later.
    """
    fired_at = occurrence.to_utc(datetime(2026, 11, 1, 1, 30), NY)
    following = occurrence.next_occurrence(
        time_str="01:30",
        repeat="weekly",
        weekdays=[0, 1, 2, 3, 4, 5, 6],
        one_off_date=None,
        tz=NY,
        now_utc=fired_at,
    )
    assert following.astimezone(NY).date() == date(2026, 11, 2)


def test_normal_time_round_trips():
    result = occurrence.to_utc(datetime(2026, 6, 15, 7, 0), NY)
    assert result.astimezone(NY).replace(tzinfo=None) == datetime(2026, 6, 15, 7, 0)


def test_alarm_across_spring_forward_still_scheduled():
    """A 02:30 weekday alarm must not vanish on the transition day."""
    now = _utc(2026, 3, 7, 12, 0)  # Saturday before the change
    result = occurrence.next_occurrence(
        time_str="02:30",
        repeat="weekly",
        weekdays=[6],  # Sunday
        one_off_date=None,
        tz=NY,
        now_utc=now,
    )
    assert result is not None
    assert result.astimezone(NY).hour == 3


# --- weekly ----------------------------------------------------------------


def test_weekly_picks_next_matching_day():
    now = _utc(2026, 8, 8, 12, 0)  # Saturday
    result = occurrence.next_occurrence(
        time_str="07:00",
        repeat="weekly",
        weekdays=WEEKDAYS,
        one_off_date=None,
        tz=NY,
        now_utc=now,
    )
    assert result == _utc(2026, 8, 10, 7, 0)  # Monday


def test_weekly_later_today_still_counts():
    now = _utc(2026, 8, 10, 6, 0)  # Monday 06:00
    result = occurrence.next_occurrence(
        time_str="07:00",
        repeat="weekly",
        weekdays=WEEKDAYS,
        one_off_date=None,
        tz=NY,
        now_utc=now,
    )
    assert result == _utc(2026, 8, 10, 7, 0)


def test_weekly_already_passed_today_rolls_over():
    now = _utc(2026, 8, 10, 8, 0)  # Monday 08:00, past 07:00
    result = occurrence.next_occurrence(
        time_str="07:00",
        repeat="weekly",
        weekdays=WEEKDAYS,
        one_off_date=None,
        tz=NY,
        now_utc=now,
    )
    assert result == _utc(2026, 8, 11, 7, 0)  # Tuesday


def test_no_weekdays_never_fires():
    now = _utc(2026, 8, 8, 12, 0)
    assert (
        occurrence.next_occurrence(
            time_str="07:00",
            repeat="weekly",
            weekdays=[],
            one_off_date=None,
            tz=NY,
            now_utc=now,
        )
        is None
    )


# --- skip next -------------------------------------------------------------


def test_skip_next_returns_the_one_after():
    now = _utc(2026, 8, 8, 12, 0)  # Saturday
    result = occurrence.next_occurrence(
        time_str="07:00",
        repeat="weekly",
        weekdays=WEEKDAYS,
        one_off_date=None,
        tz=NY,
        now_utc=now,
        skip_next=True,
    )
    assert result == _utc(2026, 8, 11, 7, 0)  # Tuesday, not Monday


# --- one-off ---------------------------------------------------------------


def test_one_off_in_future():
    now = _utc(2026, 8, 8, 12, 0)
    result = occurrence.next_occurrence(
        time_str="06:30",
        repeat="once",
        weekdays=None,
        one_off_date="2026-08-09",
        tz=NY,
        now_utc=now,
    )
    assert result == _utc(2026, 8, 9, 6, 30)


def test_one_off_in_past_is_none():
    now = _utc(2026, 8, 8, 12, 0)
    assert (
        occurrence.next_occurrence(
            time_str="06:30",
            repeat="once",
            weekdays=None,
            one_off_date="2026-01-01",
            tz=NY,
            now_utc=now,
        )
        is None
    )


def test_skipped_one_off_never_fires():
    now = _utc(2026, 8, 8, 12, 0)
    assert (
        occurrence.next_occurrence(
            time_str="06:30",
            repeat="once",
            weekdays=None,
            one_off_date="2026-08-09",
            tz=NY,
            now_utc=now,
            skip_next=True,
        )
        is None
    )


# --- previous / missed detection -------------------------------------------


def test_previous_occurrence_finds_last_weekday():
    now = _utc(2026, 8, 8, 12, 0)  # Saturday
    result = occurrence.previous_occurrence(
        time_str="07:00",
        repeat="weekly",
        weekdays=WEEKDAYS,
        one_off_date=None,
        tz=NY,
        now_utc=now,
    )
    assert result == _utc(2026, 8, 7, 7, 0)  # Friday


def test_previous_occurrence_none_before_first_one_off():
    now = _utc(2026, 8, 8, 12, 0)
    assert (
        occurrence.previous_occurrence(
            time_str="07:00",
            repeat="once",
            weekdays=None,
            one_off_date="2026-09-01",
            tz=NY,
            now_utc=now,
        )
        is None
    )


# --- robustness ------------------------------------------------------------


def test_garbage_time_returns_none_rather_than_raising():
    now = _utc(2026, 8, 8, 12, 0)
    assert (
        occurrence.next_occurrence(
            time_str="not-a-time",
            repeat="weekly",
            weekdays=WEEKDAYS,
            one_off_date=None,
            tz=NY,
            now_utc=now,
        )
        is None
    )


# --- one-time adjustments --------------------------------------------------


def test_adjustment_moves_only_the_named_day():
    """The moved occurrence rings early; the one after it is untouched."""
    now = _utc(2026, 8, 20, 18, 0)  # Thursday evening
    kwargs = dict(
        time_str="07:00",
        repeat="weekly",
        weekdays=WEEKDAYS,
        one_off_date=None,
        tz=NY,
        now_utc=now,
        override_for="2026-08-21",
        override_time="05:30",
    )

    moved = occurrence.next_occurrence(**kwargs)
    assert moved.astimezone(NY).replace(tzinfo=None) == datetime(2026, 8, 21, 5, 30)

    # skip_next reaches past it to Monday, back at the usual time.
    following = occurrence.next_occurrence(**{**kwargs, "skip_next": True})
    assert following.astimezone(NY).replace(tzinfo=None) == datetime(2026, 8, 24, 7, 0)


def test_adjustment_replaces_rather_than_adds():
    """Moving an occurrence must not leave the original time ringing too.

    The worst version of this bug is silent: the alarm goes off early as
    asked, and then again at its usual time.
    """
    fired_at = _utc(2026, 8, 21, 5, 30)
    following = occurrence.next_occurrence(
        time_str="07:00",
        repeat="weekly",
        weekdays=WEEKDAYS,
        one_off_date=None,
        tz=NY,
        now_utc=fired_at,
        override_for="2026-08-21",
        override_time="05:30",
    )
    assert following.astimezone(NY).date() == date(2026, 8, 24)


def test_adjustment_for_a_different_day_is_inert():
    """A spent adjustment left on the alarm changes nothing."""
    now = _utc(2026, 8, 20, 18, 0)
    result = occurrence.next_occurrence(
        time_str="07:00",
        repeat="weekly",
        weekdays=WEEKDAYS,
        one_off_date=None,
        tz=NY,
        now_utc=now,
        override_for="2026-08-14",
        override_time="05:30",
    )
    assert result.astimezone(NY).replace(tzinfo=None) == datetime(2026, 8, 21, 7, 0)


def test_adjustment_earlier_than_now_is_missed_not_fired_late():
    """06:00, alarm moved to 05:30 today: today is gone, not owed."""
    now = _utc(2026, 8, 21, 6, 0)
    result = occurrence.next_occurrence(
        time_str="07:00",
        repeat="weekly",
        weekdays=WEEKDAYS,
        one_off_date=None,
        tz=NY,
        now_utc=now,
        override_for="2026-08-21",
        override_time="05:30",
    )
    assert result.astimezone(NY).replace(tzinfo=None) == datetime(2026, 8, 24, 7, 0)


def test_previous_occurrence_sees_the_adjustment():
    """Catch-up after a restart must look for the moved time, not the usual one."""
    now = _utc(2026, 8, 21, 5, 35)
    previous = occurrence.previous_occurrence(
        time_str="07:00",
        repeat="weekly",
        weekdays=WEEKDAYS,
        one_off_date=None,
        tz=NY,
        now_utc=now,
        override_for="2026-08-21",
        override_time="05:30",
    )
    assert previous.astimezone(NY).replace(tzinfo=None) == datetime(2026, 8, 21, 5, 30)


def test_adjustment_into_the_spring_forward_gap():
    """Moved to a wall clock that does not exist: same rule as a normal time."""
    now = _utc(2026, 3, 7, 18, 0)
    result = occurrence.next_occurrence(
        time_str="07:00",
        repeat="weekly",
        weekdays=[0, 1, 2, 3, 4, 5, 6],
        one_off_date=None,
        tz=NY,
        now_utc=now,
        override_for="2026-03-08",
        override_time="02:30",
    )
    local = result.astimezone(NY)
    assert (local.hour, local.minute) == (3, 0)


def test_unreadable_adjustment_falls_back_to_the_configured_time():
    """A corrupt adjustment must not take the alarm out of service."""
    now = _utc(2026, 8, 20, 18, 0)
    result = occurrence.next_occurrence(
        time_str="07:00",
        repeat="weekly",
        weekdays=WEEKDAYS,
        one_off_date=None,
        tz=NY,
        now_utc=now,
        override_for="2026-08-21",
        override_time="not a time",
    )
    assert result.astimezone(NY).replace(tzinfo=None) == datetime(2026, 8, 21, 7, 0)
