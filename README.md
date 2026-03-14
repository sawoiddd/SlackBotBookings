# SlackBotBookingsKSE

Slack Socket Mode bot for booking meeting spaces through Yarooms.

## What this bot does
- Publishes a Home tab with 3 actions:
  - `Book time` - pick date/time, bot finds a free room.
  - `Book room` - pick a room/date, then choose an available slot.
  - `Hot Booking` - books a room for the next 30 minutes.
- Enforces booking duration rule: max **3 hours** per booking.

## Project structure
- `main.py` - app entrypoint, loads config from `.env`, starts Socket Mode handler.
- `home.py` - thin orchestrator that wires feature-specific handler registrars.
- `handlers/` - feature modules (`home_home_tab.py`, `home_book_time.py`, `home_book_room.py`, `home_hot_booking.py`) and `home_common.py`.
- `utils/` - shared helpers (`booking_utils.py`, `slack_views.py`, `slack_notifications.py`).
- `clients/yarooms_client.py` - async Yarooms API client (`aiohttp`).
- `config_env.py` - `.env` loader and required-variable validation.
- `AGENTS.md` - project-specific coding guidance.

## Requirements
- Python 3.10+
- Slack app with Socket Mode enabled
- Yarooms API token

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration (.env)
Create your local env file:

```bash
cp .env.example .env
```

Required variables:
- `SLACK_APP_TOKEN`
- `SLACK_BOT_TOKEN`
- `YAROOMS_API_KEY`

Optional:
- `YAROOMS_BASE_URL` (defaults to `https://api.yarooms.com`)

Do not commit `.env` or token values.

## Slack app setup
Required OAuth scope:
- `users:read.email`

This scope is required because booking handlers resolve user email via `client.users_info(user=user_id)` before creating Yarooms bookings.

## Run locally

```bash
python3 main.py
```

## Runtime flow (high level)
1. Slack event/action reaches a feature handler in `handlers/`.
2. Handler sends immediate `ack()`.
3. Bot opens/updates modal views (`views_open`, `views_update`) or publishes Home tab (`views_publish`).
4. Handler calls `YaroomsClient` methods to read availability and create bookings.

## Yarooms integration
Implemented in `clients/yarooms_client.py`:
- `get_spaces()`
- `get_space_availability(space_id, date)`
- `find_available_space(date, start_time, end_time)`
- `create_booking(space_id, date, start_time, end_time, user_email, title)`

Before production rollout, confirm endpoint paths and response envelopes against official docs:
- https://api-docs.yarooms.com/#introduction

## Troubleshooting
- Bot starts but no Home tab updates:
  - verify `SLACK_APP_TOKEN` / `SLACK_BOT_TOKEN` in `.env`
  - ensure Socket Mode is enabled in Slack app settings
- Booking actions fail with user info/email issues:
  - verify OAuth scope `users:read.email`
  - reinstall app to workspace after scope changes
- Room list/booking fails:
  - verify `YAROOMS_API_KEY` and `YAROOMS_BASE_URL`
  - check logs for HTTP errors from Yarooms API
