# AGENTS.md

## Project map (Slack Socket Mode bot)
- **`main.py`** — entrypoint: loads `.env` via `utils.config_env.load_tokens_from_env`, builds `AsyncApp`, awaits `register_home_handlers(app, tokens)` inside `async main()`, starts `AsyncSocketModeHandler`.
- **`home.py`** — thin orchestrator: builds `YaroomsClient`, wires feature-specific handler registrars.
- **`handlers/home_home_tab.py`** — Home tab event handler (`app_home_opened`) and dashboard view.
- **`handlers/home_book_time.py`** — Book by Time action/view handlers.
- **`handlers/home_book_room.py`** — Book by Room schedule + specific slot booking handlers.
- **`handlers/home_hot_booking.py`** — Hot Booking action handler.
- **`handlers/home_cancel_booking.py`** — DM cancellation button action handler (`action_cancel_booking`).
- **`handlers/home_common.py`** — common module imported by feature handlers; re-exports shared booking/slack helpers and provides `get_user_email`, `safe_get_room_name`.
- **`utils/booking_utils.py`** — booking/time helpers and constants: `MAX_BOOKING_HOURS`, `MAX_BOOKING_MINUTES`, `_duration_minutes`, `_available_time_options`, `_normalized_available_slots`, `_covers_interval`.
- **`utils/slack_views.py`** — shared Slack view builders (`skeleton_view`, `simple_modal`, `error_modal_with_context`, `quota_exceeded_modal`).
- **`utils/slack_notifications.py`** — shared chat notification helper (`notify_booking_in_chat`), now includes DM cancellation button when `booking_id` is known.
- **`utils/daily_quota.py`** — per-user daily booking quota tracker (`DailyQuotaTracker`). Uses Redis (primary) with in-memory fallback. Counter is incremented **only after** `create_booking` succeeds and decremented after successful cancellation (`record_cancellation`).
- **`clients/yarooms_client.py`** — async Yarooms API client (`YaroomsClient`). Methods include `get_spaces`, `get_space_availability`, `find_available_space`, `create_booking`, `delete_booking`, `extract_booking_id`. Endpoint paths/response shapes are documented in the file and must be verified against https://api-docs.yarooms.com/#introduction.
- **`utils/config_env.py`** — environment loader/validator for required Slack/Yarooms keys.

## Required environment keys
Add these to `.env` (already gitignored).

**Option A — static API token (original):**
```bash
SLACK_APP_TOKEN=xapp-...
SLACK_BOT_TOKEN=xoxb-...
YAROOMS_API_KEY=<your Yarooms API token>
YAROOMS_BASE_URL=https://api.yarooms.com
LOG_LEVEL=DEBUG
```

**Option B — email / password login (e.g. KSE instance):**
```bash
SLACK_APP_TOKEN=xapp-...
SLACK_BOT_TOKEN=xoxb-...
YAROOMS_EMAIL=you@example.com
YAROOMS_PASSWORD=secret
YAROOMS_SUBDOMAIN=KSE          # optional; sent as query param to /api/auth
YAROOMS_BASE_URL=https://kse.eu.yarooms.com
REDIS_URL=redis://localhost:6379/0  # optional; falls back to in-memory cache
LOG_LEVEL=DEBUG
```

If `YAROOMS_API_KEY` is set it always takes precedence over email/password.
Both `YAROOMS_EMAIL` **and** `YAROOMS_PASSWORD` must be present when no API key is configured.

## Required Slack OAuth scopes
- `users:read` — needed for `client.users_info(user=user_id)` calls in booking handlers.
- `users:read.email` — needed to access `profile.email` from user info responses.

## Architecture and data flow
- Runtime flow: Slack event/action → Bolt decorator in feature module (`handlers/home_home_tab.py`, `handlers/home_book_time.py`, `handlers/home_book_room.py`, `handlers/home_hot_booking.py`) → immediate `ack()` → modal/home view update via `client.views_open`, `client.views_update`, or `client.views_publish`.
- Home tab (`app_home_opened`) publishes 3 booking entry points: `action_book_time`, `action_book_room`, `action_hot_booking`.
- All 4 booking handlers call real `YaroomsClient` methods; no stubs remain.
- Room list in `open_book_room_modal` uses cached Yarooms spaces (`get_spaces_cached` with TTL/stale fallback); on API/cache miss it shows an explicit error modal (no static template rooms).
- `YaroomsClient.get_spaces` filters rooms to **Skype rooms** and **Silent Boxes** only; other room types are ignored and never cached.
- Cache backend: **Redis** (primary, `yarooms:spaces` / `yarooms:spaces:stale` keys) with automatic **in-memory fallback** when Redis is unavailable. Injected via `yarooms.set_redis_client(redis)` in `home.py`.
- Spaces cache is **warmed at bot startup** via `get_spaces_cached(force_refresh=True)` so the first user gets an instant room list.
- `skeleton_view("Searching")` is used as loading state; type is `"modal"` (was incorrectly `"home"` before).

## Business rules
- **Max booking duration: 3 hours per booking** (`MAX_BOOKING_HOURS = 3`, `MAX_BOOKING_MINUTES = 180` in `utils/booking_utils.py`).
- **Max 3 hours per user per day** (`MAX_DAILY_BOOKING_MINUTES = 180` in `utils/booking_utils.py`). Tracked by `DailyQuotaTracker` (`utils/daily_quota.py`); Redis key `yarooms:daily_quota:<email>:<date>` with 48 h TTL, in-memory fallback. Counter incremented **only after** `create_booking` API succeeds.
  - `handle_book_time_submission`: inline error on `block_end_time` before skeleton.
  - `handle_book_time_specific_room`: re-check before `create_booking`; shows `quota_exceeded_modal`.
  - `handle_book_specific_slot`: check before `create_booking`; shows `quota_exceeded_modal`.
  - `handle_hot_booking`: check before `create_booking`; shows `quota_exceeded_modal`.
- Enforced in two places:
  - `handle_book_time_submission`: validated before `ack()` using `response_action="errors"` on `block_end_time` — inline modal error, no skeleton shown on failure.
  - `handle_book_specific_slot`: validated after unpacking the button value; on failure modal updates to a "Booking Rejected" error view.
  - `handle_book_room_submission`: slots exceeding the limit are filtered out before rendering the schedule view.
- Duration helper: `_duration_minutes(start, end)` — module-level in `utils/booking_utils.py`; returns negative if end ≤ start.
- **No past bookings:** `_is_past_slot(date_str, start_time)` rejects slots whose start has already passed (`datetime.now()`).
  - `handle_book_time_submission`: inline modal error on `block_start_time` before `ack()` skeleton.
  - `handle_book_time_specific_room`: modal "Time Passed" before re-checking availability.
  - `handle_book_room_submission`: past slots are filtered out of the schedule view before rendering.
  - `handle_book_specific_slot`: modal "Time Passed" before re-checking availability.

## Handler patterns to preserve
- Always call `await ack()` first for actions.
- For modal submissions: `await ack(response_action="update", view=skeleton_view(...))` then `client.views_update(...)`.
- Feature modules use `import handlers.home_common as common` (Common Module Pattern) to keep imports short and consistent.
- Data extraction uses stable Block Kit IDs: `state_values["block_date"]["action_date"]["selected_date"]`.
- `Book by Time` currently uses two `static_select` inputs (`block_start_time`, `block_end_time`) and both use `_available_time_options()`.
- `Book by Time` submission now fetches API availability and shows a "Choose a Room" list; booking is finalized only after user clicks `action_book_time_specific_room` (with a live re-check before create).
- `_available_time_options(start_hour=8, end_hour=22, minute_step=10)` supports configurable ranges; defaults provide **10-minute increments** from `08:00` through `21:50`, which keeps each Slack `static_select` under the 100-option limit.
- Keep `_available_time_options()` under Slack `static_select` limit (max 100 options per field).
- Slot button value format: `"{room_id}_{start}_{end}"` — parsed with **`rsplit("_", 2)`** (not `split`) so room IDs containing underscores are handled safely.
- Booking date is passed from `handle_book_room_submission` → `handle_book_room_time_submission` via `private_metadata` (format: `room_id|date`).
- `Book by Room` schedule view shows free intervals as text and provides two `static_select` time pickers whose options are restricted to times **inside** free windows only (`_schedule_time_options`). Booked periods are physically absent from the pickers.
- `handle_book_room_time_submission` (callback `modal_book_room_time_submit`) validates start < end, duration ≤ max, not past, quota — all as inline errors before `ack()` skeleton. Then re-checks live availability and creates the booking.
- `handle_book_specific_slot` is kept registered as a legacy fallback for any stale slot-button modals.
- Successful bookings send a DM via `notify_booking_in_chat(...)` with room/date/time details.
- Successful booking DMs include a **Cancel booking** button when `create_booking` returns a booking id.
- `action_cancel_booking` cancels via `DELETE /api/bookings/:ID`, sends a DM result, and rolls back daily quota minutes.
- All booking handlers resolve the Slack user's email via `get_user_email(client, user_id)` before calling `create_booking`. This requires `users:read` + `users:read.email` Slack OAuth scopes.
- `create_booking` dual strategy: (1) resolve email → Yarooms `account_id` via `/api/accounts` and try on-behalf-of booking; (2) on failure, fall back to bot-account booking. Both strategies include `description="Booked via Slack by <email>"` so the booker is visible in Yarooms web UI.
- **Note:** Yarooms sanitises `@` → `[at]` in description fields.
- `/api/accounts` results are cached in-memory for 10 min (`_ACCOUNTS_CACHE_TTL`).
- The on-behalf-of `account_id` booking requires the bot's Yarooms account to have "book for others" permission in the Yarooms group settings. If the permission is missing, Strategy 2 (bot-account + description) is used silently.
- Yarooms API requests use `X-Token: <token>` and `/api/*` endpoints; Book by Room day schedule uses `/api/bookings` (`space_id` + `date`) as primary source and falls back to `/api/spaces/availability` probing on failure.
- In email/password mode, `YaroomsClient` automatically re-authenticates on HTTP 401 and retries once, so long-running bot sessions can recover expired tokens.

## Important codebase quirks
- `@app.view("modal_book_room_submit")` is registered at module registrar level in `handlers/home_book_room.py` (NOT nested inside `open_book_room_modal`) — nesting causes re-registration on every button click.
- `skeleton_view()` is a module-level function (not nested) returning `"type": "modal"`.
- UI text is mixed English/Ukrainian; preserve existing tone unless a task explicitly asks to standardize copy.

## Local workflows
```bash
pip install -r requirements.txt   # install dependencies
cp .env.example .env              # bootstrap local env file
python3 main.py                   # run bot
```

## Integrations and secrets
- Slack Bolt async stack: `slack_bolt.async_app.AsyncApp` + `slack_bolt.adapter.socket_mode.aiohttp.AsyncSocketModeHandler`.
- Yarooms API client: `clients/yarooms_client.py` (`YaroomsClient`, aiohttp-based). Verify endpoint paths and response envelope shapes from https://api-docs.yarooms.com/#introduction before going live.
- `.env` contains live tokens — already in `.gitignore`; never log or copy values.
