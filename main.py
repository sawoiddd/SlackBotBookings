import slack_bolt
from configJsonReader import ConfigJsonReader
from slack_bolt.adapter.socket_mode import SocketModeHandler


config_path = "config.json"

tokens = ConfigJsonReader.GetTokens(config_path)

#bot token
app = slack_bolt.App(token=tokens["bot-token"])

#app token
SocketModeHandler(app, tokens["app-token"]).start()