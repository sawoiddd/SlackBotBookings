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



    # @app.action("action_book_time")
    # async def book_time_button(ack, body, client):
    #     await ack()
    #
    #     user_id = body["user"]["id"]

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






