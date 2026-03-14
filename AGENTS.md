# AGENTS.md

## Project map (Slack Socket Mode bot)
- **`main.py`** — entrypoint: loads `.env` via `utils.config_env.load_tokens_from_env`, builds `AsyncApp`, calls `register_home_handlers(app, tokens)`, starts `AsyncSocketModeHandler`.
- **`home.py`** — thin orchestrator: builds `YaroomsClient`, wires feature-specific handler registrars.
- **`handlers/home_home_tab.py`** — Home tab event handler (`app_home_opened`) and dashboard view.
- **`handlers/home_book_time.py`** — Book by Time action/view handlers.
- **`handlers/home_book_room.py`** — Book by Room schedule + specific slot booking handlers.
- **`handlers/home_hot_booking.py`** — Hot Booking action handler.
- **`handlers/home_common.py`** — common module imported by feature handlers; re-exports shared booking/slack helpers and provides `get_user_email`, `safe_get_room_name`.
- **`utils/booking_utils.py`** — booking/time helpers and constants: `MAX_BOOKING_HOURS`, `MAX_BOOKING_MINUTES`, `_duration_minutes`, `_available_time_options`, `_normalized_available_slots`, `_covers_interval`.
- **`utils/slack_views.py`** — shared Slack view builders (currently `skeleton_view`).
- **`utils/slack_notifications.py`** — shared chat notification helper (`notify_booking_in_chat`).
- **`clients/yarooms_client.py`** — async Yarooms API client (`YaroomsClient`). Methods: `get_spaces`, `get_space_availability`, `find_available_space`, `create_booking`. Endpoint paths/response shapes are documented in the file and must be verified against https://api-docs.yarooms.com/#introduction.
- **`utils/config_env.py`** — environment loader/validator for required Slack/Yarooms keys.

## Required environment keys
Add these to `.env` (already gitignored):
```bash
SLACK_APP_TOKEN=xapp-...
SLACK_BOT_TOKEN=xoxb-...
YAROOMS_API_KEY=<your Yarooms bearer token>
YAROOMS_BASE_URL=https://api.yarooms.com
```

## Required Slack OAuth scopes
- `users:read.email` — needed in all booking handlers to resolve user email for Yarooms API calls via `client.users_info(user=user_id)`.

## Architecture and data flow
- Runtime flow: Slack event/action → Bolt decorator in feature module (`handlers/home_home_tab.py`, `handlers/home_book_time.py`, `handlers/home_book_room.py`, `handlers/home_hot_booking.py`) → immediate `ack()` → modal/home view update via `client.views_open`, `client.views_update`, or `client.views_publish`.
- Home tab (`app_home_opened`) publishes 3 booking entry points: `action_book_time`, `action_book_room`, `action_hot_booking`.
- All 4 booking handlers call real `YaroomsClient` methods; no stubs remain.
- Room list in `open_book_room_modal` is fetched live from Yarooms; falls back to static list on API error.
- `skeleton_view("Searching")` is used as loading state; type is `"modal"` (was incorrectly `"home"` before).

## Business rules
- **Max booking duration: 3 hours per booking** (`MAX_BOOKING_HOURS = 3`, `MAX_BOOKING_MINUTES = 180` in `utils/booking_utils.py`).
- Enforced in two places:
  - `handle_book_time_submission`: validated before `ack()` using `response_action="errors"` on `block_end_time` — inline modal error, no skeleton shown on failure.
  - `handle_book_specific_slot`: validated after unpacking the button value; on failure modal updates to a "Booking Rejected" error view.
  - `handle_book_room_submission`: slots exceeding the limit are filtered out before rendering the schedule view.
- Duration helper: `_duration_minutes(start, end)` — module-level in `utils/booking_utils.py`; returns negative if end ≤ start.

## Handler patterns to preserve
- Always call `await ack()` first for actions.
- For modal submissions: `await ack(response_action="update", view=skeleton_view(...))` then `client.views_update(...)`.
- Feature modules use `import handlers.home_common as common` (Common Module Pattern) to keep imports short and consistent.
- Data extraction uses stable Block Kit IDs: `state_values["block_date"]["action_date"]["selected_date"]`.
- `Book by Time` currently uses two `static_select` inputs (`block_start_time`, `block_end_time`) and both use `_available_time_options()`.
- `_available_time_options(start_hour=8, end_hour=22, minute_step=10)` supports configurable ranges; defaults provide **10-minute increments** from `08:00` through `21:50`, which keeps each Slack `static_select` under the 100-option limit.
- Keep `_available_time_options()` under Slack `static_select` limit (max 100 options per field).
- Slot button value format: `"{room_id}_{start}_{end}"` — parsed with **`rsplit("_", 2)`** (not `split`) so room IDs containing underscores are handled safely.
- Booking date is passed from `handle_book_room_submission` → `handle_book_specific_slot` via `private_metadata` on the schedule modal view.
- `handle_book_specific_slot` re-fetches room availability before `create_booking` and rejects stale slots with a "Slot Unavailable" modal.
- Successful bookings send a DM via `notify_booking_in_chat(...)` with room/date/time details.

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
