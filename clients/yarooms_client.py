"""
Async client for the Yarooms REST API.

Documentation : https://api-docs.yarooms.com/#introduction
Auth options:
  1. Static API token     -> set YAROOMS_API_KEY in .env
  2. Email / password     -> set YAROOMS_EMAIL, YAROOMS_PASSWORD, YAROOMS_SUBDOMAIN in .env
     The classmethod `YaroomsClient.from_credentials(...)` authenticates once at startup
     and returns a ready-to-use client.

Cache:
  - When a Redis client is attached via `set_redis_client(redis)`, spaces are cached
    in Redis under key `yarooms:spaces` with a TTL of `SPACES_CACHE_FRESH_TTL_SECONDS`.
  - Stale-on-error fallback uses a second Redis key `yarooms:spaces:stale` that
    expires after `SPACES_CACHE_STALE_TTL_SECONDS`.
  - If Redis is unreachable, the client falls back to in-memory cache transparently.
  - Set `REDIS_URL=redis://localhost:6379/0` in .env to enable Redis.

Required scope: users:read.email (Slack) — needed to resolve user e-mail for bookings
"""

import aiohttp
import asyncio
import json
import time
from utils.booking_utils import _covers_interval, _to_hhmm, _to_minutes

try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
    _RedisType = aioredis.Redis
except ImportError:
    aioredis = None  # type: ignore[assignment]
    _REDIS_AVAILABLE = False
    _RedisType = None


YAROOMS_BASE_URL = "https://api.yarooms.com"
SPACES_CACHE_FRESH_TTL_SECONDS = 300
SPACES_CACHE_STALE_TTL_SECONDS = 86400
REDIS_KEY_FRESH = "yarooms:spaces"
REDIS_KEY_STALE = "yarooms:spaces:stale"
TARGET_SPACE_KEYWORDS = (
    "skype",
    "silent box",
    "silent-box",
    "silentbox",
)


class YaroomsClient:
    """Small async wrapper around the Yarooms REST API."""

    def __init__(self, api_key: str, base_url: str = YAROOMS_BASE_URL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._auth_email: str = ""
        self._auth_password: str = ""
        self._auth_subdomain: str = ""
        self._auth_refresh_lock = asyncio.Lock()

        # Persistent HTTP session for connection pooling (lazy-initialized)
        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()

        # Redis client — injected via set_redis_client()
        self._redis: "aioredis.Redis | None" = None

        # In-memory fallback cache
        self._spaces_cache_enabled = True
        self._spaces_cache_fresh_ttl_seconds = SPACES_CACHE_FRESH_TTL_SECONDS
        self._spaces_cache_stale_ttl_seconds = SPACES_CACHE_STALE_TTL_SECONDS
        self._spaces_cache_data: list[dict] = []
        self._spaces_cache_present = False
        self._spaces_cache_last_success_at: float | None = None
        self._spaces_cache_last_attempt_at: float | None = None
        self._spaces_cache_last_error: str | None = None
        self._spaces_cache_lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy-initialize and return the persistent HTTP session."""
        if self._session is None:
            async with self._session_lock:
                if self._session is None:
                    self._session = aiohttp.ClientSession(headers=self._headers)
        return self._session

    async def close(self) -> None:
        """Close the persistent HTTP session on shutdown."""
        if self._session is not None:
            await self._session.close()
            self._session = None

    # ── Redis wiring ─────────────────────────────────────────────────────────

    def set_redis_client(self, redis_client) -> None:
        """Attach an async Redis client for distributed caching.

        Args:
            redis_client: An instance of ``redis.asyncio.Redis``.
                Pass ``None`` to revert to in-memory-only cache.
        """
        self._redis = redis_client

    # ── spaces cache helpers ─────────────────────────────────────────────────

    @staticmethod
    def _space_name(space: dict) -> str:
        return str(
            space.get("name")
            or space.get("title")
            or space.get("space_name")
            or space.get("displayName")
            or ""
        )

    @staticmethod
    def _to_hhmm_safe(value: str) -> str:
        """Parse API time-like values into HH:MM (seconds rounded up)."""
        minutes = _to_minutes(str(value), round_up_seconds=True)
        return _to_hhmm(minutes) if minutes is not None else ""

    def _availability_from_status_snapshot(
        self,
        snapshot: dict,
        *,
        requested_start: str | None = None,
        requested_end: str | None = None,
        requested_date: str | None = None,
    ) -> list[dict]:
        """Normalize tenant-specific status snapshots into free-slot lists.

        Some Yarooms tenants return room/day snapshots with a current ``status`` and
        ``next_change`` metadata instead of explicit slot arrays. Prefer the explicit
        ``next_change.interval`` free window when present, otherwise fall back to the
        older status/change heuristic.
        """
        if not isinstance(snapshot, dict):
            return []

        import logging
        _log = logging.getLogger(__name__)

        status = snapshot.get("status")
        next_change = snapshot.get("next_change") or {}
        space_name = snapshot.get("space_name", "?")

        _log.debug(
            f"[snapshot] room={space_name}, status={status}, "
            f"next_change={next_change}, requested={requested_start}-{requested_end}, date={requested_date}"
        )

        # Interval-aware fast path: for requests that provide start/end, many
        # tenants return status-only answers for the requested interval itself.
        if requested_start and requested_end:
            booked_interval = (next_change.get("booked_interval") or {}) if isinstance(next_change, dict) else {}
            booked_start = self._to_hhmm_safe(str(booked_interval.get("start") or ""))
            booked_end = self._to_hhmm_safe(str(booked_interval.get("end") or ""))

            # Extract raw change datetime and determine if it falls on the requested date
            raw_change = str(next_change.get("change") or "") if isinstance(next_change, dict) else ""
            next_change_time = self._to_hhmm_safe(raw_change)
            # Check if the next_change date matches the requested date.
            # If it's a different day, the boundary does NOT apply today.
            next_change_is_same_day = True
            if requested_date and raw_change and len(raw_change) >= 10:
                change_date = raw_change[:10]  # e.g. "2026-03-21"
                if change_date != requested_date:
                    next_change_is_same_day = False
                    _log.debug(
                        f"[snapshot] room={space_name}: next_change date {change_date} "
                        f"!= requested date {requested_date}, boundary ignored"
                    )

            req_start_minutes = _to_minutes(requested_start)
            req_end_minutes = _to_minutes(requested_end, round_up_seconds=True)
            booked_start_minutes = _to_minutes(booked_start) if booked_start else None
            booked_end_minutes = _to_minutes(booked_end, round_up_seconds=True) if booked_end else None
            next_change_minutes = _to_minutes(next_change_time) if (next_change_time and next_change_is_same_day) else None

            # If Yarooms explicitly reports a booked interval overlapping the
            # requested time, treat room as unavailable regardless of status code.
            if (
                req_start_minutes is not None
                and req_end_minutes is not None
                and booked_start_minutes is not None
                and booked_end_minutes is not None
                and booked_start_minutes < req_end_minutes
                and booked_end_minutes > req_start_minutes
            ):
                _log.debug(
                    f"[snapshot] REJECTED room={space_name}: booked_interval "
                    f"{booked_start}-{booked_end} overlaps requested {requested_start}-{requested_end}"
                )
                return []

            if status in (0, "0", False):
                # If we know when the next booking starts ON THE SAME DAY,
                # requested interval must end on/before that boundary to remain
                # bookable.  BUT — only reject when the requested interval
                # actually *straddles* the boundary (starts before it, ends
                # after it).  If the entire request is at/after the boundary
                # the snapshot is not informative about that later window;
                # the API returned status=0 for the queried range so we trust it.
                if (
                    req_start_minutes is not None
                    and req_end_minutes is not None
                    and next_change_minutes is not None
                    and req_start_minutes < next_change_minutes
                    and req_end_minutes > next_change_minutes
                ):
                    _log.debug(
                        f"[snapshot] REJECTED room={space_name}: requested {requested_start}-{requested_end} "
                        f"straddles next_change boundary {next_change_time} (same day)"
                    )
                    return []
                if (
                    next_change_minutes is not None
                    and req_start_minutes is not None
                    and req_start_minutes >= next_change_minutes
                ):
                    _log.debug(
                        f"[snapshot] ACCEPTED room={space_name}: status=0, next_change boundary "
                        f"{next_change_time} is before requested start {requested_start} — boundary ignored"
                    )
                _log.debug(
                    f"[snapshot] ACCEPTED room={space_name}: status=0 (free), "
                    f"next_change={next_change_time}, same_day={next_change_is_same_day}, "
                    f"requested={requested_start}-{requested_end}"
                )
                return [{"start": requested_start, "end": requested_end}]
            if status in (1, "1", True):
                _log.debug(
                    f"[snapshot] REJECTED room={space_name}: status=1 (occupied)"
                )
                return []

        interval = next_change.get("interval") or {}
        interval_start = self._to_hhmm_safe(str(interval.get("start") or ""))
        interval_end = self._to_hhmm_safe(str(interval.get("end") or ""))
        if interval_start and interval_end and _to_minutes(interval_end) > _to_minutes(interval_start):
            return [{"start": interval_start, "end": interval_end}]

        booked_interval = next_change.get("booked_interval") or {}
        booked_end = self._to_hhmm_safe(str(booked_interval.get("end") or ""))
        change = next_change.get("change") or ""
        change_time = self._to_hhmm_safe(str(change)) if change else ""

        if status in (0, "0", False):
            end = change_time or "23:59"
            return [{"start": "00:00", "end": end}]

        if status in (2, "2"):
            if booked_end and change_time and _to_minutes(change_time) > _to_minutes(booked_end):
                return [{"start": booked_end, "end": change_time}]
            if booked_end:
                return [{"start": booked_end, "end": "23:59"}]
            if change_time:
                return [{"start": change_time, "end": "23:59"}]
            return []

        if status in (1, "1", True):
            if change_time:
                return [{"start": change_time, "end": "23:59"}]
            return []

        return []

    def _filter_target_spaces(self, spaces: list[dict]) -> list[dict]:
        """Keep only Skype rooms and Silent Boxes."""
        return [
            s for s in spaces
            if any(kw in self._space_name(s).strip().lower() for kw in TARGET_SPACE_KEYWORDS)
        ]

    # ── Redis cache primitives ───────────────────────────────────────────────

    async def _redis_get_spaces(self) -> list[dict] | None:
        """Try to read the fresh spaces list from Redis. Returns None on miss/error."""
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(REDIS_KEY_FRESH)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    async def _redis_get_stale_spaces(self) -> list[dict] | None:
        """Try to read the stale fallback list from Redis. Returns None on miss/error."""
        if not self._redis:
            return None
        try:
            raw = await self._redis.get(REDIS_KEY_STALE)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
        return None

    async def _redis_set_spaces(self, spaces: list[dict]) -> None:
        """Write spaces list to Redis (fresh TTL + update stale key). Silently ignores errors."""
        if not self._redis:
            return
        try:
            payload = json.dumps(spaces)
            await self._redis.setex(REDIS_KEY_FRESH, SPACES_CACHE_FRESH_TTL_SECONDS, payload)
            await self._redis.setex(REDIS_KEY_STALE, SPACES_CACHE_STALE_TTL_SECONDS, payload)
        except Exception:
            pass

    async def _redis_delete_spaces(self) -> None:
        """Remove both Redis cache keys. Silently ignores errors."""
        if not self._redis:
            return
        try:
            await self._redis.delete(REDIS_KEY_FRESH, REDIS_KEY_STALE)
        except Exception:
            pass

    # ── public cache API ─────────────────────────────────────────────────────

    async def invalidate_spaces_cache(self) -> None:
        """Clear the spaces cache (Redis + in-memory)."""
        self._spaces_cache_data = []
        self._spaces_cache_present = False
        await self._redis_delete_spaces()

    def get_spaces_cache_meta(self) -> dict:
        """Return debug metadata for spaces cache state."""
        now = time.time()
        age = (
            now - self._spaces_cache_last_success_at
            if self._spaces_cache_last_success_at is not None
            else None
        )
        if not self._spaces_cache_present:
            state = "empty"
        elif age is not None and age <= self._spaces_cache_fresh_ttl_seconds:
            state = "fresh"
        else:
            state = "stale"

        return {
            "backend": "redis" if self._redis else "memory",
            "enabled": self._spaces_cache_enabled,
            "fresh_ttl_seconds": self._spaces_cache_fresh_ttl_seconds,
            "stale_ttl_seconds": self._spaces_cache_stale_ttl_seconds,
            "cached_count": len(self._spaces_cache_data) if self._spaces_cache_present else 0,
            "last_success_at_epoch": self._spaces_cache_last_success_at,
            "last_attempt_at_epoch": self._spaces_cache_last_attempt_at,
            "last_error": self._spaces_cache_last_error,
            "state": state,
        }

    async def get_spaces_cached(
        self,
        *,
        force_refresh: bool = False,
        allow_stale_on_error: bool = True,
    ) -> list[dict]:
        """Return spaces list from Redis (primary) or in-memory (fallback) cache.

        Decision order:
          1. If not force_refresh → try Redis fresh key.
          2. If Redis miss → check in-memory fresh hit.
          3. If still miss → acquire single-flight lock and fetch from Yarooms.
          4. On fetch error and allow_stale_on_error → try Redis stale, then in-memory stale.
          5. If no stale → re-raise the original exception.
        """
        if not self._spaces_cache_enabled:
            return await self.get_spaces()

        # 1. Fast path: Redis fresh hit
        if not force_refresh:
            cached = await self._redis_get_spaces()
            if cached:
                # Also warm the in-memory layer so Redis outage is covered
                self._spaces_cache_data = cached
                self._spaces_cache_present = True
                self._spaces_cache_last_success_at = time.time()
                return list(cached)

        # 2. Fast path: in-memory fresh hit
        now = time.time()
        if (
            not force_refresh
            and self._spaces_cache_present
            and self._spaces_cache_data
            and self._spaces_cache_last_success_at is not None
            and (now - self._spaces_cache_last_success_at) <= self._spaces_cache_fresh_ttl_seconds
        ):
            return list(self._spaces_cache_data)

        # 3. Refresh — single-flight lock prevents thundering herd
        async with self._spaces_cache_lock:
            # Re-check inside lock (another coroutine may have refreshed while we waited)
            if not force_refresh:
                cached = await self._redis_get_spaces()
                if cached:
                    self._spaces_cache_data = cached
                    self._spaces_cache_present = True
                    self._spaces_cache_last_success_at = time.time()
                    return list(cached)
                now = time.time()
                if (
                    self._spaces_cache_present
                    and self._spaces_cache_data
                    and self._spaces_cache_last_success_at is not None
                    and (now - self._spaces_cache_last_success_at)
                    <= self._spaces_cache_fresh_ttl_seconds
                ):
                    return list(self._spaces_cache_data)

            try:
                self._spaces_cache_last_attempt_at = time.time()
                spaces = await self.get_spaces()
                self._spaces_cache_data = list(spaces)
                self._spaces_cache_present = True
                self._spaces_cache_last_success_at = time.time()
                self._spaces_cache_last_error = None
                await self._redis_set_spaces(spaces)
                return list(spaces)
            except Exception as exc:
                self._spaces_cache_last_error = f"{type(exc).__name__}: {exc}"
                if allow_stale_on_error:
                    # 4a. Try Redis stale
                    stale = await self._redis_get_stale_spaces()
                    if stale:
                        return stale
                    # 4b. Try in-memory stale
                    now = time.time()
                    if (
                        self._spaces_cache_present
                        and self._spaces_cache_data
                        and self._spaces_cache_last_success_at is not None
                        and (now - self._spaces_cache_last_success_at)
                        <= self._spaces_cache_stale_ttl_seconds
                    ):
                        return list(self._spaces_cache_data)
                raise

    # ── factory: email / password auth ──────────────────────────────────────

    @classmethod
    async def from_credentials(
        cls,
        email: str,
        password: str,
        base_url: str,
        subdomain: str = "",
    ) -> "YaroomsClient":
        """Authenticate via email/password and return a ready client."""
        auth_url = f"{base_url.rstrip('/')}/api/auth"
        params: dict = {"email": email, "password": password}
        if subdomain:
            params["subdomain"] = subdomain

        async with aiohttp.ClientSession() as session:
            async with session.post(auth_url, params=params) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(
                        f"Yarooms auth failed (HTTP {resp.status}): {text[:200]}"
                    )
                body = await resp.json()

        token = (body.get("data") or {}).get("token") or body.get("token")
        if not token:
            raise RuntimeError("Yarooms auth response contained no token.")

        client = cls(api_key=token, base_url=base_url)
        client._auth_email = email
        client._auth_password = password
        client._auth_subdomain = subdomain
        return client

    async def _refresh_api_token(self) -> None:
        """Re-authenticate and update api_key (credentials mode only)."""
        if not (self._auth_email and self._auth_password):
            raise RuntimeError("Cannot refresh Yarooms token without stored credentials.")
        auth_url = f"{self.base_url}/api/auth"
        params: dict = {"email": self._auth_email, "password": self._auth_password}
        if self._auth_subdomain:
            params["subdomain"] = self._auth_subdomain

        async with self._auth_refresh_lock:
            async with aiohttp.ClientSession() as session:
                async with session.post(auth_url, params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(
                            f"Yarooms re-auth failed (HTTP {resp.status}): {text[:200]}"
                        )
                    body = await resp.json()
            token = (body.get("data") or {}).get("token") or body.get("token")
            if not token:
                raise RuntimeError("Yarooms re-auth response contained no token.")
            self.api_key = token

    # ── low-level helpers ────────────────────────────────────────────────────

    @property
    def _headers(self) -> dict:
        return {
            "X-Token": self.api_key,
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict | list:
        """Send an authenticated request, auto-refreshing token on 401."""
        can_refresh = bool(self._auth_email and self._auth_password)
        for attempt in range(2):
            session = await self._get_session()
            try:
                async with session.request(
                    method, f"{self.base_url}{path}", **kwargs
                ) as resp:
                    if resp.status == 401 and can_refresh and attempt == 0:
                        await self._refresh_api_token()
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientError:
                # Connection pool error — close session and retry once
                if self._session is not None:
                    await self._session.close()
                    self._session = None
                if attempt == 0:
                    continue
                raise
        raise RuntimeError("Yarooms request failed after auth refresh retry.")

    # ── spaces / rooms ───────────────────────────────────────────────────────

    async def get_spaces(self) -> list[dict]:
        """Fetch and filter spaces from Yarooms (no cache — always live)."""
        import logging
        logger = logging.getLogger(__name__)
        
        result = await self._request("GET", "/api/spaces")
        spaces: list[dict] = []
        if isinstance(result, list):
            spaces = result
        elif isinstance(result, dict):
            data = result.get("data")
            if isinstance(data, list):
                spaces = data
            elif isinstance(data, dict):
                spaces = data.get("list") or data.get("items") or []
            spaces = spaces or result.get("spaces", [])
        
        raw_count = len(spaces)
        filtered = self._filter_target_spaces(spaces)
        filtered_count = len(filtered)
        
        logger.info(
            f"Yarooms get_spaces: raw_count={raw_count}, filtered_count={filtered_count}, "
            f"filtering_keywords={TARGET_SPACE_KEYWORDS}"
        )
        
        # Log which rooms were filtered out (for debugging)
        if raw_count > filtered_count:
            filtered_out = [
                self._space_name(s) for s in spaces
                if not any(kw in self._space_name(s).strip().lower() for kw in TARGET_SPACE_KEYWORDS)
            ]
            logger.debug(f"Yarooms get_spaces: filtered_out_rooms={filtered_out[:10]}")
        
        return filtered

    async def get_space_availability(
        self,
        space_id: str,
        date: str,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[dict]:
        """Fetch available time slots for one space on a specific date."""
        params: dict[str, str] = {"spaces": space_id, "date": date}
        if start_time and end_time:
            params["start"] = start_time
            params["end"] = end_time

        result = await self._request(
            "GET", "/api/spaces/availability", params=params
        )
        if isinstance(result, dict):
            data = result.get("data", result.get("slots", []))
            if isinstance(data, list):
                result = data
            elif isinstance(data, dict):
                # Variant A: direct map by space id
                mapped = data.get(space_id) or data.get(str(space_id))
                if isinstance(mapped, list):
                    result = mapped
                elif isinstance(mapped, dict) and "status" in mapped:
                    result = self._availability_from_status_snapshot(
                        mapped,
                        requested_start=start_time,
                        requested_end=end_time,
                        requested_date=date,
                    )
                elif mapped is not None:
                    # Unknown shape — treat as empty to avoid crashes
                    result = []
                else:
                    # Variant B: nested map by date then by space id
                    day_map = data.get(date)
                    if isinstance(day_map, dict):
                        room_info = day_map.get(space_id) or day_map.get(str(space_id))
                        if isinstance(room_info, dict) and "status" in room_info:
                            result = self._availability_from_status_snapshot(
                                room_info,
                                requested_start=start_time,
                                requested_end=end_time,
                                requested_date=date,
                            )
                        else:
                            result = data.get("slots", [])
                    else:
                        result = data.get("slots", [])
            else:
                result = []
            if isinstance(result, list) and result and isinstance(result[0], dict) and "slots" in result[0]:
                room_item = next(
                    (
                        i for i in result
                        if str(i.get("spaceId") or i.get("space_id") or i.get("id")) == str(space_id)
                    ),
                    result[0],
                )
                result = room_item.get("slots", [])
        return result if isinstance(result, list) else []

    # ── search helpers ───────────────────────────────────────────────────────

    async def find_available_space(
        self, date: str, start_time: str, end_time: str
    ) -> dict | None:
        """Find the first space whose availability covers the requested interval."""
        spaces = await self.get_spaces()
        for space in spaces:
            try:
                slots = await self.get_space_availability(space["id"], date)
            except Exception:
                continue
            for slot in slots:
                s = slot.get("startTime") or slot.get("start", "")
                e = slot.get("endTime") or slot.get("end", "")
                if _covers_interval((str(s), str(e)), start_time, end_time):
                    return space
        return None

    # ── accounts (user lookup by email) ─────────────────────────────────────

    _accounts_cache: list[dict] | None = None
    _accounts_cache_at: float = 0
    _ACCOUNTS_CACHE_TTL = 600  # 10 min

    async def _get_accounts(self) -> list[dict]:
        """Fetch Yarooms accounts with in-memory cache."""
        now = time.time()
        if self._accounts_cache is not None and (now - self._accounts_cache_at) < self._ACCOUNTS_CACHE_TTL:
            return self._accounts_cache
        result = await self._request("GET", "/api/accounts")
        data = result if isinstance(result, list) else (result.get("data") or {})
        if isinstance(data, dict):
            accounts = data.get("list") or data.get("items") or []
        elif isinstance(data, list):
            accounts = data
        else:
            accounts = []
        self._accounts_cache = accounts
        self._accounts_cache_at = time.time()
        return accounts

    async def resolve_account_id(self, email: str) -> str | None:
        """Find the Yarooms account_id matching the given email. Returns None on miss."""
        if not email:
            return None
        target = email.strip().lower()
        accounts = await self._get_accounts()
        for acc in accounts:
            if (acc.get("email") or "").strip().lower() == target:
                return str(acc["id"])
        return None

    # ── bookings ─────────────────────────────────────────────────────────────

    async def create_booking(
        self,
        space_id: str,
        date: str,
        start_time: str,
        end_time: str,
        user_email: str = "",
        title: str = "Slack Booking",
    ) -> dict:
        """Create a Yarooms booking.

        When *user_email* is provided the method:
          1. Resolves the email → Yarooms account_id and tries to create
             the booking with ``account_id`` (on-behalf-of).
          2. If the account lookup fails or the API rejects the account_id
             (e.g. insufficient permissions), falls back to creating the
             booking under the authenticated token user and records the
             booker's email in the ``description`` field so it is visible
             in the Yarooms web UI.
        """
        # Yarooms /api/bookings expects form-encoded dates[] fields.
        effective_title = user_email if user_email else title
        payload: dict[str, str] = {
            "space_id": str(space_id),
            "dates[0][start]": f"{date} {start_time}",
            "dates[0][end]": f"{date} {end_time}",
            "title": effective_title,
        }

        # Always record the booker's email so it is visible in Yarooms web UI.
        if user_email:
            payload["description"] = f"Booked via Slack by {user_email}"

        account_id: str | None = None
        if user_email:
            try:
                account_id = await self.resolve_account_id(user_email)
            except Exception:
                account_id = None

        # Strategy 1: book on behalf of the resolved Yarooms account
        if account_id:
            try:
                payload_with_account = {**payload, "account_id": account_id}
                return await self._request("POST", "/api/bookings", data=payload_with_account)
            except Exception:
                pass  # fall through to strategy 2

        # Strategy 2: book under the authenticated bot account
        return await self._request("POST", "/api/bookings", data=payload)


