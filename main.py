"""Bot entrypoint — configures logging, prints a startup fingerprint, starts
the Slack Socket Mode handler, and ensures graceful shutdown of the Yarooms
HTTP session.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

# ── Logging must be configured BEFORE any Slack Bolt imports. ──────────────
# Bolt adds its own handler to the root logger during import; if we call
# basicConfig() afterwards it becomes a no-op (Python only adds a handler when
# none exist). We force our own StreamHandler unconditionally instead.
from utils.config_env import load_tokens_from_env

tokens = load_tokens_from_env()

_log_level = getattr(logging, tokens.get("log-level", "INFO").upper(), logging.INFO)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
logging.root.handlers.clear()          # remove anything Bolt may have added
logging.root.addHandler(_handler)
logging.root.setLevel(_log_level)
# Also quiet noisy Slack SDK transport noise unless DEBUG was requested
if _log_level > logging.DEBUG:
    logging.getLogger("slack_bolt").setLevel(logging.WARNING)
    logging.getLogger("slack_sdk").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ── Startup fingerprint ───────────────────────────────────────────────────
_startup_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
logger.info(f"Bot starting  pid={os.getpid()}  ts={_startup_ts}")

print(f"[startup] logging level={logging.getLevelName(_log_level)}", flush=True)

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from home import register_home_handlers

app = AsyncApp(token=tokens["bot-token"])



async def main():
    yarooms = await register_home_handlers(app, tokens)
    handler = AsyncSocketModeHandler(app, tokens["app-token"])
    try:
        await handler.start_async()
    finally:
        logger.info("Shutting down — closing YaroomsClient session…")
        await yarooms.close()


if __name__ == "__main__":
    # Start the async event loop
    asyncio.run(main())

