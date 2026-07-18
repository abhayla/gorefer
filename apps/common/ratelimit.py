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

from django.conf import settings
from django.core.cache import cache


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


def hit(scope: str, ident: str, *, limit: int, window: int) -> tuple[bool, int]:
    """Register one hit. Returns (allowed, retry_after_seconds).

    A no-op that always allows when RATELIMIT_ENABLED is off (dev/CI).
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
        cache.add(key, 1, timeout=window)
        count = 1
    if count > limit:
        return False, window
    return True, 0


def check_rate(scope: str, ident: str, *, limit: int, window: int) -> None:
    """hit() + raise RateLimited when the quota is exceeded."""
    allowed, retry_after = hit(scope, ident, limit=limit, window=window)
    if not allowed:
        raise RateLimited(retry_after)


def client_ip(request) -> str:
    """Best-effort caller IP for rate-limit keying. Uses the trusted-proxy hop so a
    spoofed XFF can't split an attacker across many buckets."""
    from apps.common.netaddr import trusted_client_ip

    return trusted_client_ip(request) or "unknown"
