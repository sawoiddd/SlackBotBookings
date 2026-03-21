"""Thin orchestrator — builds the YaroomsClient (with optional Redis cache),
warms the spaces cache, creates the DailyQuotaTracker, and registers all
feature-specific Slack handler modules.
"""

import logging

from clients.yarooms_client import YaroomsClient
from utils.daily_quota import DailyQuotaTracker

from handlers.home_book_room import register_book_room_handlers
from handlers.home_book_time import register_book_time_handlers
from handlers.home_home_tab import register_home_tab_handlers
from handlers.home_hot_booking import register_hot_booking_handlers

logger = logging.getLogger(__name__)


async def _build_redis_client(redis_url: str):
    """Create and verify an async Redis client. Returns None if unavailable."""
    if not redis_url:
        return None
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(redis_url, decode_responses=True)
        await client.ping()
        logger.info(f"Redis cache connected: {redis_url}")
        return client
    except Exception as exc:
        logger.warning(f"Redis unavailable ({exc}); falling back to in-memory cache.")
        return None


async def register_home_handlers(app, config: dict):
    """Create shared clients and register all Slack handlers.

    Supports two Yarooms auth modes (checked in order):
      1. ``yarooms-api-key`` is non-empty → use it directly as the bearer token.
      2. ``yarooms-email`` + ``yarooms-password`` → call
         :meth:`YaroomsClient.from_credentials` to obtain a token at startup.
    """
    api_key   = config.get("yarooms-api-key", "")
    base_url  = config.get("yarooms-base-url", "https://api.yarooms.com")

    if api_key:
        yarooms = YaroomsClient(api_key=api_key, base_url=base_url)
    else:
        yarooms = await YaroomsClient.from_credentials(
            email=config["yarooms-email"],
            password=config["yarooms-password"],
            base_url=base_url,
            subdomain=config.get("yarooms-subdomain", ""),
        )

    # ── Daily quota tracker ───────────────────────────────────────────────
    quota = DailyQuotaTracker()

    # ── Redis (shared between spaces cache and quota tracker) ─────────────
    redis_client = await _build_redis_client(config.get("redis-url", ""))
    if redis_client:
        yarooms.set_redis_client(redis_client)
        quota.set_redis_client(redis_client)

    # Warm the cache at startup so the first user gets an instant room list.
    try:
        spaces = await yarooms.get_spaces_cached(force_refresh=True)
        logger.info(f"Spaces cache warmed at startup: {len(spaces)} rooms.")
    except Exception as exc:
        logger.warning(f"Startup cache warm-up failed (will retry on first request): {exc}")

    logger.info(f"Daily quota tracker ready: {quota.get_meta()}")

    register_home_tab_handlers(app)
    register_book_time_handlers(app, yarooms, quota)
    register_book_room_handlers(app, yarooms, quota)
    register_hot_booking_handlers(app, yarooms, quota)

    return yarooms

