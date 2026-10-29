"""Public link paths — the ONE builder for every referral / partner-direct link GoRefer
generates, and the matcher for the program-prefixed routes (owner decision 2026-10-29).

Two link families resolve to the same engine:

    bare (unchanged, already shared widely)   prefixed (program-branded)
    /open                                     /{url_prefix}/open
    /r/{client_id}                            /{url_prefix}/r/{client_id}
    /r/{channel}/{client_id}                  /{url_prefix}/r/{channel}/{client_id}

`url_prefix` is a column on `ReferralProgram` (Zerodha = `zerodha`), never a route
literal — a second partner gets its own word by data, not by a deploy (CLAUDE.md §4).
Every link GoRefer GENERATES uses the prefixed form when the active program has a
prefix, and the bare form otherwise; both forms are always served.

Paths only (leading `/`, no host) — callers keep their own host convention.
"""
from __future__ import annotations

from .models import ReferralProgram
from .redirect_service import get_active_program


def program_url_prefix(tenant=None) -> str:
    """The active program's link word, lowercased; "" when it has none (or none exists)."""
    try:
        program = get_active_program(tenant)
    except ReferralProgram.DoesNotExist:
        return ""
    return (program.url_prefix or "").strip().lower()


def _prefixed(path: str, tenant) -> str:
    prefix = program_url_prefix(tenant)
    return f"/{prefix}{path}" if prefix else path


def referral_path(client_id: str, *, channel: str | None = None, tenant=None) -> str:
    """`/{prefix}/r/[{channel}/]{client_id}` — or the bare `/r/...` form without a prefix."""
    channel_segment = f"{channel}/" if channel else ""
    return _prefixed(f"/r/{channel_segment}{client_id}", tenant)


def partner_direct_path(*, tenant=None) -> str:
    """`/{prefix}/open` — or the bare `/open` without a prefix."""
    return _prefixed("/open", tenant)


def matches_program_prefix(tenant, value: str) -> bool:
    """True when `value` is the link word of the program the redirect engine serves.

    Deliberately the ACTIVE program's word only, not any program's: the engine resolves
    one program per tenant, so accepting another program's word would send its visitors
    to the wrong partner. Case-insensitive (`/Zerodha/r/...` works)."""
    prefix = program_url_prefix(tenant)
    return bool(prefix) and (value or "").lower() == prefix
