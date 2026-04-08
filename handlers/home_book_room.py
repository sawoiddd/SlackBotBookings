"""Book by Room — user picks a specific room and date, sees its available
slots schedule, and taps a slot to book.  Past slots are filtered out and a
live re-check is performed before create_booking.
"""

import handlers.home_common as common


def register_book_room_handlers(app, yarooms, quota):
    """Register Book by Room and slot-booking handlers."""

    def _get_cache_meta() -> dict:
        """Fetch Yarooms cache metadata (safe for logging)."""
        fn = getattr(yarooms, "get_spaces_cache_meta", None)
        return fn() if callable(fn) else {}

    @app.action("action_book_room")
    async def open_book_room_modal(ack, body, client, logger):
        """Open Book by Room modal with cached Yarooms list and explicit error state."""
        await ack()
        try:
            options = []
            load_error_text = ""
            try:
                logger.debug(f"Yarooms spaces cache meta(before): {_get_cache_meta()}")

                spaces = await yarooms.get_spaces_cached()
                if not spaces:
                    spaces = await yarooms.get_spaces_cached(
                        force_refresh=True,
                        allow_stale_on_error=False,
                    )

                for space in spaces:
                    room_id = space.get("id") or space.get("spaceId")
                    room_name = space.get("name") or space.get("title")
                    if room_id and room_name:
                        options.append(
                            {
                                "text": {"type": "plain_text", "text": room_name, "emoji": False},
                                "value": str(room_id),
                            }
                        )
                if not options:
                    raise RuntimeError("Yarooms returned no selectable spaces.")
            except Exception as api_err:
                logger.error(
                    f"Could not fetch Yarooms spaces: error={api_err}; cache_meta={_get_cache_meta()}"
                )
                load_error_text = str(api_err)

            logger.info(f"Book by Room options: count={len(options)}")
            if options:
                logger.debug(f"Yarooms spaces cache meta(after): {_get_cache_meta()}")

            if not options:
                await client.views_open(
                    trigger_id=body["trigger_id"],
                    view=common.error_modal_with_context(
                        "Бронювання кімнати",
                        "❌ Не вдалося завантажити кімнати з Yarooms. Спробуйте ще раз за кілька секунд.",
                        [f"Деталі: `{load_error_text[:120]}`" if load_error_text else "Деталі: недоступні"],
                    ),
                )
                return

            await client.views_open(
                trigger_id=body["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": "modal_book_room_submit",
                    "title": {"type": "plain_text", "text": "Бронювання кімнати", "emoji": False},
                    "submit": {"type": "plain_text", "text": "Показати розклад", "emoji": False},
                    "close": {"type": "plain_text", "text": "Скасувати", "emoji": False},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Оберіть кімнату та дату, щоб побачити доступні часові інтервали.",
                            },
                        },
                        {"type": "divider"},
                        {
                            "type": "input",
                            "block_id": "block_room",
                            "element": {
                                "type": "static_select",
                                "placeholder": {"type": "plain_text", "text": "Оберіть кімнату", "emoji": False},
                                "options": options,
                                "action_id": "action_room",
                            },
                            "label": {"type": "plain_text", "text": "Яка кімната?", "emoji": False},
                        },
                        {
                            "type": "input",
                            "block_id": "block_room_date",
                            "element": {
                                "type": "datepicker",
                                "placeholder": {"type": "plain_text", "text": "Оберіть дату", "emoji": False},
                                "action_id": "action_room_date",
                            },
                            "label": {"type": "plain_text", "text": "На яку дату?", "emoji": False},
                        },
                    ],
                },
            )
        except Exception as e:
            logger.error(f"Error opening book room modal: {e}")

    @app.view("modal_book_room_submit")
    async def handle_book_room_submission(ack, body, client, view, logger):
        """Show the room's free intervals and start/end time pickers.

        Uses ``get_space_day_schedule`` to walk the full working day
        (08:00-22:00), displays free windows as informational text, and
        presents two ``static_select`` pickers whose options are restricted
        to times inside those free windows only.
        """
        await ack(response_action="update", view=common.skeleton_view("Завантаження розкладу"))
        state_values = view["state"]["values"]
        try:
            selected_option = state_values["block_room"]["action_room"]["selected_option"]
            room_id = selected_option["value"]
            room_name = selected_option["text"]["text"]
            selected_date = state_values["block_room_date"]["action_room_date"]["selected_date"]

            # Walk the full working day to discover every free window
            free_windows = await yarooms.get_space_day_schedule(
                room_id, selected_date,
            )
            logger.info(
                f"Book by Room schedule: room={room_name} ({room_id}), "
                f"date={selected_date}, free_windows={len(free_windows)}"
            )

            # Build time-picker options (only times inside free windows)
            start_options = common._schedule_time_options(free_windows)
            end_options = common._schedule_time_options(free_windows, is_end=True)

            # Filter out past times (relevant when date is today)
            start_options = [
                o for o in start_options
                if not common._is_past_slot(selected_date, o["value"])
            ]
            end_options = [
                o for o in end_options
                if not common._is_past_slot(selected_date, o["value"])
            ]

            # ── No available time → show info-only modal ─────────────────
            if not start_options or not end_options:
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=common.simple_modal(
                        "Немає доступного часу",
                        f"😕 Для *{room_name}* на *{selected_date}* не знайдено вільного часу.",
                    ),
                )
                return

            # ── Build readable schedule text ─────────────────────────────
            schedule_lines: list[str] = []
            for w in free_windows:
                dur = common._duration_minutes(w["start"], w["end"])
                if dur <= 0:
                    continue
                h, m = divmod(dur, 60)
                dur_str = f"{h}h {m}min" if m else f"{h}h"
                schedule_lines.append(f"✅  *{w['start']} – {w['end']}*  ({dur_str})")
            schedule_text = "\n".join(schedule_lines) or "_Немає вільних інтервалів_"

            await client.views_update(
                view_id=body["view"]["id"],
                view={
                    "type": "modal",
                    "callback_id": "modal_book_room_time_submit",
                    "title": {"type": "plain_text", "text": "Бронювання кімнати", "emoji": False},
                    "submit": {"type": "plain_text", "text": "Забронювати", "emoji": False},
                    "close": {"type": "plain_text", "text": "Скасувати", "emoji": False},
                    "private_metadata": f"{room_id}|{selected_date}",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*{room_name}*  ·  {selected_date}\n\n{schedule_text}",
                            },
                        },
                        {"type": "divider"},
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "_Оберіть час початку та завершення в межах вільних інтервалів вище:_",
                            },
                        },
                        {
                            "type": "input",
                            "block_id": "block_book_start",
                            "element": {
                                "type": "static_select",
                                "placeholder": {"type": "plain_text", "text": "Час початку", "emoji": False},
                                "options": start_options,
                                "action_id": "action_book_start",
                            },
                            "label": {"type": "plain_text", "text": "Час початку", "emoji": False},
                        },
                        {
                            "type": "input",
                            "block_id": "block_book_end",
                            "element": {
                                "type": "static_select",
                                "placeholder": {"type": "plain_text", "text": "Час завершення", "emoji": False},
                                "options": end_options,
                                "action_id": "action_book_end",
                            },
                            "label": {"type": "plain_text", "text": "Час завершення", "emoji": False},
                        },
                    ],
                },
            )
        except Exception as e:
            logger.error(f"Error handling room schedule submission: {e}", exc_info=True)
            await client.views_update(
                view_id=body["view"]["id"],
                view=common.simple_modal(
                    "Помилка",
                    "❌ Не вдалося завантажити розклад кімнати. Спробуйте ще раз.",
                ),
            )

    # ── NEW: time-picker submission → validate + book ────────────────────

    @app.view("modal_book_room_time_submit")
    async def handle_book_room_time_submission(ack, body, client, view, logger):
        """Validate the chosen start/end, re-check live availability, and book."""
        state_values = view["state"]["values"]
        metadata = view.get("private_metadata", "")
        parts = metadata.split("|", 1)
        room_id = parts[0] if len(parts) > 0 else ""
        booking_date = parts[1] if len(parts) > 1 else ""

        start_time = state_values["block_book_start"]["action_book_start"]["selected_option"]["value"]
        end_time = state_values["block_book_end"]["action_book_end"]["selected_option"]["value"]
        user_id = body["user"]["id"]

        logger.info(
            f"Book by Room time submit: user={user_id}, room={room_id}, "
            f"date={booking_date}, start={start_time}, end={end_time}"
        )

        # ── Pre-ack inline validations ───────────────────────────────────
        duration = common._duration_minutes(start_time, end_time)
        if duration <= 0:
            await ack(
                response_action="errors",
                errors={"block_book_end": "Час завершення має бути пізніше за час початку."},
            )
            return
        if duration > common.MAX_BOOKING_MINUTES:
            await ack(
                response_action="errors",
                errors={
                    "block_book_end": (
                        f"Тривалість бронювання не може перевищувати {common.MAX_BOOKING_HOURS} год."
                    ),
                },
            )
            return
        if common._is_past_slot(booking_date, start_time):
            await ack(
                response_action="errors",
                errors={"block_book_start": "Цей час уже минув."},
            )
            return

        # Quota pre-check (fast: Redis/memory read)
        user_email = await common.get_user_email(client, user_id)
        if user_email:
            allowed, used, remaining = await quota.check_quota(
                user_email, booking_date, duration,
            )
            if not allowed:
                await ack(
                    response_action="errors",
                    errors={
                        "block_book_end": (
                            f"Денний ліміт: використано {used}/{common.MAX_DAILY_BOOKING_MINUTES} хв. "
                            f"Залишилось лише {remaining} хв на сьогодні."
                        ),
                    },
                )
                return

        await ack(response_action="update", view=common.skeleton_view("Бронювання"))

        try:
            # ── Live availability re-check ───────────────────────────────
            try:
                latest_slots = await yarooms.get_space_availability(
                    room_id, booking_date, start_time, end_time,
                )
            except Exception as avail_err:
                logger.warning(
                    f"Book by Room re-check failed: room={room_id}, date={booking_date}, "
                    f"err={type(avail_err).__name__}: {avail_err}"
                )
                latest_slots = []

            latest_available = common._normalized_available_slots(
                latest_slots, apply_duration_cap=False,
            )
            still_available = any(
                common._covers_interval(slot, start_time, end_time)
                for slot in latest_available
            )
            if not still_available:
                # Fallback: if interval re-check disagrees with the schedule UI,
                # validate against a fresh day schedule before rejecting.
                try:
                    day_windows = await yarooms.get_space_day_schedule(room_id, booking_date)
                    still_available = any(
                        common._covers_interval((w["start"], w["end"]), start_time, end_time)
                        for w in day_windows
                    )
                    if still_available:
                        logger.info(
                            f"Book by Room boundary fallback accepted: room={room_id}, "
                            f"date={booking_date}, interval={start_time}-{end_time}"
                        )
                except Exception as day_err:
                    logger.warning(
                        f"Book by Room day-schedule fallback failed: room={room_id}, "
                        f"date={booking_date}, err={type(day_err).__name__}: {day_err}"
                    )
            if not still_available:
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=common.simple_modal(
                        "Інтервал недоступний",
                        "❌ Обраний час більше недоступний — кімнату могли щойно забронювати.",
                    ),
                )
                return

            # ── Create booking ───────────────────────────────────────────
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
                    f"Book by Room create_booking failed: room={room_id}, date={booking_date}, "
                    f"start={start_time}, end={end_time}, err={type(book_err).__name__}: {book_err}"
                )
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=common.error_modal_with_context(
                        "Помилка бронювання",
                        "❌ Не вдалося забронювати кімнату. Спробуйте ще раз.",
                        [f"Деталі: `{str(book_err)[:120]}`"],
                    ),
                )
                return

            # ── Record quota ONLY after success ──────────────────────────
            if user_email and duration > 0:
                await quota.record_booking(user_email, booking_date, duration)

            booking_id = yarooms.extract_booking_id(booking_result)

            room_name = await common.safe_get_room_name(yarooms, room_id)

            await client.views_update(
                view_id=body["view"]["id"],
                view={
                    "type": "modal",
                    "title": {"type": "plain_text", "text": "Бронювання підтверджено", "emoji": False},
                    "close": {"type": "plain_text", "text": "Готово", "emoji": False},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"✅ Заброньовано *{room_name}* на *{booking_date}* "
                                    f"з *{start_time}* до *{end_time}*."
                                ),
                            },
                        },
                        {
                            "type": "context",
                            "elements": [
                                {"type": "mrkdwn", "text": "Ваше бронювання додано в Yarooms."}
                            ],
                        },
                    ],
                },
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
        except Exception as e:
            logger.error(f"Error in room time booking: {e}", exc_info=True)
            await client.views_update(
                view_id=body["view"]["id"],
                view=common.simple_modal(
                    "Помилка бронювання",
                    "❌ Не вдалося завершити це бронювання. Спробуйте ще раз.",
                ),
            )

    # ── Legacy slot-button handler (kept for stale modals) ───────────────

    @app.action("action_book_specific_slot")
    async def handle_book_specific_slot(ack, body, client, logger):
        """Book one selected slot from the room schedule modal."""
        await ack()
        try:
            action = body["actions"][0]
            room_id, start_time, end_time = action["value"].rsplit("_", 2)
            user_id = body["user"]["id"]

            duration = common._duration_minutes(start_time, end_time)
            if duration <= 0 or duration > common.MAX_BOOKING_MINUTES:
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=common.simple_modal(
                        "Бронювання відхилено",
                        f"❌ Цей інтервал перевищує ліміт *{common.MAX_BOOKING_HOURS} год* на одне бронювання.",
                    ),
                )
                return

            booking_date = body["view"].get("private_metadata") or common.get_local_now().strftime("%Y-%m-%d")

            if common._is_past_slot(booking_date, start_time):
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=common.simple_modal(
                        "Час минув",
                        "❌ Цей часовий інтервал уже минув. Оновіть розклад та оберіть майбутній.",
                    ),
                )
                return

            try:
                latest_slots = await yarooms.get_space_availability(
                    room_id, booking_date, start_time, end_time,
                )
            except Exception as avail_err:
                logger.warning(
                    f"Book by Room re-check failed: room={room_id}, date={booking_date}, "
                    f"err={type(avail_err).__name__}: {avail_err}"
                )
                latest_slots = []

            latest_available = common._normalized_available_slots(latest_slots, apply_duration_cap=False)
            still_available = any(
                common._covers_interval(available_slot, start_time, end_time)
                for available_slot in latest_available
            )
            if not still_available:
                # Legacy-flow fallback for interval/schedule boundary mismatches.
                try:
                    day_windows = await yarooms.get_space_day_schedule(room_id, booking_date)
                    still_available = any(
                        common._covers_interval((w["start"], w["end"]), start_time, end_time)
                        for w in day_windows
                    )
                    if still_available:
                        logger.info(
                            f"Book by Room legacy boundary fallback accepted: room={room_id}, "
                            f"date={booking_date}, interval={start_time}-{end_time}"
                        )
                except Exception as day_err:
                    logger.warning(
                        f"Book by Room legacy day-schedule fallback failed: room={room_id}, "
                        f"date={booking_date}, err={type(day_err).__name__}: {day_err}"
                    )
            if not still_available:
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=common.simple_modal(
                        "Інтервал недоступний",
                        "❌ Цей інтервал більше недоступний. Оновіть розклад і оберіть інший.",
                    ),
                )
                return

            user_email = await common.get_user_email(client, user_id)
            logger.debug(f"Book by Room resolved email for {user_id}: '{user_email}'")

            # ── Daily quota check ─────────────────────────────────────────
            if user_email and duration > 0:
                allowed, used, remaining = await quota.check_quota(
                    user_email, booking_date, duration,
                )
                if not allowed:
                    await client.views_update(
                        view_id=body["view"]["id"],
                        view=common.quota_exceeded_modal(
                            used, remaining, duration,
                            common.MAX_DAILY_BOOKING_MINUTES,
                        ),
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
                    f"Book by Room create_booking failed: room={room_id}, date={booking_date}, "
                    f"start={start_time}, end={end_time}, err={type(book_err).__name__}: {book_err}"
                )
                error_detail = str(book_err)[:120]
                await client.views_update(
                    view_id=body["view"]["id"],
                    view=common.error_modal_with_context(
                        "Помилка бронювання",
                        "❌ Не вдалося забронювати кімнату — можливо, її щойно зайняли. Спробуйте ще раз.",
                        [f"Деталі: `{error_detail}`"],
                    ),
                )
                return

            # ── Record quota ONLY after successful booking ────────────────
            if user_email and duration > 0:
                await quota.record_booking(user_email, booking_date, duration)

            booking_id = yarooms.extract_booking_id(booking_result)

            room_name = await common.safe_get_room_name(yarooms, room_id)

            await client.views_update(
                view_id=body["view"]["id"],
                view={
                    "type": "modal",
                    "title": {"type": "plain_text", "text": "Бронювання підтверджено", "emoji": False},
                    "close": {"type": "plain_text", "text": "Готово", "emoji": False},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"✅ Ви забронювали кімнату з *{start_time}* до *{end_time}* на *{booking_date}*.",
                            },
                        },
                        {
                            "type": "context",
                            "elements": [
                                {"type": "mrkdwn", "text": "Ваше бронювання додано в Yarooms."}
                            ],
                        },
                    ],
                },
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
        except Exception as e:
            logger.error(f"Error booking specific slot: {e}")
            await client.views_update(
                view_id=body["view"]["id"],
                view=common.simple_modal(
                    "Помилка бронювання",
                    "Не вдалося завершити це бронювання. Можливо, інтервал уже недоступний.",
                ),
            )
