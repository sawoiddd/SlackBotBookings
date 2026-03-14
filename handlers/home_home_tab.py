def _home_action_block(text: str, button_text: str, value: str, action_id: str) -> dict:
    """Build a standard Home tab section with an action button."""
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": text},
        "accessory": {
            "type": "button",
            "text": {"type": "plain_text", "text": button_text},
            "style": "primary",
            "value": value,
            "action_id": action_id,
        },
    }


def build_home_tab_view() -> dict:
    """Return the full Home tab view payload."""
    return {
        "type": "home",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": " Yarooms Booking Dashboard"},
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Welcome! Use the options below to find and book a free room.",
                    }
                ],
            },
            {"type": "divider"},
            _home_action_block(
                text="* Обирай час, а кімнату знайде бот*\n_Вкажи потрібний час, і ми підберемо найкращий варіант._",
                button_text=" Book time",
                value="book_time",
                action_id="action_book_time",
            ),
            {"type": "divider"},
            _home_action_block(
                text="* Вибери кімнату та число*\n_Перевір розклад улюбленої кімнати та знайди вільні вікна._",
                button_text="📅 Book room",
                value="book_room",
                action_id="action_book_room",
            ),
            {"type": "divider"},
            _home_action_block(
                text="*Вільний спейс прямо на зараз*\n_Потрібне місце негайно? Бронюй в один клік._",
                button_text="⚡ Hot Booking",
                value="hot_booking",
                action_id="action_hot_booking",
            ),
        ],
    }


def register_home_tab_handlers(app):
    """Register handlers related to Home tab rendering."""

    @app.event("app_home_opened")
    async def update_home_tab(client, event, logger):
        """Publish the app Home tab with booking entry points."""
        try:
            await client.views_publish(
                user_id=event["user"],
                view=build_home_tab_view(),
            )
        except Exception as e:
            logger.error(f"Error publishing home tab: {e}")


