from slack_bolt.async_app import AsyncApp

from configJsonReader import ConfigJsonReader
import asyncio
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler

from home import register_home_handlers

config_path = "config.json"

tokens = ConfigJsonReader.GetTokens(config_path)

#bot token
app = AsyncApp(token=tokens["bot-token"])

register_home_handlers(app)

async def main():
    handler = AsyncSocketModeHandler(app, tokens["app-token"])
    await handler.start_async()


if __name__ == "__main__":
    # Start the async event loop
    asyncio.run(main())