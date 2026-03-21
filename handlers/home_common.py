"""Common module imported by all feature handlers via
``import handlers.home_common as common``.

Re-exports shared booking/time helpers and Slack view utilities, and provides
``get_user_email`` and ``safe_get_room_name`` helpers.
"""

import logging

from utils.booking_utils import (
    MAX_BOOKING_HOURS,
    MAX_BOOKING_MINUTES,
    MAX_DAILY_BOOKING_MINUTES,
    _available_time_options,
    _covers_interval,
    _duration_minutes,
    _is_past_slot,
    _normalized_available_slots,
)
from utils.slack_notifications import notify_booking_in_chat
from utils.slack_views import (
    error_modal_with_context,
    quota_exceeded_modal,
    simple_modal,
    skeleton_view,
)

_logger = logging.getLogger(__name__)

__all__ = [
    "MAX_BOOKING_HOURS",
    "MAX_BOOKING_MINUTES",
    "MAX_DAILY_BOOKING_MINUTES",
    "_available_time_options",
    "_covers_interval",
    "_duration_minutes",
    "_is_past_slot",
    "_normalized_available_slots",
    "error_modal_with_context",
    "notify_booking_in_chat",
    "quota_exceeded_modal",
    "simple_modal",
    "skeleton_view",
    "get_user_email",
    "safe_get_room_name",
]


async def get_user_email(client, user_id: str) -> str:
    """Resolve a Slack user e-mail (requires users:read + users:read.email scopes).

    Returns an empty string when the API call fails (e.g. missing OAuth scope)
    so callers can continue without crashing.
    """
    try:
        user_info = await client.users_info(user=user_id)
        email = user_info["user"]["profile"].get("email", "")
        if not email:
            _logger.warning(
                "users_info succeeded but profile.email is empty for user=%s. "
                "Check that the Slack app has the 'users:read.email' scope AND "
                "the app was re-installed to the workspace after adding the scope.",
                user_id,
            )
        return email
    except Exception as exc:
        _logger.error(
            "Failed to fetch email for user=%s: %s. "
            "Verify 'users:read' + 'users:read.email' scopes are granted and "
            "the app was re-installed after adding them.",
            user_id,
            exc,
        )
        return ""


async def safe_get_room_name(yarooms, room_id: str) -> str:
    """Resolve room name from Yarooms, falling back to room_id on any failure."""
    try:
        spaces = await yarooms.get_spaces_cached()
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
