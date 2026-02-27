import asyncio
import random

def register_home_handlers(app):
    # Listen for the Home Tab opening
    @app.event("app_home_opened")
    async def update_home_tab(client, event, logger):
        try:
            await client.views_publish(
                user_id=event["user"],
                view={

    "type": "home",
    "blocks": [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": " Yarooms Booking Dashboard",
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Welcome! Use the options below to find and book a free room."
                }
            ]
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "* Обирай час, а кімнату знайде бот*\n_Вкажи потрібний час, і ми підберемо найкращий варіант._"
            },
            "accessory": {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": " Book time",
                },
                "style": "primary",
                "value": "book_time",
                "action_id": "action_book_time"
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "* Вибери кімнату та число*\n_Перевір розклад улюбленої кімнати та знайди вільні вікна._"
            },
            "accessory": {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "📅 Book room",
                },
                "style": "primary",
                "value": "book_room",
                "action_id": "action_book_room"
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Вільний спейс прямо на зараз*\n_Потрібне місце негайно? Бронюй в один клік._"
            },
            "accessory": {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "⚡ Hot Booking",
                },
                "style": "primary",
                "value": "hot_booking",
                "action_id": "action_hot_booking"
            }
        }
    ]

                }
            )
        except Exception as e:
            logger.error(f"Error publishing home tab: {e}")



    @app.action("action_book_time")
    async def open_book_time_modal(ack, body, client, logger):
        await ack()
        try:
            # 2. Open the modal using the trigger_id from the button click
            await client.views_open(
                trigger_id=body["trigger_id"],
                view={
    "type": "modal",
    "callback_id": "modal_book_time_submit",
    "title": {
        "type": "plain_text",
        "text": "Book by Time",
    },
    "submit": {
        "type": "plain_text",
        "text": "Find Room",
    },
    "close": {
        "type": "plain_text",
        "text": "Cancel",
    },
    "blocks": [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Select the date and time you need a workspace. The system will automatically find an available room for you."
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "input",
            "block_id": "block_date",
            "element": {
                "type": "datepicker",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select a date",
                },
                "action_id": "action_date"
            },
            "label": {
                "type": "plain_text",
                "text": "Date",
            }
        },
        {
            "type": "input",
            "block_id": "block_start_time",
            "element": {
                "type": "timepicker",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select start time",
                },
                "action_id": "action_start_time"
            },
            "label": {
                "type": "plain_text",
                "text": "Start Time",
            }
        },
        {
            "type": "input",
            "block_id": "block_end_time",
            "element": {
                "type": "timepicker",
                "placeholder": {
                    "type": "plain_text",
                    "text": "Select end time",
                },
                "action_id": "action_end_time"
            },
            "label": {
                "type": "plain_text",
                "text": "End Time",
            }
        }
    ]
}

            )
        except Exception as e:
            logger.error(f"Error opening modal: {e}")


    @app.view("modal_book_time_submit")
    async def handle_book_time_submission(ack, body, client, view, logger):
        # Extract data from user
        state_values = view["state"]["values"]

        selected_date = state_values["block_date"]["action_date"]["selected_date"]
        start_time = state_values["block_start_time"]["action_start_time"]["selected_time"]
        end_time = state_values["block_end_time"]["action_end_time"]["selected_time"]


        # upload skeleton while searching
        await ack(response_action="update", view=skeleton_view("Searching"))

        # 4. Execute your background task (Yarooms API)
        try:
            # We use asyncio.sleep to simulate the time it takes to call the Yarooms API
            await asyncio.sleep(3)

            # Simulate getting available rooms and picking a random one
            # (Replace this with your actual Yarooms GET and POST requests)
            available_rooms = ["Conference Room A", "Focus Pod B", "Meeting Room C"]
            booked_room = random.choice(available_rooms)

            # 5. Build the Final "Success" View
            success_view = {
                "type": "modal",
                "title": {
                    "type": "plain_text",
                    "text": "Room Booked!",
                    "emoji": False
                },
                "close": {
                    "type": "plain_text",
                    "text": "Awesome",
                    "emoji": False
                },
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🎉 *Success!*\n\nWe successfully booked *{booked_room}* for you."
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"📅 *Date:* {selected_date} | ⏰ *Time:* {start_time} - {end_time}"
                            }
                        ]
                    }
                ]
            }

            # 6. PUSH the final view to the user using the modal's unique ID
            await client.views_update(
                view_id=body["view"]["id"],
                view=success_view
            )

        except Exception as e:
            logger.error(f"Error during background booking: {e}")

            # If the Yarooms API fails, push an Error View instead
            error_view = {
                "type": "modal",
                "title": {"type": "plain_text", "text": "Booking Failed", "emoji": False},
                "close": {"type": "plain_text", "text": "Close", "emoji": False},
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn",
                                 "text": "❌ Sorry, we couldn't book a room right now or no rooms were available. Please try again later."}
                    }
                ]
            }
            await client.views_update(view_id=body["view"]["id"], view=error_view)

    @app.action("action_book_room")
    async def open_book_room_modal(ack, body, client, logger):
        # 1. Acknowledge the button click immediately
        await ack()

        try:
            # 2. Open the modal using the trigger_id
            await client.views_open(
                trigger_id=body["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": "modal_book_room_submit",
                    "title": {
                        "type": "plain_text",
                        "text": "Book by Room",
                        "emoji": False
                    },
                    "submit": {
                        "type": "plain_text",
                        "text": "Check Schedule",
                        "emoji": False
                    },
                    "close": {
                        "type": "plain_text",
                        "text": "Cancel",
                        "emoji": False
                    },
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Select a specific room and date to see its available time slots."
                            }
                        },
                        {
                            "type": "divider"
                        },
                        {
                            "type": "input",
                            "block_id": "block_room",
                            "element": {
                                "type": "static_select",
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "Select a room",
                                    "emoji": False
                                },
                                "options": [
                                    {
                                        "text": {
                                            "type": "plain_text",
                                            "text": "Conference Room A",
                                            "emoji": False
                                        },
                                        "value": "roomA"
                                    },
                                    {
                                        "text": {
                                            "type": "plain_text",
                                            "text": "Focus Pod B",
                                            "emoji": False
                                        },
                                        "value": "roomB"
                                    },
                                    {
                                        "text": {
                                            "type": "plain_text",
                                            "text": "Meeting Room C",
                                            "emoji": False
                                        },
                                        "value": "roomC"
                                    }
                                ],
                                "action_id": "action_room"
                            },
                            "label": {
                                "type": "plain_text",
                                "text": "Which room?",
                                "emoji": False
                            }
                        },
                        {
                            "type": "input",
                            "block_id": "block_room_date",
                            "element": {
                                "type": "datepicker",
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "Select a date",
                                    "emoji": False
                                },
                                "action_id": "action_room_date"
                            },
                            "label": {
                                "type": "plain_text",
                                "text": "On which date?",
                                "emoji": False
                            }
                        }
                    ]
                }
            )
        except Exception as e:
            logger.error(f"Error opening book room modal: {e}")

        @app.view("modal_book_room_submit")
        async def handle_book_room_submission(ack, body, client, view, logger):
            await ack(response_action="update", view=skeleton_view("Searching"))

            # 2. Extract the user's selected room and date
            state_values = view["state"]["values"]

            try:
                # For a static_select, drill into 'selected_option'
                selected_option = state_values["block_room"]["action_room"]["selected_option"]
                room_id = selected_option["value"]
                room_name = selected_option["text"]["text"]

                # For the datepicker, grab the 'selected_date'
                selected_date = state_values["block_room_date"]["action_room_date"]["selected_date"]

                # 3. Call your Yarooms API logic here using room_id and selected_date
                # ...

                # 4. Build the view showing available slots
                # In your actual app, you will loop through the API response to generate these blocks
                schedule_view = {
                    "type": "modal",
                    "title": {
                        "type": "plain_text",
                        "text": "Available Slots",
                        "emoji": False
                    },
                    "close": {
                        "type": "plain_text",
                        "text": "Close",
                        "emoji": False
                    },
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"Schedule for *{room_name}* on *{selected_date}*:"
                            }
                        },
                        {
                            "type": "divider"
                        },
                        # Example Slot Block
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "*10:00 - 11:00*"
                            },
                            "accessory": {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Book Slot",
                                    "emoji": False
                                },
                                "style": "primary",
                                # Tip: Pack the data into the value string to use in the next step!
                                "value": f"{room_id}_10:00_11:00",
                                "action_id": "action_book_specific_slot"
                            }
                        }
                    ]
                }

                # 5. Push the schedule view to the user using views_update
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=schedule_view
                )

            except Exception as e:
                logger.error(f"Error handling room schedule submission: {e}")

    @app.action("action_book_specific_slot")
    async def handle_book_specific_slot(ack, body, client, logger):
        # 1. Acknowledge the button click immediately
        await ack()

        try:
            # 2. Extract the value string from the button that was clicked
            # body["actions"] is a list of all actions in this event (usually just one)
            action = body["actions"][0]
            value_string = action["value"]

            # 3. Unpack the data
            # This turns "room123_10:00_11:00" into three separate variables
            room_id, start_time, end_time = value_string.split("_")
            user_id = body["user"]["id"]

            # 4. Call your Yarooms API POST request here
            # Example:
            # success = await book_yarooms_space(room_id, start_time, end_time, user_email)

            # 5. Build the final Success View
            success_view = {
                "type": "modal",
                "title": {
                    "type": "plain_text",
                    "text": "Booking Confirmed",
                    "emoji": False
                },
                "close": {
                    "type": "plain_text",
                    "text": "Done",
                    "emoji": False
                },
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"Success! You have booked the room from *{start_time}* to *{end_time}*."
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "Your reservation has been added to Yarooms."
                            }
                        ]
                    }
                ]
            }

            # 6. Update the current modal to show the success message
            await client.views_update(
                view_id=body["view"]["id"],
                view=success_view
            )

        except Exception as e:
            logger.error(f"Error booking specific slot: {e}")

            # Push an error view if something goes wrong (e.g., someone else just booked it)
            error_view = {
                "type": "modal",
                "title": {"type": "plain_text", "text": "Booking Failed", "emoji": False},
                "close": {"type": "plain_text", "text": "Close", "emoji": False},
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn",
                                 "text": "Sorry, we couldn't complete this booking. The slot might no longer be available."}
                    }
                ]
            }
            await client.views_update(view_id=body["view"]["id"], view=error_view)

    def skeleton_view(word):
        return {
            "type": "home",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⏳ {word}..."
                    }
                }
            ]
        }






