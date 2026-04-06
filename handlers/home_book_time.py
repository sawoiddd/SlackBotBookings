"""Book by Time — user picks date + time range, bot searches all cached rooms
in parallel and presents a room picker.  Final booking includes a live
availability re-check before calling create_booking.
"""

import asyncio
import handlers.home_common as common
import time

MAX_PARALLEL_AVAILABILITY_CHECKS = 8


async def _check_room_availability(
    *,
    space: dict,
    yarooms,
    selected_date: str,
    start_time: str,
    end_time: str,
    semaphore: asyncio.Semaphore,
    logger,
) -> tuple[str, str] | None:
    """Check a single room against requested interval using bookings data.

    Uses ``yarooms.is_interval_free`` which fetches **all** bookings for the
    day via ``/api/bookings`` and checks for real overlaps.  This replaces the
    old snapshot-based ``/api/spaces/availability`` check that could only see
    the *first* upcoming state change and missed subsequent bookings inside the
    requested window.

    Returns:
      - (room_id, room_name) if interval is fully free
      - None when unavailable or malformed
    """
    room_id = str(space.get("id") or space.get("spaceId") or "")
    room_name = space.get("name") or space.get("title") or room_id
    if not room_id:
        return None

    try:
        async with semaphore:
            is_free = await yarooms.is_interval_free(
                room_id,
                selected_date,
                start_time,
                end_time,
            )

        logger.debug(
            f"Book by Time availability: room={room_name} ({room_id}), "
            f"date={selected_date}, requested={start_time}-{end_time}, "
            f"free={is_free}"
        )
        return (room_id, room_name) if is_free else None
    except Exception as exc:
        logger.warning(
            f"Book by Time availability check failed: room={room_name} ({room_id}), "
            f"date={selected_date}, err={type(exc).__name__}: {exc}"
        )
        return None


async def _find_available_rooms(
    *,
    spaces: list[dict],
    yarooms,
    selected_date: str,
    start_time: str,
    end_time: str,
    logger,
) -> list[tuple[str, str]]:
    """Return available (room_id, room_name) pairs for the requested interval."""
    semaphore = asyncio.Semaphore(MAX_PARALLEL_AVAILABILITY_CHECKS)
    results = await asyncio.gather(
        *[
            _check_room_availability(
                space=space,
                yarooms=yarooms,
                selected_date=selected_date,
                start_time=start_time,
                end_time=end_time,
                semaphore=semaphore,
                logger=logger,
            )
            for space in spaces
        ],
        return_exceptions=False,
    )
    return [r for r in results if r is not None]


def _choose_room_view(
    *,
    selected_date: str,
    start_time: str,
    end_time: str,
    available_rooms: list[tuple[str, str]],
) -> dict:
    """Build room picker modal for Book by Time results."""
    room_blocks = []
    for room_id, room_name in available_rooms:
        room_blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{room_name}*"},
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Забронювати", "emoji": False},
                    "style": "primary",
                    "value": f"{room_id}|{selected_date}|{start_time}|{end_time}",
                    "action_id": "action_book_time_specific_room",
                },
            }
        )

    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": "Оберіть кімнату", "emoji": False},
        "close": {"type": "plain_text", "text": "Закрити", "emoji": False},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"Доступно на *{selected_date}* з *{start_time}* до *{end_time}*\n"
                        f"Знайдено кімнат: *{len(available_rooms)}*"
                    ),
                },
            },
            {"type": "divider"},
            *room_blocks,
        ],
    }


def register_book_time_handlers(app, yarooms, quota):
    """Register Book by Time action/view handlers."""

    @app.action("action_book_time")
    async def open_book_time_modal(ack, body, client, logger):
        """Open the Book by Time modal."""
        await ack()
        try:
            await client.views_open(
                trigger_id=body["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": "modal_book_time_submit",
                    "title": {"type": "plain_text", "text": "Бронювання за часом"},
                    "submit": {"type": "plain_text", "text": "Знайти кімнату"},
                    "close": {"type": "plain_text", "text": "Скасувати"},
                    "clear_on_close": True,
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Оберіть дату та інтервал часу. Система автоматично знайде вільну кімнату.",
                            },
                        },
                        {"type": "divider"},
                        {
                            "type": "input",
                            "block_id": "block_date",
                            "element": {
                                "type": "datepicker",
                                "placeholder": {"type": "plain_text", "text": "Оберіть дату"},
                                "action_id": "action_date",
                            },
                            "label": {"type": "plain_text", "text": "Дата"},
                        },
                        {
                            "type": "input",
                            "block_id": "block_start_time",
                            "element": {
                                "type": "static_select",
                                "placeholder": {"type": "plain_text", "text": "Оберіть час початку"},
                                "options": common._available_time_options(),
                                "action_id": "action_start_time",
                            },
                            "label": {"type": "plain_text", "text": "Час початку"},
                        },
                        {
                            "type": "input",
                            "block_id": "block_end_time",
                            "element": {
                                "type": "static_select",
                                "placeholder": {"type": "plain_text", "text": "Оберіть час завершення"},
                                "options": common._available_time_options(),
                                "action_id": "action_end_time",
                            },
                            "label": {"type": "plain_text", "text": "Час завершення"},
                        },
                    ],
                },
            )
        except Exception as e:
            logger.error(f"Error opening modal: {e}")

    @app.view("modal_book_time_submit")
    async def handle_book_time_submission(ack, body, client, view, logger):
        """Validate input, fetch API availability, and show room options."""
        state_values = view["state"]["values"]
        selected_date = state_values["block_date"]["action_date"]["selected_date"]
        start_time = state_values["block_start_time"]["action_start_time"]["selected_option"]["value"]
        end_time = state_values["block_end_time"]["action_end_time"]["selected_option"]["value"]
        user_id = body["user"]["id"]

        logger.info(
            f"Book by Time submit: user={user_id}, date={selected_date}, start={start_time}, end={end_time}"
        )

        duration = common._duration_minutes(start_time, end_time)
        if duration <= 0:
            await ack(
                response_action="errors",
                errors={"block_end_time": "Час завершення має бути пізніше за час початку."},
            )
            return
        if duration > common.MAX_BOOKING_MINUTES:
            await ack(
                response_action="errors",
                errors={"block_end_time": f"Тривалість бронювання не може перевищувати {common.MAX_BOOKING_HOURS} год."},
            )
            return
        if common._is_past_slot(selected_date, start_time):
            await ack(
                response_action="errors",
                errors={"block_start_time": "Цей час уже минув. Оберіть майбутній інтервал."},
            )
            return

        # ── Daily quota pre-check ────────────────────────────────────────
        user_email_for_quota = await common.get_user_email(client, user_id)
        if user_email_for_quota:
            allowed, used, remaining = await quota.check_quota(
                user_email_for_quota, selected_date, duration,
            )
            if not allowed:
                await ack(
                    response_action="errors",
                    errors={
                        "block_end_time": (
                            f"Денний ліміт: використано {used}/{common.MAX_DAILY_BOOKING_MINUTES} хв. "
                            f"На сьогодні залишилось лише {remaining} хв."
                        ),
                    },
                )
                return

        await ack(response_action="update", view=common.skeleton_view("Пошук"))

        try:
            spaces = await yarooms.get_spaces_cached(force_refresh=True)
            logger.info(f"Book by Time spaces loaded: count={len(spaces)}")

            if not spaces:
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=common.simple_modal(
                        "Кімнати не знайдено",
                        "⚠️ Не вдалося завантажити список кімнат. Спробуйте ще раз за мить.",
                    ),
                )
                return

            available_rooms = await _find_available_rooms(
                spaces=spaces,
                yarooms=yarooms,
                selected_date=selected_date,
                start_time=start_time,
                end_time=end_time,
                logger=logger,
            )
            logger.info(
                f"Book by Time search: user={user_id}, checked={len(spaces)}, found={len(available_rooms)}"
            )

            if not available_rooms:
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=common.simple_modal(
                        "Кімнати не знайдено",
                        (
                            f"😕 На *{selected_date}* з *{start_time}* до *{end_time}* "
                            f"немає вільних Skype-кімнат або Silent Box."
                        ),
                    ),
                )
                return

            await client.views_update(
                view_id=body["view"]["id"],
                view=_choose_room_view(
                    selected_date=selected_date,
                    start_time=start_time,
                    end_time=end_time,
                    available_rooms=available_rooms,
                ),
            )
        except Exception as exc:
            error_ref = f"BT-{int(time.time())}"
            logger.exception(
                f"Book by Time unhandled error [{error_ref}]: user={user_id}, "
                f"date={selected_date}, start={start_time}, end={end_time}"
            )
            error_detail = str(exc)[:140] if str(exc) else type(exc).__name__
            await client.views_update(
                view_id=body["view"]["id"],
                view=common.error_modal_with_context(
                    "Помилка бронювання",
                    "❌ Не вдалося виконати пошук кімнат. Спробуйте ще раз.",
                    [f"Код: `{error_ref}`", f"Деталі: `{error_detail}`"],
                ),
            )

    @app.action("action_book_time_specific_room")
    async def handle_book_time_specific_room(ack, body, client, logger):
        """Book the selected room option after re-checking live availability."""
        await ack()

        async def _safe_modal_update(view_payload: dict, *, stage: str) -> bool:
            """Best-effort modal update to avoid Slack action red-crosses on UI errors."""
            try:
                await client.views_update(view_id=body["view"]["id"], view=view_payload)
                return True
            except Exception as ui_err:
                logger.error(
                    "Book by Time modal update failed at %s: user=%s, err=%s: %s",
                    stage,
                    body.get("user", {}).get("id", "unknown"),
                    type(ui_err).__name__,
                    ui_err,
                )
                return False

        room_id = ""
        booking_date = ""
        start_time = ""
        end_time = ""
        try:
            await _safe_modal_update(common.skeleton_view("Бронювання"), stage="loading_skeleton")

            action = body["actions"][0]
            room_id, booking_date, start_time, end_time = action["value"].split("|", 3)
            user_id = body["user"]["id"]
            logger.info(
                f"Book by Time room selected: user={user_id}, room={room_id}, "
                f"date={booking_date}, start={start_time}, end={end_time}"
            )

            if common._is_past_slot(booking_date, start_time):
                await _safe_modal_update(
                    common.simple_modal(
                        "Час минув",
                        "❌ Цей часовий інтервал уже минув. Зробіть новий пошук для майбутнього часу.",
                    ),
                    stage="past_time",
                )
                return

            # Re-check live availability (bookings-based, not snapshot)
            try:
                still_available = await yarooms.is_interval_free(
                    room_id,
                    booking_date,
                    start_time,
                    end_time,
                )
            except Exception as avail_err:
                logger.warning(
                    f"Book by Time re-check failed: room={room_id}, date={booking_date}, "
                    f"err={type(avail_err).__name__}: {avail_err}"
                )
                still_available = False

            if not still_available:
                await _safe_modal_update(
                    common.simple_modal(
                        "Інтервал недоступний",
                        "❌ Цей інтервал уже недоступний. Спробуйте виконати пошук знову.",
                    ),
                    stage="slot_unavailable",
                )
                return

            user_email = await common.get_user_email(client, user_id)
            logger.debug(f"Book by Time resolved email for {user_id}: '{user_email}'")

            # ── Daily quota re-check (guards against concurrent bookings) ─
            booking_duration = common._duration_minutes(start_time, end_time)
            if user_email and booking_duration > 0:
                allowed, used, remaining = await quota.check_quota(
                    user_email, booking_date, booking_duration,
                )
                if not allowed:
                    await _safe_modal_update(
                        common.quota_exceeded_modal(
                            used, remaining, booking_duration,
                            common.MAX_DAILY_BOOKING_MINUTES,
                        ),
                        stage="quota_exceeded",
                    )
                    return

            try:
                booking_result = await yarooms.create_booking(
                    space_id=room_id,
                    date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    user_email=user_email,
                )
            except Exception as book_err:
                logger.error(
                    f"Book by Time create_booking failed: room={room_id}, date={booking_date}, "
                    f"start={start_time}, end={end_time}, err={type(book_err).__name__}: {book_err}"
                )
                error_detail = str(book_err)[:120]
                await _safe_modal_update(
                    common.error_modal_with_context(
                        "Помилка бронювання",
                        "❌ Не вдалося забронювати кімнату — можливо, її щойно зайняли. Спробуйте пошук ще раз.",
                        [f"Деталі: `{error_detail}`"],
                    ),
                    stage="booking_failed",
                )
                return

            # ── Record quota ONLY after successful booking ────────────────
            if user_email and booking_duration > 0:
                await quota.record_booking(user_email, booking_date, booking_duration)

            booking_id = yarooms.extract_booking_id(booking_result)

            room_name = await common.safe_get_room_name(yarooms, room_id)
            await _safe_modal_update(
                {
                    "type": "modal",
                    "title": {"type": "plain_text", "text": "Кімнату заброньовано", "emoji": False},
                    "close": {"type": "plain_text", "text": "Готово", "emoji": False},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"🎉 Успішно заброньовано *{room_name}*.",
                            },
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"📅 *Дата:* {booking_date} | ⏰ *Час:* {start_time} - {end_time}",
                                }
                            ],
                        },
                    ],
                },
                stage="booking_success",
            )

            await common.notify_booking_in_chat(
                client=client,
                logger=logger,
                user_id=user_id,
                room_name=room_name,
                booking_date=booking_date,
                start_time=start_time,
                end_time=end_time,
                booking_id=booking_id,
                user_email=user_email,
            )
        except Exception:
            logger.exception(
                f"Book by Time room booking error: user={body['user']['id']}, room={room_id}, "
                f"date={booking_date}, start={start_time}, end={end_time}"
            )
            updated = await _safe_modal_update(
                common.simple_modal(
                    "Помилка бронювання",
                    "❌ Не вдалося завершити бронювання цієї кімнати. Спробуйте ще раз.",
                ),
                stage="exception_fallback",
            )
            if not updated:
                await client.chat_postMessage(
                    channel=body["user"]["id"],
                    text="Не вдалося оновити вікно бронювання. Відкрийте Home повторно та спробуйте ще раз.",
                )
