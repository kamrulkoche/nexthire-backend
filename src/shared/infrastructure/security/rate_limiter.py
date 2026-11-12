"""In-process rate limiting, for the endpoints where an attacker gets to retry.

Ported from hgs-backend unchanged apart from the limiter instances at the
bottom. sp-company-backend's limiter needs Redis; this one needs nothing: a
fixed window in a dict, guarded by a lock.

**Know what this does and does not buy you.** The counters live in one process's
memory, so:

- Across several workers, each worker enforces the limit separately. Four
  Uvicorn workers means four times the configured allowance.
- A restart forgets every counter.

It still closes the case that matters here. Online password guessing needs
thousands of attempts against one account; five per fifteen minutes stops that
whether or not the count is shared perfectly. It is NOT a defence against a
distributed flood — that belongs at the reverse proxy, which sees every worker.

Fixed window rather than sliding: a sliding window needs the timestamp of every
request, and the burst a fixed window permits at a boundary (2× the limit across
two adjacent windows) is irrelevant against a five-per-quarter-hour budget.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

from fastapi import HTTPException, Request, status

from ...utils.config import settings
from ..logging import get_logger

logger = get_logger(__name__)


@dataclass
class _Window:
    """One caller's counter for the current window."""

    count: int = 0
    started_at: float = field(default_factory=time.monotonic)


class RateLimiter:
    """Fixed-window rate limiter keyed by an arbitrary string.

    Thread-safe: FastAPI runs sync dependencies in a thread pool, so two
    requests genuinely execute this concurrently and a bare ``dict`` read,
    increment and write would lose counts under exactly the load that matters.
    """

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int,
        name: str = "default",
        enabled: Callable[[], bool] = lambda: True,
    ):
        """Configure the limiter.

        Args:
            limit: Requests permitted per window
            window_seconds: Window length
            name: Label used in log lines
            enabled: Read on every check; when it returns False every attempt
                is allowed and nothing is counted
        """
        self.limit = limit
        self.window_seconds = window_seconds
        self.name = name
        self.enabled = enabled
        self._windows: Dict[str, _Window] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> Tuple[bool, int]:
        """Record an attempt and report whether it is allowed.

        Args:
            key: Caller identity — an IP, or an IP plus the submitted email

        Returns:
            ``(allowed, retry_after_seconds)``. ``retry_after`` is 0 when
            allowed.
        """
        if not self.enabled():
            return True, 0

        now = time.monotonic()

        with self._lock:
            self._evict_expired(now)

            window = self._windows.get(key)
            if window is None or now - window.started_at >= self.window_seconds:
                self._windows[key] = _Window(count=1, started_at=now)
                return True, 0

            window.count += 1
            if window.count > self.limit:
                elapsed = now - window.started_at
                retry_after = max(1, int(self.window_seconds - elapsed))
                return False, retry_after

            return True, 0

    def reset(self, key: str) -> None:
        """Forget a caller's counter.

        Called after a SUCCESSFUL login, so that someone who mistyped their
        password twice and then got it right is not still one attempt from a
        lockout for the rest of the window.

        Args:
            key: The same key that was passed to ``check``
        """
        with self._lock:
            self._windows.pop(key, None)

    def _evict_expired(self, now: float) -> None:
        """Drop windows that have elapsed.

        Without this the dict is an unbounded memory leak: every distinct IP
        that ever hit the endpoint keeps an entry forever. Called under the
        lock, from ``check`` — a background sweeper would be a second moving
        part for a dict that stays small.

        Args:
            now: Current monotonic time
        """
        expired = [
            key
            for key, window in self._windows.items()
            if now - window.started_at >= self.window_seconds
        ]
        for key in expired:
            del self._windows[key]


def client_key(request: Request, suffix: Optional[str] = None) -> str:
    """Build a limiter key from the request's origin.

    Prefers the left-most ``X-Forwarded-For`` entry, because in deployment this
    service sits behind a proxy and ``request.client.host`` would then be the
    proxy — one key for every user on earth.

    **That header is client-supplied and trivially forged**, so this is only
    sound when the proxy in front overwrites it. It does not weaken anything
    relative to having no limiter: a forged header buys an attacker the
    unlimited attempts they would have had anyway.

    Args:
        request: The incoming request
        suffix: Extra key material, e.g. the submitted email, so one attacker
            cannot lock every account from one address by cycling addresses

    Returns:
        The limiter key
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        origin = forwarded.split(",")[0].strip()
    else:
        origin = request.client.host if request.client else "unknown"

    return f"{origin}:{suffix}" if suffix else origin


def enforce(limiter: RateLimiter, key: str) -> None:
    """Apply a limiter, raising 429 when the caller is over budget.

    Raises ``HTTPException`` rather than a domain exception deliberately: this
    runs at the API boundary, where the rule already is that dependencies raise
    HTTP errors and use cases raise domain ones. ``http_exception_handler``
    reshapes it into the standard error envelope.

    Args:
        limiter: The limiter to consult
        key: Caller key from ``client_key``

    Raises:
        HTTPException: 429 with a ``Retry-After`` header
    """
    allowed, retry_after = limiter.check(key)
    if allowed:
        return

    logger.warning(f"Rate limit hit on '{limiter.name}' for key {key!r}")
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=(
            f"Too many attempts. Please wait {retry_after} seconds before trying again."
        ),
        headers={"Retry-After": str(retry_after)},
    )


#: Limiter for `/auth/login`. Five attempts per fifteen minutes per
#: (address, email) pair — generous for a person who forgot which password they
#: used, useless for a script working through a word list.
#: ``AUTH_RATE_LIMIT_ENABLED=false`` switches it (and the register limiter) off
#: in dev/test only — see ``Settings.auth_rate_limit_active``.
login_limiter = RateLimiter(
    limit=5,
    window_seconds=15 * 60,
    name="auth:login",
    enabled=lambda: settings.auth_rate_limit_active,
)

#: Limiter for `/auth/register` — the one anonymous WRITE. Five accounts per
#: hour per address: enough for a household sharing a connection, too few to
#: mint accounts in bulk.
register_limiter = RateLimiter(
    limit=5,
    window_seconds=60 * 60,
    name="auth:register",
    enabled=lambda: settings.auth_rate_limit_active,
)

#: Limiter for a seeker asking for fresh AI recommendations. Each refresh can
#: cost a Gemini call, so it is keyed per user and kept small.
recommendation_limiter = RateLimiter(
    limit=10, window_seconds=60 * 60, name="app:recommendations"
)

#: Limiter for an admin starting a collection run by hand. A run fetches from
#: a third party, which has its own limits we should not trip.
manual_run_limiter = RateLimiter(limit=20, window_seconds=60 * 60, name="admin:run")

#: Limiter for a signed-in user changing their own password. Keyed by user id:
#: the caller is authenticated, so this bounds guessing the CURRENT password
#: from a session someone left open — the same five-per-quarter-hour budget a
#: sign-in gets.
password_change_limiter = RateLimiter(
    limit=5, window_seconds=15 * 60, name="account:password"
)

#: Lead Finder: searches a lead finder may START per hour, keyed per user. The
#: real cost bound is the daily Places request quota (counted in the
#: database); this stops a script from queueing searches back to back.
lead_search_limiter = RateLimiter(
    limit=settings.lead_searches_per_hour, window_seconds=60 * 60, name="lead:search"
)

#: Lead Finder: "Refresh from Google" (one Place Details request each) per hour,
#: keyed per user. Refreshes are not part of a search, so this is their budget.
lead_refresh_limiter = RateLimiter(
    limit=60, window_seconds=60 * 60, name="lead:refresh"
)

#: Lead Finder: export files per hour, keyed per user. Each builds a file of up
#: to 5000 rows in memory.
lead_export_limiter = RateLimiter(limit=60, window_seconds=60 * 60, name="lead:export")
