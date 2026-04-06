"""Shared Slack chat notification helpers — sends booking confirmation DMs."""

import json


async def notify_booking_in_chat(
    client,
    logger,
    user_id: str,
    room_name: str,
    booking_date: str,
    start_time: str,
    end_time: str,
    booking_id: str | None = None,
    user_email: str = "",
) -> None:
    """Send a booking confirmation DM with room and time details."""
    try:
        payload = {
            "booking_id": booking_id,
            "room_name": room_name,
            "booking_date": booking_date,
            "start_time": start_time,
            "end_time": end_time,
            "user_email": user_email,
            "user_id": user_id,
        }

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "✅ *Бронювання підтверджено!*\n"
                        f"*Кімната:* {room_name}\n"
                        f"*Дата:* {booking_date}\n"
                        f"*Час:* {start_time} - {end_time}"
                    ),
                },
            }
        ]

        if booking_id:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "action_id": "action_cancel_booking",
                            "style": "danger",
                            "text": {"type": "plain_text", "text": "Скасувати бронювання", "emoji": False},
                            "value": json.dumps(payload, separators=(",", ":")),
                            "confirm": {
                                "title": {"type": "plain_text", "text": "Скасувати бронювання?", "emoji": False},
                                "text": {
                                    "type": "mrkdwn",
                                    "text": (
                                        f"Скасувати бронювання на *{booking_date}* "
                                        f"(*{start_time}-{end_time}*)?"
                                    ),
                                },
                                "confirm": {"type": "plain_text", "text": "Так, скасувати", "emoji": False},
                                "deny": {"type": "plain_text", "text": "Залишити", "emoji": False},
                            },
                        }
                    ],
                }
            )

        await client.chat_postMessage(
            channel=user_id,
            text=(
                "Бронювання підтверджено!\n"
                f"Кімната: {room_name}\n"
                f"Дата: {booking_date}\n"
                f"Час: {start_time} - {end_time}"
            ),
            blocks=blocks,
        )
    except Exception as notify_error:
        logger.warning(f"Could not send booking confirmation message: {notify_error}")


