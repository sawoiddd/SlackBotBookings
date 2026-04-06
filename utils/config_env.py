"""Environment loader and validator for required Slack / Yarooms settings.

Reads a ``.env`` file (simple KEY=VALUE format) and validates that at least one
Yarooms auth mode is configured (static API key **or** email + password).
"""

import os
from pathlib import Path


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


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
    """Load and validate required Slack/Yarooms settings from .env/environment.

    Yarooms auth accepts two mutually-exclusive modes:
      1. Static bearer token  → set YAROOMS_API_KEY
      2. Email / password     → set YAROOMS_EMAIL + YAROOMS_PASSWORD
         (optionally YAROOMS_SUBDOMAIN, defaults to empty string)

    If both are present, YAROOMS_API_KEY takes precedence.
    """
    _load_dotenv_file()

    api_key    = _optional_env("YAROOMS_API_KEY")
    email      = _optional_env("YAROOMS_EMAIL")
    password   = _optional_env("YAROOMS_PASSWORD")
    subdomain  = _optional_env("YAROOMS_SUBDOMAIN")
    base_url   = _optional_env("YAROOMS_BASE_URL", "https://api.yarooms.com")

    if not api_key and not (email and password):
        raise RuntimeError(
            "Yarooms auth not configured. "
            "Set YAROOMS_API_KEY or both YAROOMS_EMAIL and YAROOMS_PASSWORD in .env."
        )

    return {
        "app-token":          _require_env("SLACK_APP_TOKEN"),
        "bot-token":          _require_env("SLACK_BOT_TOKEN"),
        # Yarooms – one of the two auth modes will be populated
        "yarooms-api-key":    api_key,
        "yarooms-email":      email,
        "yarooms-password":   password,
        "yarooms-subdomain":  subdomain,
        "yarooms-base-url":   base_url,
        # Optional Redis cache URL; falls back to in-memory cache when absent
        "redis-url":          _optional_env("REDIS_URL", ""),
        # Optional log level (DEBUG, INFO, WARNING, ERROR)
        "log-level":          _optional_env("LOG_LEVEL", "INFO").upper(),
    }


