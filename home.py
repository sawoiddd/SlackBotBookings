from clients.yarooms_client import YaroomsClient

from handlers.home_book_room import register_book_room_handlers
from handlers.home_book_time import register_book_time_handlers
from handlers.home_home_tab import register_home_tab_handlers
from handlers.home_hot_booking import register_hot_booking_handlers


def register_home_handlers(app, config: dict):
    """Create shared clients and register all Slack handlers."""
    yarooms = YaroomsClient(
        api_key=config.get("yarooms-api-key", ""),
        base_url=config.get("yarooms-base-url", "https://api.yarooms.com"),
    )

    register_home_tab_handlers(app)
    register_book_time_handlers(app, yarooms)
    register_book_room_handlers(app, yarooms)
    register_hot_booking_handlers(app, yarooms)
