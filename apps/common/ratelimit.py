"""Lightweight fixed-window rate limiter (Fable5 H3).

No Redis (ADR-024) — backed by the DB cache (settings.CACHES 'default'), so counters
are shared across gunicorn workers. A per-process LocMem counter would let each worker
grant the full quota; the DB cache makes the limit global.

Fixed-window (not sliding) is deliberately simple and cheap: one atomic incr per hit.
The worst case is 2× burst at a window boundary — acceptable for anti-spam/abuse on
public endpoints. `RATELIMIT_ENABLED` gates it off in dev/CI so test loops aren't
throttled.

Usage (Django Ninja / view):
    from apps.common.ratelimit import check_rate, RateLimited
    check_rate("leads", client_ip(request), limit=settings.RATELIMIT_LEADS_MAX,
               window=settings.RATELIMIT_API_WINDOW)  # raises RateLimited on exceed
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError

logger = logging.getLogger("gorefer.ratelimit")

# One loud line per process, not one per request: a missing cache table is hit on EVERY
# rate-limited request, and a log line per hit buries the message it is trying to send.
_backend_failure_logged = False


class RateLimited(Exception):
    """Raised when a caller exceeds its window quota. `retry_after` is seconds."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"rate limited; retry after {retry_after}s")


def _bucket(scope: str, ident: str, window: int) -> str:
    # A coarse window epoch keeps the key stable within the window and rolls over after.
    # (No wall-clock import at module import; time is read per-call.)
    import time

    epoch = int(time.time()) // max(1, window)
    return f"rl:{scope}:{ident}:{epoch}"


def _degrade_open(exc: Exception) -> tuple[bool, int]:
    """Allow the request, and say so once, when the cache backend cannot be used."""
    global _backend_failure_logged

    if not _backend_failure_logged:
        _backend_failure_logged = True
        logger.error(
            "RATE LIMITER DISABLED — the DB cache backend is unusable (%s: %s). Requests "
            "are being served WITHOUT rate limiting. Fix on the box with: "
            "python manage.py createcachetable",
            exc.__class__.__name__, exc,
        )
    return True, 0


def hit(scope: str, ident: str, *, limit: int, window: int) -> tuple[bool, int]:
    """Register one hit. Returns (allowed, retry_after_seconds).

    A no-op that always allows when RATELIMIT_ENABLED is off (dev/CI).

    DEGRADES OPEN when the DB cache backend is unusable (T-162). The cache table is
    created by `manage.py createcachetable`, a step that is easy to miss on a fresh box
    or after a DB restore — and when it is missing, every cache call raises
    ProgrammingError. Before this, that turned a *missing anti-spam counter* into a 500
    on the public lead form and the login/OTP screens: the page died rather than the
    limit. Allowing the request (loudly, once per process) is the right trade — an
    unthrottled endpoint is a smaller failure than an unreachable one, and the log line
    names the exact command that fixes it.
    """
    if not getattr(settings, "RATELIMIT_ENABLED", False):
        return True, 0
    key = _bucket(scope, ident, window)
    # add() sets to 1 only if absent (with TTL); incr() bumps an existing counter.
    try:
        added = cache.add(key, 1, timeout=window)
        count = 1 if added else cache.incr(key)
    except ValueError:
        # Key expired between add() and incr() — treat as a fresh window.
        try:
            cache.add(key, 1, timeout=window)
        except DatabaseError as exc:
            return _degrade_open(exc)
        count = 1
    except DatabaseError as exc:
        return _degrade_open(exc)
    if count > limit:
        return False, window
    return True, 0


def check_rate(scope: str, ident: str, *, limit: int, window: int) -> None:
    """hit() + raise RateLimited when the quota is exceeded."""
    allowed, retry_after = hit(scope, ident, limit=limit, window=window)
    if not allowed:
        raise RateLimited(retry_after)


def counter_value(key: str) -> int:
    """Read a counter, degrading to 0 when the cache backend is unusable.

    For call sites that keep their own counter in the same DB cache (the admin
    login-attempt lock). They fail exactly the same way as hit() on a missing cache
    table, so they degrade through the same door instead of 500-ing the login page.
    """
    try:
        return int(cache.get(key) or 0)
    except DatabaseError as exc:
        _degrade_open(exc)
        return 0


def bump_counter(key: str, *, window: int) -> None:
    """Increment a counter (creating it with a TTL), degrading to a no-op on failure."""
    try:
        if cache.add(key, 1, timeout=window) is False:
            cache.incr(key)
    except ValueError:
        try:
            cache.add(key, 1, timeout=window)
        except DatabaseError as exc:
            _degrade_open(exc)
    except DatabaseError as exc:
        _degrade_open(exc)


def clear_counter(key: str) -> None:
    """Delete a counter, degrading to a no-op when the cache backend is unusable."""
    try:
        cache.delete(key)
    except DatabaseError as exc:
        _degrade_open(exc)


def client_ip(request) -> str:
    """Best-effort caller IP for rate-limit keying. Uses the trusted-proxy hop so a
    spoofed XFF can't split an attacker across many buckets."""
    from apps.common.netaddr import trusted_client_ip

    return trusted_client_ip(request) or "unknown"
