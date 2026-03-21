"""Booking and time helpers used across handlers.

Constants:
    MAX_BOOKING_HOURS / MAX_BOOKING_MINUTES — per-booking duration ceiling.

Functions:
    _to_minutes        — parse HH:MM / ISO-datetime to minute-of-day.
    _to_hhmm           — format minute-of-day back to HH:MM.
    _duration_minutes   — signed duration between two time strings.
    _available_time_options — Slack static_select options for a time range.
    _normalized_available_slots — clean and cap raw Yarooms slot dicts.
    _covers_interval    — check if a free window fully covers a request.
    _is_past_slot       — reject slots whose start has already passed.
"""

import re
from datetime import datetime

MAX_BOOKING_HOURS = 3
MAX_BOOKING_MINUTES = MAX_BOOKING_HOURS * 60
MAX_DAILY_BOOKING_MINUTES = MAX_BOOKING_HOURS * 60  # per-user daily ceiling (same as per-booking for now)
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?")


def _to_minutes(value: str, *, round_up_seconds: bool = False) -> int | None:
    """Parse time-like strings to minute-of-day.

    Accepts values like ``HH:MM``, ``HH:MM:SS``, ``YYYY-MM-DD HH:MM(:SS)`` and
    ISO-like forms containing a time component.
    """
    matches = list(_TIME_RE.finditer(str(value).strip()))
    if not matches:
        return None
    hour_raw, minute_raw, second_raw = matches[-1].groups()
    hour = int(hour_raw)
    minute = int(minute_raw)
    second = int(second_raw or "0")
    if minute > 59 or second > 59:
        return None
    # Allow 24:00(:00) as an end-of-day boundary.
    if hour == 24:
        if minute == 0 and second == 0:
            return 24 * 60
        return None
    if hour > 23:
        return None
    total = hour * 60 + minute
    if round_up_seconds and second > 0:
        total = min(total + 1, 24 * 60)
    return total


def _to_hhmm(total_minutes: int) -> str:
    clamped = max(0, min(total_minutes, 24 * 60))
    if clamped == 24 * 60:
        return "24:00"
    return f"{clamped // 60:02d}:{clamped % 60:02d}"


def _duration_minutes(start: str, end: str) -> int:
    """Return booking duration in minutes. Returns negative if end is before start.

    Accepts both ``HH:MM`` and ``YYYY-MM-DD HH:MM(:SS)`` formats — the date
    portion is stripped automatically so callers don't have to normalise.
    """
    start_minutes = _to_minutes(start)
    end_minutes = _to_minutes(end, round_up_seconds=True)
    if start_minutes is None or end_minutes is None:
        return -1
    return end_minutes - start_minutes


def _available_time_options(
    start_hour: int = 8,
    end_hour: int = 22,
    minute_step: int = 10,
) -> list[dict]:
    """Return Slack static-select time options for a configurable hour window."""
    return [
        {
            "text": {"type": "plain_text", "text": f"{hour:02d}:{minute:02d}", "emoji": False},
            "value": f"{hour:02d}:{minute:02d}",
        }
        for hour in range(start_hour, end_hour)
        for minute in range(0, 60, minute_step)
    ]


def _normalized_available_slots(
    raw_slots: list[dict],
    *,
    apply_duration_cap: bool = True,
) -> list[tuple[str, str]]:
    """Normalize Yarooms availability payload into valid (start, end) HH:MM tuples.

    Args:
        raw_slots: Raw slot dicts from ``get_space_availability``.
        apply_duration_cap: When *True* (default) slots longer than
            ``MAX_BOOKING_MINUTES`` are dropped.  Set to *False* for
            "covers-interval" checks where the free window may legitimately
            exceed the per-booking cap.
    """
    normalized: list[tuple[str, str]] = []
    for slot in raw_slots:
        raw_start = slot.get("startTime") or slot.get("start", "")
        raw_end = slot.get("endTime") or slot.get("end", "")
        if not raw_start or not raw_end:
            continue
        start_minutes = _to_minutes(str(raw_start))
        end_minutes = _to_minutes(str(raw_end), round_up_seconds=True)
        if start_minutes is None or end_minutes is None:
            continue
        duration = end_minutes - start_minutes
        if duration <= 0:
            continue
        if apply_duration_cap and duration > MAX_BOOKING_MINUTES:
            continue
        normalized.append((_to_hhmm(start_minutes), _to_hhmm(end_minutes)))

    normalized.sort(key=lambda pair: _to_minutes(pair[0]) or 0)
    return normalized


def _covers_interval(available_slot: tuple[str, str], start: str, end: str) -> bool:
    """Return True if `available_slot` fully covers the [start, end] interval.

    Accepts both ``HH:MM`` and ``YYYY-MM-DD HH:MM(:SS)`` — only the time
    portion is compared.
    """
    slot_start = _to_minutes(available_slot[0])
    slot_end = _to_minutes(available_slot[1], round_up_seconds=True)
    req_start = _to_minutes(start)
    req_end = _to_minutes(end, round_up_seconds=True)
    if None in (slot_start, slot_end, req_start, req_end):
        return False
    return slot_start <= req_start and slot_end >= req_end


def _is_past_slot(date_str: str, start_time: str) -> bool:
    """Return True if the given date + start_time is strictly in the past.

    Args:
        date_str: ``YYYY-MM-DD`` date string.
        start_time: ``HH:MM`` time string.

    Returns:
        ``True`` when the slot start has already passed (compared to
        ``datetime.now()``), ``False`` otherwise or on parse errors.
    """
    try:
        slot_dt = datetime.strptime(f"{date_str} {start_time}", "%Y-%m-%d %H:%M")
        return slot_dt < datetime.now()
    except (ValueError, TypeError):
        return False


