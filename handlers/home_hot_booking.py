"""Hot Booking — instantly books the first available room for the next
30 minutes from now.
"""

from datetime import datetime, timedelta

import handlers.home_common as common


def register_hot_booking_handlers(app, yarooms, quota):
    """Register Hot Booking action handler."""

    def _round_up_to_10_minute_boundary(dt: datetime) -> datetime:
        """Round datetime up to the next 10-minute boundary (seconds zeroed)."""
        base = dt.replace(second=0, microsecond=0)
        rem = base.minute % 10
        if rem == 0:
            return base
        return base + timedelta(minutes=(10 - rem))

    @app.action("action_hot_booking")
    async def handle_hot_booking(ack, body, client, logger):
        """Try to instantly book any room available for the next 30 minutes."""
        await ack()
        try:
            response = await client.views_open(
                trigger_id=body["trigger_id"],
                view=common.skeleton_view("Пошук кімнати"),
            )
            new_view_id = response["view"]["id"]
            user_id = body["user"]["id"]

            # Yarooms booking strategies commonly require fixed minute steps.
            # Align Hot Booking start/end to 10-minute boundaries to avoid 400s.
            start_dt = _round_up_to_10_minute_boundary(datetime.now())
            end_dt = start_dt + timedelta(minutes=30)

            # Cross-midnight is unsupported by create_booking(date + HH:MM pair).
            if end_dt.date() != start_dt.date():
                await client.views_update(
                    view_id=new_view_id,
                    view=common.simple_modal(
                        "Швидке бронювання",
                        "⚠️ Швидке бронювання недоступне біля опівночі. Скористайтеся бронюванням за часом.",
                    ),
                )
                return

            today = start_dt.strftime("%Y-%m-%d")
            start_time = start_dt.strftime("%H:%M")
            end_time = end_dt.strftime("%H:%M")

            user_email = await common.get_user_email(client, user_id)
            logger.debug(f"Hot Booking resolved email for {user_id}: '{user_email}'")

            # ── Daily quota check ─────────────────────────────────────────
            booking_duration = 30
            if user_email:
                allowed, used, remaining = await quota.check_quota(
                    user_email, today, booking_duration,
                )
                if not allowed:
                    await client.views_update(
                        view_id=new_view_id,
                        view=common.quota_exceeded_modal(
                            used, remaining, booking_duration,
                            common.MAX_DAILY_BOOKING_MINUTES,
                        ),
                    )
                    return

            # Find first room that is truly free (bookings-based check)
            spaces = await yarooms.get_spaces_cached()
            space = None
            for candidate in spaces:
                cid = str(candidate.get("id") or candidate.get("spaceId") or "")
                if not cid:
                    continue
                try:
                    if await yarooms.is_interval_free(cid, today, start_time, end_time):
                        space = candidate
                        break
                except Exception:
                    continue

            if space is None:
                raise RuntimeError("Наразі немає вільних кімнат.")

            booking_result = await yarooms.create_booking(
                space_id=space["id"],
                date=today,
                start_time=start_time,
                end_time=end_time,
                user_email=user_email,
                title="Швидке бронювання через Slack",
            )

            # ── Record quota ONLY after successful booking ────────────────
            if user_email:
                await quota.record_booking(user_email, today, booking_duration)

            booking_id = yarooms.extract_booking_id(booking_result)

            await client.views_update(
                view_id=new_view_id,
                view={
                    "type": "modal",
                    "title": {"type": "plain_text", "text": "Кімнату заброньовано", "emoji": False},
                    "close": {"type": "plain_text", "text": "Готово", "emoji": False},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"⚡ *{space['name']}* ваша до *{end_time}*!",
                            },
                        },
                        {
                            "type": "context",
                            "elements": [
                                {"type": "mrkdwn", "text": "Ваш розклад у Yarooms оновлено."}
                            ],
                        },
                    ],
                },
            )

            await common.notify_booking_in_chat(
                client=client,
                logger=logger,
                user_id=user_id,
                room_name=space.get("name", space.get("id", "Невідома кімната")),
                booking_date=today,
                start_time=start_time,
                end_time=end_time,
                booking_id=booking_id,
                user_email=user_email,
            )
        except Exception as e:
            logger.error(
                f"Error processing hot booking: user={body.get('user', {}).get('id', 'unknown')}, "
                f"err={type(e).__name__}: {e}"
            )
            await client.chat_postMessage(
                channel=body["user"]["id"],
                text="На жаль, зараз не вдалося виконати швидке бронювання.",
            )
