from slack_bolt.async_app import AsyncApp

import asyncio
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler

from home import register_home_handlers
from utils.config_env import load_tokens_from_env

tokens = load_tokens_from_env()

app = AsyncApp(token=tokens["bot-token"])

register_home_handlers(app, tokens)

async def main():
    handler = AsyncSocketModeHandler(app, tokens["app-token"])
    await handler.start_async()


if __name__ == "__main__":
    # Start the async event loop
    asyncio.run(main())