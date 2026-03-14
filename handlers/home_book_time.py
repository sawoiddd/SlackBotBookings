import handlers.home_common as common


def register_book_time_handlers(app, yarooms):
    """Register Book by Time action/view handlers."""

    @app.action("action_book_time")
    async def open_book_time_modal(ack, body, client, logger):
        """Open the Book by Time modal."""
        await ack()
        try:
            await client.views_open(
                trigger_id=body["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": "modal_book_time_submit",
                    "title": {"type": "plain_text", "text": "Book by Time"},
                    "submit": {"type": "plain_text", "text": "Find Room"},
                    "close": {"type": "plain_text", "text": "Cancel"},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Select the date and time you need a workspace. The system will automatically find an available room for you.",
                            },
                        },
                        {"type": "divider"},
                        {
                            "type": "input",
                            "block_id": "block_date",
                            "element": {
                                "type": "datepicker",
                                "placeholder": {"type": "plain_text", "text": "Select a date"},
                                "action_id": "action_date",
                            },
                            "label": {"type": "plain_text", "text": "Date"},
                        },
                        {
                            "type": "input",
                            "block_id": "block_start_time",
                            "element": {
                                "type": "static_select",
                                "placeholder": {"type": "plain_text", "text": "Select start time"},
                                "options": common._available_time_options(),
                                "action_id": "action_start_time",
                            },
                            "label": {"type": "plain_text", "text": "Start Time"},
                        },
                        {
                            "type": "input",
                            "block_id": "block_end_time",
                            "element": {
                                "type": "static_select",
                                "placeholder": {"type": "plain_text", "text": "Select end time"},
                                "options": common._available_time_options(),
                                "action_id": "action_end_time",
                            },
                            "label": {"type": "plain_text", "text": "End Time"},
                        },
                    ],
                },
            )
        except Exception as e:
            logger.error(f"Error opening modal: {e}")

    @app.view("modal_book_time_submit")
    async def handle_book_time_submission(ack, body, client, view, logger):
        """Validate and process Book by Time submission."""
        state_values = view["state"]["values"]
        selected_date = state_values["block_date"]["action_date"]["selected_date"]
        start_time = state_values["block_start_time"]["action_start_time"]["selected_option"]["value"]
        end_time = state_values["block_end_time"]["action_end_time"]["selected_option"]["value"]
        user_id = body["user"]["id"]

        duration = common._duration_minutes(start_time, end_time)
        if duration <= 0:
            await ack(
                response_action="errors",
                errors={"block_end_time": "End time must be after start time."},
            )
            return
        if duration > common.MAX_BOOKING_MINUTES:
            await ack(
                response_action="errors",
                errors={"block_end_time": f"Booking cannot be longer than {common.MAX_BOOKING_HOURS} hours per booking."},
            )
            return

        await ack(response_action="update", view=common.skeleton_view("Searching"))

        try:
            user_email = await common.get_user_email(client, user_id)

            space = await yarooms.find_available_space(selected_date, start_time, end_time)
            if space is None:
                raise RuntimeError("No rooms available for the selected time slot.")

            await yarooms.create_booking(
                space_id=space["id"],
                date=selected_date,
                start_time=start_time,
                end_time=end_time,
                user_email=user_email,
            )

            await client.views_update(
                view_id=body["view"]["id"],
                view={
                    "type": "modal",
                    "title": {"type": "plain_text", "text": "Room Booked!", "emoji": False},
                    "close": {"type": "plain_text", "text": "Awesome", "emoji": False},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"🎉 *Success!*\n\nWe successfully booked *{space['name']}* for you.",
                            },
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"📅 *Date:* {selected_date} | ⏰ *Time:* {start_time} - {end_time}",
                                }
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
                booking_date=selected_date,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as e:
            logger.error(f"Error during background booking: {e}")
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
                                "text": "❌ Sorry, we couldn't book a room right now or no rooms were available. Please try again later.",
                            },
                        }
                    ],
                },
            )


