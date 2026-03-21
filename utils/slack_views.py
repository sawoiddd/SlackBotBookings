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


