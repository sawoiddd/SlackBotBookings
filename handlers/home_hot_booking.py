"""Hot Booking — instantly books the first available room for the next
30 minutes from now.
"""

from datetime import datetime, timedelta

import handlers.home_common as common


def register_hot_booking_handlers(app, yarooms):
    """Register Hot Booking action handler."""

    @app.action("action_hot_booking")
    async def handle_hot_booking(ack, body, client, logger):
        """Try to instantly book any room available for the next 30 minutes."""
        await ack()
        try:
            response = await client.views_open(
                trigger_id=body["trigger_id"],
                view=common.skeleton_view("Finding a room"),
            )
            new_view_id = response["view"]["id"]
            user_id = body["user"]["id"]

            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            start_time = now.strftime("%H:%M")
            end_time = (now + timedelta(minutes=30)).strftime("%H:%M")

            space = await yarooms.find_available_space(today, start_time, end_time)
            if space is None:
                raise RuntimeError("No rooms available right now.")

            user_email = await common.get_user_email(client, user_id)
            logger.debug(f"Hot Booking resolved email for {user_id}: '{user_email}'")

            await yarooms.create_booking(
                space_id=space["id"],
                date=today,
                start_time=start_time,
                end_time=end_time,
                user_email=user_email,
                title="Hot Booking via Slack",
            )

            await client.views_update(
                view_id=new_view_id,
                view={
                    "type": "modal",
                    "title": {"type": "plain_text", "text": "Room Booked", "emoji": False},
                    "close": {"type": "plain_text", "text": "Done", "emoji": False},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"⚡ *{space['name']}* is yours until *{end_time}*!",
                            },
                        },
                        {
                            "type": "context",
                            "elements": [
                                {"type": "mrkdwn", "text": "Your Yarooms schedule has been updated."}
                            ],
                        },
                    ],
                },
            )

            await common.notify_booking_in_chat(
                client=client,
                logger=logger,
                user_id=user_id,
                room_name=space.get("name", space.get("id", "Unknown room")),
                booking_date=today,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as e:
            logger.error(f"Error processing hot booking: {e}")
            await client.chat_postMessage(
                channel=body["user"]["id"],
                text="Sorry, we couldn't complete the hot booking right now.",
            )
