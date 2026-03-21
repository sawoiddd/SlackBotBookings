"""Book by Room — user picks a specific room and date, sees its available
slots schedule, and taps a slot to book.  Past slots are filtered out and a
live re-check is performed before create_booking.
"""

from datetime import datetime

import handlers.home_common as common


def register_book_room_handlers(app, yarooms):
    """Register Book by Room and slot-booking handlers."""

    def _get_cache_meta() -> dict:
        """Fetch Yarooms cache metadata (safe for logging)."""
        fn = getattr(yarooms, "get_spaces_cache_meta", None)
        return fn() if callable(fn) else {}

    @app.action("action_book_room")
    async def open_book_room_modal(ack, body, client, logger):
        """Open Book by Room modal with cached Yarooms list and explicit error state."""
        await ack()
        try:
            options = []
            load_error_text = ""
            try:
                logger.debug(f"Yarooms spaces cache meta(before): {_get_cache_meta()}")

                spaces = await yarooms.get_spaces_cached()
                if not spaces:
                    spaces = await yarooms.get_spaces_cached(
                        force_refresh=True,
                        allow_stale_on_error=False,
                    )

                for space in spaces:
                    room_id = space.get("id") or space.get("spaceId")
                    room_name = space.get("name") or space.get("title")
                    if room_id and room_name:
                        options.append(
                            {
                                "text": {"type": "plain_text", "text": room_name, "emoji": False},
                                "value": str(room_id),
                            }
                        )
                if not options:
                    raise RuntimeError("Yarooms returned no selectable spaces.")
            except Exception as api_err:
                logger.error(
                    f"Could not fetch Yarooms spaces: error={api_err}; cache_meta={_get_cache_meta()}"
                )
                load_error_text = str(api_err)

            logger.info(f"Book by Room options: count={len(options)}")
            if options:
                logger.debug(f"Yarooms spaces cache meta(after): {_get_cache_meta()}")

            if not options:
                await client.views_open(
                    trigger_id=body["trigger_id"],
                    view=common.error_modal_with_context(
                        "Book by Room",
                        "❌ Could not load rooms from Yarooms right now. Please try again in a few seconds.",
                        [f"Details: `{load_error_text[:120]}`" if load_error_text else "Details: unavailable"],
                    ),
                )
                return

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

            # Drop slots whose start time has already passed
            available_slots = [
                (s, e) for s, e in available_slots
                if not common._is_past_slot(selected_date, s)
            ]

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
                slot_blocks = [
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
                    for start, end in available_slots
                ]

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
                view=common.simple_modal(
                    "Error",
                    "❌ Could not load the room schedule. Please try again.",
                ),
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
                    view=common.simple_modal(
                        "Booking Rejected",
                        f"❌ This slot exceeds the *{common.MAX_BOOKING_HOURS}-hour* per-booking limit and cannot be booked.",
                    ),
                )
                return

            booking_date = body["view"].get("private_metadata") or datetime.now().strftime("%Y-%m-%d")

            if common._is_past_slot(booking_date, start_time):
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=common.simple_modal(
                        "Time Passed",
                        "❌ This time slot has already passed. Please refresh the schedule and choose a future slot.",
                    ),
                )
                return

            try:
                latest_slots = await yarooms.get_space_availability(room_id, booking_date)
            except Exception as avail_err:
                logger.warning(
                    f"Book by Room re-check failed: room={room_id}, date={booking_date}, "
                    f"err={type(avail_err).__name__}: {avail_err}"
                )
                latest_slots = []

            latest_available = common._normalized_available_slots(latest_slots)
            still_available = any(
                common._covers_interval(available_slot, start_time, end_time)
                for available_slot in latest_available
            )
            if not still_available:
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=common.simple_modal(
                        "Slot Unavailable",
                        "❌ This slot is no longer available. Please refresh the schedule and choose another one.",
                    ),
                )
                return

            user_email = await common.get_user_email(client, user_id)
            logger.debug(f"Book by Room resolved email for {user_id}: '{user_email}'")

            try:
                await yarooms.create_booking(
                    space_id=room_id,
                    date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    user_email=user_email,
                )
            except Exception as book_err:
                logger.error(
                    f"Book by Room create_booking failed: room={room_id}, date={booking_date}, "
                    f"start={start_time}, end={end_time}, err={type(book_err).__name__}: {book_err}"
                )
                error_detail = str(book_err)[:120]
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=common.error_modal_with_context(
                        "Booking Failed",
                        "❌ The room could not be booked — it may have just been taken. Please try again.",
                        [f"Details: `{error_detail}`"],
                    ),
                )
                return

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
                view=common.simple_modal(
                    "Booking Failed",
                    "Sorry, we couldn't complete this booking. The slot might no longer be available.",
                ),
            )
