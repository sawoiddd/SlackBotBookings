async def notify_booking_in_chat(
    client,
    logger,
    user_id: str,
    room_name: str,
    booking_date: str,
    start_time: str,
    end_time: str,
) -> None:
    """Send a booking confirmation DM with room and time details."""
    try:
        await client.chat_postMessage(
            channel=user_id,
            text=(
                "Booking confirmed!\n"
                f"Room: {room_name}\n"
                f"Date: {booking_date}\n"
                f"Time: {start_time} - {end_time}"
            ),
        )
    except Exception as notify_error:
        logger.warning(f"Could not send booking confirmation message: {notify_error}")


