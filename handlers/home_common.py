from utils.booking_utils import (
    MAX_BOOKING_HOURS,
    MAX_BOOKING_MINUTES,
    _available_time_options,
    _covers_interval,
    _duration_minutes,
    _normalized_available_slots,
)
from utils.slack_notifications import notify_booking_in_chat
from utils.slack_views import skeleton_view

__all__ = [
    "MAX_BOOKING_HOURS",
    "MAX_BOOKING_MINUTES",
    "_available_time_options",
    "_covers_interval",
    "_duration_minutes",
    "_normalized_available_slots",
    "notify_booking_in_chat",
    "skeleton_view",
    "get_user_email",
    "safe_get_room_name",
]


async def get_user_email(client, user_id: str) -> str:
    """Resolve a Slack user e-mail (requires users:read.email scope)."""
    user_info = await client.users_info(user=user_id)
    return user_info["user"]["profile"]["email"]


async def safe_get_room_name(yarooms, room_id: str) -> str:
    """Resolve room name from Yarooms, falling back to room_id on any failure."""
    try:
        spaces = await yarooms.get_spaces()
        return next(
            (
                space.get("name")
                for space in spaces
                if str(space.get("id")) == str(room_id) and space.get("name")
            ),
            room_id,
        )
    except Exception:
        return room_id



