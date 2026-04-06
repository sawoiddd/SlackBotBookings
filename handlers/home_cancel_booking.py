"""Booking cancellation action handler for DM confirmation messages."""

import json

import handlers.home_common as common


def register_cancel_booking_handlers(app, yarooms, quota):
    """Register handler for `action_cancel_booking` button clicks in DMs."""

    @app.action("action_cancel_booking")
    async def handle_cancel_booking(ack, body, client, logger):
        """Cancel an existing Yarooms booking from DM button action."""
        await ack()

        action = (body.get("actions") or [{}])[0]
        raw_value = str(action.get("value") or "")
        user_id = body.get("user", {}).get("id", "")

        try:
            payload = json.loads(raw_value)
        except Exception:
            payload = {"booking_id": raw_value}

        booking_id = str(payload.get("booking_id") or "").strip()
        booking_date = str(payload.get("booking_date") or "").strip()
        start_time = str(payload.get("start_time") or "").strip()
        end_time = str(payload.get("end_time") or "").strip()
        room_name = str(payload.get("room_name") or "Кімната").strip()
        user_email = str(payload.get("user_email") or "").strip()
        payload_user_id = str(payload.get("user_id") or "").strip()

        if payload_user_id and payload_user_id != user_id:
            await client.chat_postMessage(
                channel=user_id,
                text="❌ Ви можете скасувати лише власне бронювання.",
            )
            return

        if not booking_id:
            await client.chat_postMessage(
                channel=user_id,
                text="❌ Відсутній ID бронювання. Неможливо скасувати.",
            )
            return

        try:
            cancelled = await yarooms.delete_booking(booking_id)
        except Exception as exc:
            logger.error(
                f"Cancel booking failed: booking_id={booking_id}, user={user_id}, "
                f"err={type(exc).__name__}: {exc}"
            )
            cancelled = False

        if not cancelled:
            await client.chat_postMessage(
                channel=user_id,
                text=(
                    "❌ Не вдалося скасувати бронювання зараз. "
                    "Можливо, воно вже скасоване або недоступне."
                ),
            )
            return

        # Free daily quota after a successful cancellation.
        duration = common._duration_minutes(start_time, end_time)
        if user_email and booking_date and duration > 0:
            try:
                await quota.record_cancellation(user_email, booking_date, duration)
            except Exception as exc:
                logger.warning(
                    f"Quota rollback failed after cancellation: user_email={user_email}, "
                    f"date={booking_date}, minutes={duration}, err={type(exc).__name__}: {exc}"
                )

        await client.chat_postMessage(
            channel=user_id,
            text=(
                f"🗑️ Бронювання скасовано: {room_name} на {booking_date} "
                f"{start_time}-{end_time}."
            ),
        )

        # Best-effort: replace original DM button message with cancelled state.
        try:
            channel_id = body.get("channel", {}).get("id")
            message_ts = body.get("container", {}).get("message_ts")
            if channel_id and message_ts:
                await client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    text="Бронювання скасовано.",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"🗑️ *Скасовано:* {room_name}\n"
                                    f"Дата: {booking_date}\n"
                                    f"Час: {start_time}-{end_time}"
                                ),
                            },
                        }
                    ],
                )
        except Exception as exc:
            logger.debug(f"Could not update original DM cancellation message: {exc}")

