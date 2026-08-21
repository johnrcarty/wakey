"""Pure date/time math for Wakey alarms.

Deliberately free of Home Assistant imports so the DST-sensitive logic can be
unit tested directly and fast. Everything here takes an explicit tzinfo and an
explicit "now", so there is no hidden dependency on the machine clock.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo

# How far ahead/back to search for a matching weekday. Two weeks is more than
# enough for any weekday mask and bounds the loop.
MAX_SEARCH_DAYS = 14

REPEAT_ONCE = "once"
REPEAT_WEEKLY = "weekly"


def parse_time(value: str) -> time:
    """Parse "HH:MM" or "HH:MM:SS" into a time. Seconds are ignored."""
    parts = value.split(":")
    return time(int(parts[0]), int(parts[1]))


def to_utc(naive_local: datetime, tz: tzinfo) -> datetime:
    """Convert a naive local wall-clock datetime to an aware UTC instant.

    Both DST edge cases are resolved deliberately:

    * **Ambiguous** (fall back — 01:30 happens twice): the *first* occurrence
      is used, so the alarm fires once, at the earlier of the two.
    * **Nonexistent** (spring forward — 02:30 never happens): the first valid
      instant at or after the requested wall clock is used, which is the
      transition itself (03:00). Firing at 03:00 is closer to the user's
      intent than the naive round-trip result of 03:30, and it can never fire
      *early*.
    """
    aware = naive_local.replace(tzinfo=tz, fold=0)
    utc = aware.astimezone(timezone.utc)
    if utc.astimezone(tz).replace(tzinfo=None) == naive_local:
        # Exists. For an ambiguous time fold=0 is the first occurrence, which
        # is what we want.
        return utc

    # Nonexistent local time: it fell in a spring-forward gap. fold=0 maps to
    # an instant after the gap, fold=1 to one before it. Bisect between them
    # for the exact transition, maintaining local(lo) < target <= local(hi).
    a = naive_local.replace(tzinfo=tz, fold=0).astimezone(timezone.utc)
    b = naive_local.replace(tzinfo=tz, fold=1).astimezone(timezone.utc)
    lo, hi = (b, a) if b < a else (a, b)
    while (hi - lo) > timedelta(seconds=1):
        mid = lo + (hi - lo) / 2
        if mid.astimezone(tz).replace(tzinfo=None) < naive_local:
            lo = mid
        else:
            hi = mid
    return hi.replace(microsecond=0)


def _instant_for(
    day: date,
    alarm_time: time,
    tz: tzinfo,
    override_for: str | None,
    override_time: str | None,
) -> datetime:
    """The UTC instant this alarm lands on for one local day.

    A one-time adjustment replaces the wall clock on exactly one date and
    changes nothing else, so it is applied here rather than by the callers.
    Every lookup — next, next-but-one, previous — then agrees about which
    occurrence was moved and where it went.
    """
    if override_for and override_time and day.isoformat() == override_for:
        try:
            return to_utc(datetime.combine(day, parse_time(override_time)), tz)
        except (ValueError, IndexError):
            # An unreadable adjustment must not take the alarm out entirely;
            # fall back to the time the user actually configured.
            pass
    return to_utc(datetime.combine(day, alarm_time), tz)


def _matches(day: date, repeat: str, weekdays: list[int] | None) -> bool:
    if repeat == REPEAT_WEEKLY:
        return bool(weekdays) and day.weekday() in weekdays
    return True


def _candidate_days(repeat: str, one_off_date: str | None, anchor: date, forward: bool) -> list[date]:
    if repeat == REPEAT_ONCE:
        if not one_off_date:
            return []
        return [date.fromisoformat(one_off_date)]
    step = 1 if forward else -1
    return [anchor + timedelta(days=step * i) for i in range(MAX_SEARCH_DAYS + 1)]


def next_occurrence(
    *,
    time_str: str,
    repeat: str,
    weekdays: list[int] | None,
    one_off_date: str | None,
    tz: tzinfo,
    now_utc: datetime,
    skip_next: bool = False,
    override_for: str | None = None,
    override_time: str | None = None,
) -> datetime | None:
    """Return the next UTC instant this alarm should fire, or None.

    None means "never again" — an expired one-off, a weekly alarm with no
    weekdays selected, or a one-off whose only occurrence was skipped.
    """
    try:
        alarm_time = parse_time(time_str)
    except (ValueError, IndexError):
        return None

    anchor = now_utc.astimezone(tz).date()
    hits: list[datetime] = []
    for day in _candidate_days(repeat, one_off_date, anchor, forward=True):
        if not _matches(day, repeat, weekdays):
            continue
        instant = _instant_for(day, alarm_time, tz, override_for, override_time)
        if instant > now_utc:
            hits.append(instant)
            # Only ever need two: the next one, and the one after it for
            # skip_next.
            if len(hits) >= 2:
                break

    if not hits:
        return None
    if skip_next:
        return hits[1] if len(hits) > 1 else None
    return hits[0]


def previous_occurrence(
    *,
    time_str: str,
    repeat: str,
    weekdays: list[int] | None,
    one_off_date: str | None,
    tz: tzinfo,
    now_utc: datetime,
    override_for: str | None = None,
    override_time: str | None = None,
) -> datetime | None:
    """Return the most recent UTC instant at or before now, or None.

    Used on startup to work out whether an alarm was missed while Home
    Assistant was down.
    """
    try:
        alarm_time = parse_time(time_str)
    except (ValueError, IndexError):
        return None

    anchor = now_utc.astimezone(tz).date()
    for day in _candidate_days(repeat, one_off_date, anchor, forward=False):
        if not _matches(day, repeat, weekdays):
            continue
        instant = _instant_for(day, alarm_time, tz, override_for, override_time)
        if instant <= now_utc:
            return instant
    return None
