"""Trusted client-IP resolution for auth-critical checks (Fable5 H2).

The webhook IP allowlists are a security control, so the caller IP MUST be resolved
from a hop the attacker cannot forge. `X-Forwarded-For` is a client-appendable list:
nginx's `proxy_add_x_forwarded_for` APPENDS the real peer, so the *first* entry is
attacker-controlled (`X-Forwarded-For: <zoho-ip>` would spoof `xff[0]`). The only
trustworthy entry is the one our own trusted proxies wrote — counted from the RIGHT.

`trusted_client_ip` takes N = number of trusted reverse-proxy hops in front of the app
(Cloudflare + nginx = 2, plain nginx = 1; `DJANGO_TRUSTED_PROXY_HOPS`). With N hops it
returns the (N)th entry from the end of XFF — the address the outermost trusted proxy
observed — or falls back to `REMOTE_ADDR` (the direct peer) when XFF is too short.

For non-auth, best-effort telemetry (PII capture) forging the IP only mislabels one
row, so those call sites keep the simpler client-claimed value — this helper is for
the allowlist checks that must not be bypassable.
"""
from __future__ import annotations

from django.conf import settings


def trusted_proxy_hops() -> int:
    try:
        return max(0, int(getattr(settings, "TRUSTED_PROXY_HOPS", 1)))
    except (TypeError, ValueError):
        return 1


def trusted_client_ip(request) -> str:
    """Resolve the caller IP for an allowlist/auth decision, spoof-resistant.

    Returns the entry XFF that our own trusted proxies contributed (counted from the
    end), never the attacker-controllable left-most entry. Falls back to REMOTE_ADDR.
    """
    remote = (request.META.get("REMOTE_ADDR", "") or "").strip()
    hops = trusted_proxy_hops()
    if hops <= 0:
        # No trusted proxy in front — the direct peer is the truth.
        return remote
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "") or ""
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if len(parts) >= hops:
        # The (hops)-th from the end is what the outermost trusted proxy saw.
        return parts[-hops]
    # XFF shorter than the trusted-hop count (e.g. a request that skipped a proxy):
    # do not trust a partial chain — fall back to the direct peer.
    return remote
