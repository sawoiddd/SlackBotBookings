"""Shared Slack Block Kit view builders used by multiple handlers."""


def skeleton_view(word: str) -> dict:
    """Loading placeholder for modal updates. Type is 'modal' so Slack renders it correctly."""
    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": "Please wait", "emoji": False},
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"⏳ {word}..."},
            }
        ],
    }


def simple_modal(title: str, message: str) -> dict:
    """One-section informational/error modal."""
    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": title[:24], "emoji": False},
        "close": {"type": "plain_text", "text": "Close", "emoji": False},
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message},
            }
        ],
    }


def error_modal_with_context(title: str, message: str, context_lines: list[str] | None = None) -> dict:
    """Error modal with optional context lines shown below the main message."""
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": message},
        }
    ]
    if context_lines:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": line} for line in context_lines
                ],
            }
        )
    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": title[:24], "emoji": False},
        "close": {"type": "plain_text", "text": "Close", "emoji": False},
        "blocks": blocks,
    }


def quota_exceeded_modal(used: int, remaining: int, requested: int, max_daily: int) -> dict:
    """Modal shown when a booking would exceed the daily quota."""
    return simple_modal(
        "Daily Limit Reached",
        (
            f"⏳ You've used *{used}* of your *{max_daily}* daily minutes.\n"
            f"Remaining: *{remaining}* min — but this booking needs *{requested}* min.\n\n"
            f"Please choose a shorter slot or try again tomorrow."
        ),
    )


