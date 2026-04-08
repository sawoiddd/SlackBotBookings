"""Heroku-ready environment loader using python-dotenv.

Hybrid loading strategy:
  1. Attempt to load variables from a local ``.env`` file (for local dev).
     ``override=False`` ensures that system environment variables (e.g. Heroku
     Config Vars already present in ``os.environ``) are never overwritten.
  2. If ``.env`` is absent the call is a silent no-op — all values are then
     read from the system environment, which is exactly how Heroku works.

To revert to the old hand-rolled parser, comment out the import in main.py
and uncomment the original ``from utils.config_env import load_tokens_from_env``.
"""

import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────


def _require_env(name: str) -> str:
    """Return a required env var or raise with a Heroku-friendly message."""
    value = os.getenv(name, "").strip()
    if not value:
        raise KeyError(
            f"Missing required variable: {name}. "
            f"Set it in a .env file (local dev) or as a system environment "
            f"variable / Heroku Config Var (production)."
        )
    return value


def _optional_env(name: str, default: str = "") -> str:
    """Return an optional env var, falling back to *default*."""
    return os.getenv(name, default).strip()


# ── Public entry point ─────────────────────────────────────────────────────


def load_tokens_from_env() -> dict:
    """Load and validate required Slack/Yarooms settings.

    Yarooms auth accepts two mutually-exclusive modes:
      1. Static bearer token  → set ``YAROOMS_API_KEY``
      2. Email / password     → set ``YAROOMS_EMAIL`` + ``YAROOMS_PASSWORD``
         (optionally ``YAROOMS_SUBDOMAIN``, defaults to empty string)

    If both are present, ``YAROOMS_API_KEY`` takes precedence.

    Loading order:
      • ``.env`` file (if present) → populates ``os.environ`` **without**
        overriding existing values.
      • System environment (Heroku Config Vars, Docker env, shell exports)
        always wins.
    """
    # -- Hybrid load: .env file first, system env as fallback ---------------
    dotenv_loaded = load_dotenv(override=False)  # True when .env was found
    if dotenv_loaded:
        logger.info("Loaded variables from .env file (local dev mode).")
    else:
        logger.info(
            "No .env file found — reading from system environment "
            "(Heroku / Docker / CI)."
        )

    # -- Yarooms auth -------------------------------------------------------
    api_key   = _optional_env("YAROOMS_API_KEY")
    email     = _optional_env("YAROOMS_EMAIL")
    password  = _optional_env("YAROOMS_PASSWORD")
    subdomain = _optional_env("YAROOMS_SUBDOMAIN")
    base_url  = _optional_env("YAROOMS_BASE_URL", "https://api.yarooms.com")

    if not api_key and not (email and password):
        raise KeyError(
            "Yarooms auth not configured. "
            "Set YAROOMS_API_KEY — or both YAROOMS_EMAIL and YAROOMS_PASSWORD — "
            "in your .env file (local) or as system environment variables / "
            "Heroku Config Vars (production)."
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

