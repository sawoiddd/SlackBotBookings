"""
Async client for the Yarooms REST API.

Documentation : https://api-docs.yarooms.com/#introduction
Required key  : set "YAROOMS_API_KEY" in .env
Required scope: users:read.email (Slack) — needed to resolve user e-mail for bookings

Endpoint paths and response shapes below are based on standard Yarooms REST conventions.
Verify against the live docs and adjust `_parse_*` helpers if field names differ.
"""

import aiohttp


YAROOMS_BASE_URL = "https://api.yarooms.com"  # confirm / override via config["yarooms-base-url"]


class YaroomsClient:
    """Small async wrapper around the Yarooms REST API.

    The client centralizes authentication, basic response envelope handling,
    and a few higher-level booking helpers used by `home.py`.

    Notes:
    - Authentication uses a bearer token supplied via `api_key`.
    - `base_url` can be overridden via `YAROOMS_BASE_URL` in `.env`.
    - Endpoint paths and payload shapes should be verified against the live Yarooms API docs.
    """

    def __init__(self, api_key: str, base_url: str = YAROOMS_BASE_URL):
        """Create a Yarooms API client instance.

        Args:
            api_key: Bearer token used to authenticate all API requests.
            base_url: Base Yarooms API URL. Defaults to `YAROOMS_BASE_URL`.

        The trailing slash is removed from `base_url` so request paths can be appended safely.
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    # ── low-level helpers ────────────────────────────────────────────────────

    @property
    def _headers(self) -> dict:
        """Return default HTTP headers for authenticated JSON requests.

        Returns:
            A header dictionary with bearer authorization plus JSON content/accept headers.
        """
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict | list:
        """Send a single authenticated HTTP request to Yarooms.

        Args:
            method: HTTP method such as `GET` or `POST`.
            path: API path appended to `base_url`, for example `/spaces`.
            **kwargs: Extra arguments passed directly to `aiohttp.ClientSession.request`,
                such as `params={...}` or `json={...}`.

        Returns:
            The decoded JSON response body, usually a `dict` or `list`.

        Raises:
            aiohttp.ClientResponseError: If Yarooms returns a non-2xx HTTP response.
            aiohttp.ClientError: For network and transport-level request failures.
        """
        async with aiohttp.ClientSession(headers=self._headers) as session:
            async with session.request(
                method, f"{self.base_url}{path}", **kwargs
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    # ── spaces / rooms ───────────────────────────────────────────────────────

    async def get_spaces(self) -> list[dict]:
        """Fetch the list of bookable Yarooms spaces.

        Returns:
            A list of room/space dictionaries. The helper also unwraps common response
            envelopes like `{"data": [...]}` or `{"spaces": [...]}`.

        Example item:
            {"id": "abc123", "name": "Conference Room A", "capacity": 10}
        """
        result = await self._request("GET", "/spaces")
        # Unwrap common envelope patterns
        if isinstance(result, dict):
            result = result.get("data", result.get("spaces", []))
        return result

    async def get_space_availability(self, space_id: str, date: str) -> list[dict]:
        """Fetch available time slots for one space on a specific date.

        Args:
            space_id: Yarooms identifier of the room/space to inspect.
            date: Booking date in `YYYY-MM-DD` format.

        Returns:
            A list of availability slot dictionaries. Common envelope formats such as
            `{"data": [...]}` and `{"slots": [...]}` are unwrapped automatically.

        Expected slot shape:
            {"startTime": "09:00", "endTime": "10:00"}

        The calling code also tolerates `start` / `end` fallback keys.
        """
        result = await self._request(
            "GET", f"/spaces/{space_id}/availability", params={"date": date}
        )
        if isinstance(result, dict):
            result = result.get("data", result.get("slots", []))
        return result

    # ── search helpers ───────────────────────────────────────────────────────

    async def find_available_space(
        self, date: str, start_time: str, end_time: str
    ) -> dict | None:
        """Find the first space with a free slot covering a requested interval.

        Args:
            date: Booking date in `YYYY-MM-DD` format.
            start_time: Desired booking start time in `HH:MM` format.
            end_time: Desired booking end time in `HH:MM` format.

        Returns:
            The first matching space dictionary if any room has a slot that fully covers
            the requested `[start_time, end_time]` interval; otherwise `None`.

        Notes:
        - This helper iterates through all spaces sequentially.
        - If availability lookup fails for one space, that space is skipped and search continues.
        """
        spaces = await self.get_spaces()
        for space in spaces:
            try:
                slots = await self.get_space_availability(space["id"], date)
            except Exception:
                continue
            for slot in slots:
                s = slot.get("startTime") or slot.get("start", "")
                e = slot.get("endTime") or slot.get("end", "")
                if s <= start_time and e >= end_time:
                    return space
        return None

    # ── bookings ─────────────────────────────────────────────────────────────

    async def create_booking(
        self,
        space_id: str,
        date: str,
        start_time: str,
        end_time: str,
        user_email: str,
        title: str = "Slack Booking",
    ) -> dict:
        """Create a new Yarooms booking.

        Args:
            space_id: Yarooms identifier of the room/space to book.
            date: Booking date in `YYYY-MM-DD` format.
            start_time: Booking start time in `HH:MM` format.
            end_time: Booking end time in `HH:MM` format.
            user_email: Email address of the Slack user who is making the booking.
            title: Optional human-readable booking title. Defaults to `Slack Booking`.

        Returns:
            The decoded booking confirmation response from Yarooms, typically including
            a booking identifier and other metadata.

        Payload sent:
            {
                "spaceId": str,
                "date": "YYYY-MM-DD",
                "startTime": "HH:MM",
                "endTime": "HH:MM",
                "userEmail": str,
                "title": str,
            }

        Note:
            Field names may need to be adjusted if the live Yarooms API contract differs.
        """
        payload = {
            "spaceId": space_id,
            "date": date,
            "startTime": start_time,
            "endTime": end_time,
            "userEmail": user_email,
            "title": title,
        }
        return await self._request("POST", "/bookings", json=payload)


