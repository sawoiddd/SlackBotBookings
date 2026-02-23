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
    async def book_time_button(ack, body, client):
        await ack()






