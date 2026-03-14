from datetime import datetime

import handlers.home_common as common


def register_book_room_handlers(app, yarooms):
    """Register Book by Room and slot-booking handlers."""

    @app.action("action_book_room")
    async def open_book_room_modal(ack, body, client, logger):
        """Open Book by Room modal with live room list."""
        await ack()
        try:
            try:
                spaces = await yarooms.get_spaces()
                options = [
                    {
                        "text": {"type": "plain_text", "text": s["name"], "emoji": False},
                        "value": s["id"],
                    }
                    for s in spaces
                ]
            except Exception as api_err:
                logger.warning(f"Could not fetch Yarooms spaces, using static fallback: {api_err}")
                options = [
                    {"text": {"type": "plain_text", "text": "Conference Room A", "emoji": False}, "value": "roomA"},
                    {"text": {"type": "plain_text", "text": "Focus Pod B", "emoji": False}, "value": "roomB"},
                    {"text": {"type": "plain_text", "text": "Meeting Room C", "emoji": False}, "value": "roomC"},
                ]

            await client.views_open(
                trigger_id=body["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": "modal_book_room_submit",
                    "title": {"type": "plain_text", "text": "Book by Room", "emoji": False},
                    "submit": {"type": "plain_text", "text": "Check Schedule", "emoji": False},
                    "close": {"type": "plain_text", "text": "Cancel", "emoji": False},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Select a specific room and date to see its available time slots.",
                            },
                        },
                        {"type": "divider"},
                        {
                            "type": "input",
                            "block_id": "block_room",
                            "element": {
                                "type": "static_select",
                                "placeholder": {"type": "plain_text", "text": "Select a room", "emoji": False},
                                "options": options,
                                "action_id": "action_room",
                            },
                            "label": {"type": "plain_text", "text": "Which room?", "emoji": False},
                        },
                        {
                            "type": "input",
                            "block_id": "block_room_date",
                            "element": {
                                "type": "datepicker",
                                "placeholder": {"type": "plain_text", "text": "Select a date", "emoji": False},
                                "action_id": "action_room_date",
                            },
                            "label": {"type": "plain_text", "text": "On which date?", "emoji": False},
                        },
                    ],
                },
            )
        except Exception as e:
            logger.error(f"Error opening book room modal: {e}")

    @app.view("modal_book_room_submit")
    async def handle_book_room_submission(ack, body, client, view, logger):
        """Show currently available slots for a selected room/date."""
        await ack(response_action="update", view=common.skeleton_view("Searching"))
        state_values = view["state"]["values"]
        try:
            selected_option = state_values["block_room"]["action_room"]["selected_option"]
            room_id = selected_option["value"]
            room_name = selected_option["text"]["text"]
            selected_date = state_values["block_room_date"]["action_room_date"]["selected_date"]

            slots = await yarooms.get_space_availability(room_id, selected_date)
            available_slots = common._normalized_available_slots(slots)

            if not available_slots:
                slot_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "😕 No free slots found for this room on the selected date.",
                        },
                    }
                ]
            else:
                slot_blocks = []
                for start, end in available_slots:
                    slot_blocks.append(
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": f"*{start} – {end}*"},
                            "accessory": {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Book Slot", "emoji": False},
                                "style": "primary",
                                "value": f"{room_id}_{start}_{end}",
                                "action_id": "action_book_specific_slot",
                            },
                        }
                    )

            await client.views_update(
                view_id=body["view"]["id"],
                view={
                    "type": "modal",
                    "title": {"type": "plain_text", "text": "Available Slots", "emoji": False},
                    "close": {"type": "plain_text", "text": "Close", "emoji": False},
                    "private_metadata": selected_date,
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"Schedule for *{room_name}* on *{selected_date}*:",
                            },
                        },
                        {"type": "divider"},
                        *slot_blocks,
                    ],
                },
            )
        except Exception as e:
            logger.error(f"Error handling room schedule submission: {e}")
            await client.views_update(
                view_id=body["view"]["id"],
                view={
                    "type": "modal",
                    "title": {"type": "plain_text", "text": "Error", "emoji": False},
                    "close": {"type": "plain_text", "text": "Close", "emoji": False},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "❌ Could not load the room schedule. Please try again.",
                            },
                        }
                    ],
                },
            )

    @app.action("action_book_specific_slot")
    async def handle_book_specific_slot(ack, body, client, logger):
        """Book one selected slot from the room schedule modal."""
        await ack()
        try:
            action = body["actions"][0]
            room_id, start_time, end_time = action["value"].rsplit("_", 2)
            user_id = body["user"]["id"]

            duration = common._duration_minutes(start_time, end_time)
            if duration <= 0 or duration > common.MAX_BOOKING_MINUTES:
                await client.views_update(
                    view_id=body["view"]["id"],
                    view={
                        "type": "modal",
                        "title": {"type": "plain_text", "text": "Booking Rejected", "emoji": False},
                        "close": {"type": "plain_text", "text": "Close", "emoji": False},
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"❌ This slot exceeds the *{common.MAX_BOOKING_HOURS}-hour* per-booking limit and cannot be booked.",
                                },
                            }
                        ],
                    },
                )
                return

            booking_date = body["view"].get("private_metadata") or datetime.now().strftime("%Y-%m-%d")

            user_email = await common.get_user_email(client, user_id)

            latest_slots = await yarooms.get_space_availability(room_id, booking_date)
            latest_available = common._normalized_available_slots(latest_slots)
            still_available = any(
                common._covers_interval(available_slot, start_time, end_time)
                for available_slot in latest_available
            )
            if not still_available:
                await client.views_update(
                    view_id=body["view"]["id"],
                    view={
                        "type": "modal",
                        "title": {"type": "plain_text", "text": "Slot Unavailable", "emoji": False},
                        "close": {"type": "plain_text", "text": "Close", "emoji": False},
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "❌ This slot is no longer available. Please refresh the schedule and choose another one.",
                                },
                            }
                        ],
                    },
                )
                return

            await yarooms.create_booking(
                space_id=room_id,
                date=booking_date,
                start_time=start_time,
                end_time=end_time,
                user_email=user_email,
            )

            room_name = await common.safe_get_room_name(yarooms, room_id)

            await client.views_update(
                view_id=body["view"]["id"],
                view={
                    "type": "modal",
                    "title": {"type": "plain_text", "text": "Booking Confirmed", "emoji": False},
                    "close": {"type": "plain_text", "text": "Done", "emoji": False},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"✅ You have booked the room from *{start_time}* to *{end_time}* on *{booking_date}*.",
                            },
                        },
                        {
                            "type": "context",
                            "elements": [
                                {"type": "mrkdwn", "text": "Your reservation has been added to Yarooms."}
                            ],
                        },
                    ],
                },
            )

            await common.notify_booking_in_chat(
                client=client,
                logger=logger,
                user_id=user_id,
                room_name=room_name,
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as e:
            logger.error(f"Error booking specific slot: {e}")
            await client.views_update(
                view_id=body["view"]["id"],
                view={
                    "type": "modal",
                    "title": {"type": "plain_text", "text": "Booking Failed", "emoji": False},
                    "close": {"type": "plain_text", "text": "Close", "emoji": False},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Sorry, we couldn't complete this booking. The slot might no longer be available.",
                            },
                        }
                    ],
                },
            )


