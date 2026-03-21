"""Per-user daily booking quota tracker.

Tracks total booked minutes per user per day.  Uses **Redis** as the primary
store (key: ``yarooms:daily_quota:<email>:<date>``, auto-expires after 48 h)
with an automatic **in-memory fallback** when Redis is unavailable.

The counter is incremented **only after** the Yarooms ``create_booking`` API
call succeeds, so failed/rejected attempts never consume quota.
"""

import logging
import time
from utils.booking_utils import MAX_DAILY_BOOKING_MINUTES

logger = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "yarooms:daily_quota:"
_REDIS_TTL_SECONDS = 48 * 3600  # auto-expire quota keys after 48 h

# In-memory fallback: simple dict keyed by "email:date" → total minutes.
# Entries older than 48 h are lazily purged.
_MEMORY_STORE: dict[str, tuple[int, float]] = {}   # key → (minutes, created_ts)
_MEMORY_TTL = 48 * 3600


def _mem_key(user_email: str, date: str) -> str:
    return f"{user_email.lower().strip()}:{date}"


def _mem_cleanup() -> None:
    """Lazily remove expired in-memory entries."""
    now = time.time()
    expired = [k for k, (_, ts) in _MEMORY_STORE.items() if now - ts > _MEMORY_TTL]
    for k in expired:
        del _MEMORY_STORE[k]


class DailyQuotaTracker:
    """Track booked minutes per user per day via Redis + in-memory fallback."""

    def __init__(self, max_daily_minutes: int = MAX_DAILY_BOOKING_MINUTES):
        self.max_daily_minutes = max_daily_minutes
        self._redis = None

    def set_redis_client(self, redis_client) -> None:
        """Attach an async Redis client (same one used for spaces cache)."""
        self._redis = redis_client

    # ── read ─────────────────────────────────────────────────────────────

    async def get_used_minutes(self, user_email: str, date: str) -> int:
        """Return total booked minutes for *user_email* on *date*."""
        rkey = f"{_REDIS_KEY_PREFIX}{user_email.lower().strip()}:{date}"

        # Try Redis first
        if self._redis:
            try:
                val = await self._redis.get(rkey)
                if val is not None:
                    return int(val)
            except Exception as exc:
                logger.debug(f"Quota Redis GET failed ({exc}); falling back to memory")

        # In-memory fallback
        _mem_cleanup()
        entry = _MEMORY_STORE.get(_mem_key(user_email, date))
        return entry[0] if entry else 0

    # ── check ────────────────────────────────────────────────────────────

    async def check_quota(
        self, user_email: str, date: str, new_minutes: int,
    ) -> tuple[bool, int, int]:
        """Check whether *new_minutes* fit inside the daily allowance.

        Returns:
            ``(allowed, used_minutes, remaining_minutes)``
        """
        used = await self.get_used_minutes(user_email, date)
        remaining = max(0, self.max_daily_minutes - used)
        allowed = new_minutes <= remaining
        logger.debug(
            f"Quota check: email={user_email}, date={date}, "
            f"used={used}, new={new_minutes}, remaining={remaining}, allowed={allowed}"
        )
        return allowed, used, remaining

    # ── write (call ONLY after create_booking succeeds) ──────────────────

    async def record_booking(
        self, user_email: str, date: str, minutes: int,
    ) -> int:
        """Increment the user's daily total by *minutes*.

        Returns the new total.  Called **only** after ``create_booking``
        succeeds so failed attempts never consume quota.
        """
        rkey = f"{_REDIS_KEY_PREFIX}{user_email.lower().strip()}:{date}"
        new_total: int | None = None

        # Try Redis
        if self._redis:
            try:
                new_total = await self._redis.incrby(rkey, minutes)
                # Ensure TTL is set (idempotent — only sets if no TTL yet)
                ttl = await self._redis.ttl(rkey)
                if ttl < 0:
                    await self._redis.expire(rkey, _REDIS_TTL_SECONDS)
            except Exception as exc:
                logger.warning(f"Quota Redis INCRBY failed ({exc}); falling back to memory")
                new_total = None

        # In-memory fallback (always kept in sync for resilience)
        mk = _mem_key(user_email, date)
        _mem_cleanup()
        prev, ts = _MEMORY_STORE.get(mk, (0, time.time()))
        mem_total = prev + minutes
        _MEMORY_STORE[mk] = (mem_total, ts)

        final = new_total if new_total is not None else mem_total
        logger.info(
            f"Quota recorded: email={user_email}, date={date}, "
            f"+{minutes} min, new_total={final}/{self.max_daily_minutes}"
        )
        return final

    # ── diagnostics ──────────────────────────────────────────────────────

    def get_meta(self) -> dict:
        """Return debug metadata about the quota tracker."""
        return {
            "max_daily_minutes": self.max_daily_minutes,
            "backend": "redis" if self._redis else "memory",
            "memory_entries": len(_MEMORY_STORE),
        }

