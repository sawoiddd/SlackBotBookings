# SlackBotBookingsKSE

Slack Socket Mode bot for booking Skype rooms and Silent Boxes through Yarooms.

## Features

| Action | What it does |
|--------|-------------|
| **Book time** | Pick a date and time range → bot finds all available rooms → you choose one. |
| **Book room** | Pick a specific room and date → see its schedule → tap a slot to book. |
| **Hot Booking** | One-tap booking of the nearest available room for the next 30 minutes. |

### Business rules

- **Max 3 hours per booking.** Enforced with inline modal errors and slot filtering.
- **Max 3 hours per user per day.** Tracked locally via Redis (primary) with in-memory fallback. Counter is incremented only after a successful Yarooms API booking. When the limit is reached, a "Daily Limit Reached" modal shows used/remaining minutes.
- **No past bookings.** Slots whose start time has already passed are rejected or filtered out automatically.
- Only **Skype rooms** and **Silent Boxes** are shown (other Yarooms space types are ignored).

---

## Project structure

```
main.py                          Entrypoint — logging, startup fingerprint, graceful shutdown
home.py                          Orchestrator — builds YaroomsClient, registers handler modules
handlers/
  home_home_tab.py               Home tab (app_home_opened) and dashboard view
  home_book_time.py              Book by Time action/view handlers
  home_book_room.py              Book by Room schedule + slot booking handlers
  home_hot_booking.py            Hot Booking action handler
  home_common.py                 Common module — re-exports shared helpers
clients/
  yarooms_client.py              Async Yarooms API client (aiohttp)
utils/
  booking_utils.py               Time/duration helpers, slot normalisation, constants
  daily_quota.py                 Per-user daily booking quota tracker (Redis + memory)
  slack_views.py                 Shared Slack view builders (skeleton, modal, quota)
  slack_notifications.py         Booking-confirmation DM helper
  config_env.py                  .env loader and required-variable validator
AGENTS.md                        Coding guidelines for AI-assisted development
```

---

## Requirements

- Python 3.10+
- Slack app with **Socket Mode** enabled
- Yarooms account (static API key **or** email/password)

```bash
pip install -r requirements.txt
```

---

## Configuration

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

### Option A — Static API token

```env
SLACK_APP_TOKEN=xapp-...
SLACK_BOT_TOKEN=xoxb-...
YAROOMS_API_KEY=<your Yarooms API token>
YAROOMS_BASE_URL=https://api.yarooms.com
LOG_LEVEL=DEBUG
```

### Option B — Email / password login

```env
SLACK_APP_TOKEN=xapp-...
SLACK_BOT_TOKEN=xoxb-...
YAROOMS_EMAIL=you@example.com
YAROOMS_PASSWORD=secret
YAROOMS_SUBDOMAIN=KSE
YAROOMS_BASE_URL=https://kse.eu.yarooms.com
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=DEBUG
```

| Variable | Required | Notes |
|----------|----------|-------|
| `SLACK_APP_TOKEN` | ✅ | Socket Mode app-level token (`xapp-…`) |
| `SLACK_BOT_TOKEN` | ✅ | Bot user token (`xoxb-…`) |
| `YAROOMS_API_KEY` | ✅ (option A) | Takes precedence over email/password |
| `YAROOMS_EMAIL` | ✅ (option B) | Must pair with `YAROOMS_PASSWORD` |
| `YAROOMS_PASSWORD` | ✅ (option B) | Must pair with `YAROOMS_EMAIL` |
| `YAROOMS_SUBDOMAIN` | ❌ | Sent as query param to `/api/auth` |
| `YAROOMS_BASE_URL` | ❌ | Defaults to `https://api.yarooms.com` |
| `REDIS_URL` | ❌ | Falls back to in-memory cache |
| `LOG_LEVEL` | ❌ | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |

> **Never commit `.env` or token values.** The file is already in `.gitignore`.

---

## Slack app setup

### Required OAuth scopes

| Scope | Why |
|-------|-----|
| `users:read` | Resolve Slack user profiles in booking handlers |
| `users:read.email` | Access `profile.email` for Yarooms on-behalf-of bookings |

After adding scopes, **reinstall the app to your workspace** for them to take effect.

---

## Run locally

```bash
python3 main.py
```

On startup the bot logs a fingerprint line with `pid` and UTC timestamp — useful for detecting stale duplicate instances:

```
Bot starting  pid=12345  ts=2026-03-20T10:00:00Z
```

On shutdown (Ctrl-C / SIGINT), the Yarooms HTTP session is closed cleanly via `YaroomsClient.close()`.

---

## Runtime flow

```
Slack event/action
  │
  ▼
Feature handler (handlers/)
  │  await ack()
  ▼
Modal / Home tab update
  │  views_open / views_update / views_publish
  ▼
YaroomsClient
  │  get_spaces_cached → get_space_availability → create_booking
  ▼
Booking confirmation DM (notify_booking_in_chat)
```

### Key implementation details

- **Spaces cache** is warmed at startup via `get_spaces_cached(force_refresh=True)`. Backend: Redis (primary) with automatic in-memory fallback.
- **Book by Time** checks all cached rooms in parallel (bounded by `MAX_PARALLEL_AVAILABILITY_CHECKS = 8`) and presents a "Choose a Room" picker. A live re-check runs before the final `create_booking`.
- **Book by Room** builds day schedule from `/api/bookings` (`space_id` + `date`) and falls back to `/api/spaces/availability` probing on failure. Selected date is passed to booking step via `private_metadata`.
- **create_booking** dual strategy: (1) resolve email → Yarooms `account_id` via `/api/accounts` → on-behalf-of booking; (2) on failure, fall back to bot-account booking with `description="Booked via Slack by <email>"`.
- In email/password mode, `YaroomsClient` auto-refreshes expired tokens on HTTP 401 and retries once.

---

## Yarooms API client

Implemented in `clients/yarooms_client.py`. Key methods:

| Method | Description |
|--------|-------------|
| `get_spaces()` | Fetch and filter spaces (Skype rooms + Silent Boxes only) |
| `get_spaces_cached()` | Cached version with TTL, stale fallback, single-flight lock |
| `get_space_availability(space_id, date, start_time?, end_time?)` | Available slots for one room on a date |
| `get_space_day_schedule(space_id, date)` | Free windows for one room/day (bookings primary, availability fallback) |
| `find_available_space(date, start_time, end_time)` | First room covering the requested interval |
| `create_booking(space_id, date, start_time, end_time, user_email?, title?)` | Create booking (dual on-behalf-of / bot-account strategy) |
| `resolve_account_id(email)` | Map email → Yarooms account ID (cached 10 min) |
| `close()` | Close the underlying aiohttp session |

Verify endpoint paths and response shapes against the official docs before any API changes: https://api-docs.yarooms.com/#introduction

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Bot starts but no Home tab updates | `SLACK_APP_TOKEN` / `SLACK_BOT_TOKEN` in `.env`; Socket Mode enabled in Slack app settings |
| Booking actions fail with email errors | `users:read` + `users:read.email` scopes granted; app reinstalled after scope changes |
| Room list empty or booking fails | `YAROOMS_API_KEY` (or email/password) and `YAROOMS_BASE_URL` are correct; check logs for HTTP errors |
| "Unclosed client session" warnings | Ensure the bot is stopped gracefully (Ctrl-C) so `YaroomsClient.close()` runs |
| Duplicate bot responses | Check startup fingerprint (`pid` / `ts`) in logs — kill stale instances |
| Redis cache not used | Verify `REDIS_URL` in `.env`; logs will show "Redis unavailable … falling back to in-memory cache" on connection failure |
