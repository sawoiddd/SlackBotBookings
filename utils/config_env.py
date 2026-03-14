import os
from pathlib import Path


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _load_dotenv_file(env_path: str = ".env") -> None:
    """Load simple KEY=VALUE pairs from a .env file into os.environ."""
    path = Path(env_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_tokens_from_env() -> dict:
    """Load and validate required Slack/Yarooms settings from .env/environment."""
    _load_dotenv_file()
    return {
        # Keep existing key names so the rest of the codebase stays unchanged.
        "app-token": _require_env("SLACK_APP_TOKEN"),
        "bot-token": _require_env("SLACK_BOT_TOKEN"),
        "yarooms-api-key": _require_env("YAROOMS_API_KEY"),
        "yarooms-base-url": os.getenv("YAROOMS_BASE_URL", "https://api.yarooms.com").strip(),
    }


