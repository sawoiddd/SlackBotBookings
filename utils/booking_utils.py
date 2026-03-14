from datetime import datetime

MAX_BOOKING_HOURS = 3
MAX_BOOKING_MINUTES = MAX_BOOKING_HOURS * 60


def _duration_minutes(start: str, end: str) -> int:
    """Return booking duration in minutes. Returns negative if end is before start."""
    fmt = "%H:%M"
    delta = datetime.strptime(end, fmt) - datetime.strptime(start, fmt)
    return int(delta.total_seconds() / 60)


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


def _normalized_available_slots(raw_slots: list[dict]) -> list[tuple[str, str]]:
    """Normalize Yarooms availability payload into valid (start, end) time tuples."""
    normalized: list[tuple[str, str]] = []
    for slot in raw_slots:
        start = slot.get("startTime") or slot.get("start", "")
        end = slot.get("endTime") or slot.get("end", "")
        if not start or not end:
            continue
        if _duration_minutes(start, end) <= 0:
            continue
        if _duration_minutes(start, end) > MAX_BOOKING_MINUTES:
            continue
        normalized.append((start, end))

    normalized.sort(key=lambda pair: pair[0])
    return normalized


def _covers_interval(available_slot: tuple[str, str], start: str, end: str) -> bool:
    """Return True if `available_slot` fully covers the [start, end] interval."""
    slot_start, slot_end = available_slot
    return slot_start <= start and slot_end >= end


