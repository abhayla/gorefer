"""LANDING_MODE + derived MESSAGE_DISCLOSURE_LEVEL (B3 / ADR-032).

Per-tenant (sub-broker) config `LANDING_MODE`:
  - `page`   (default): /r/{client_id} renders the PIFS landing (form + disclosures).
  - `direct`          : /r/{client_id} logs the click on-commit then 302s straight to
                        Zerodha, skipping the landing page. Channel/`?s` stripped, code
                        server-side — guardrails unchanged.

The §3(b) coupling (no bypass-without-disclosure gap): a `direct` link relies on a
linked disclosure host for the full §4.4 block. `MESSAGE_DISCLOSURE_LEVEL` is
therefore **DERIVED, not free-set**:
  - `full`  when LANDING_MODE=direct AND there is no live /d/{slug} host, and
  - `light` otherwise.
`resolve_message_disclosure_level()` is the single place that computes it; the
config resolver REFUSES a hand-set `direct` + `light` + no-`/d/` combination
(raise DisclosureCouplingError) so the gap can never be configured open.
"""
from __future__ import annotations

from apps.config.cascade import resolve

LANDING_MODE_PAGE = "page"
LANDING_MODE_DIRECT = "direct"
_VALID_MODES = {LANDING_MODE_PAGE, LANDING_MODE_DIRECT}

DISCLOSURE_LIGHT = "light"
DISCLOSURE_FULL = "full"


class DisclosureCouplingError(ValueError):
    """Raised when config would open the bypass-without-disclosure gap (§3b)."""


def resolve_landing_mode(tenant_id: int | None) -> str:
    """The tenant's LANDING_MODE (page|direct), default page. Unknown -> page."""
    mode = resolve("landing_mode", tenant_id=tenant_id, default=LANDING_MODE_PAGE)
    mode = (mode or LANDING_MODE_PAGE).strip().lower()
    return mode if mode in _VALID_MODES else LANDING_MODE_PAGE


def has_live_disclosure_host(tenant) -> bool:
    """True if the tenant exposes a live /d/{slug} disclosure host (DISCLOSURE_PAGE_ENABLED).

    The disclosure page (B2) exists and is enabled for the tenant, so a light message
    / direct link can point at it for the full §4.4 block. Config-driven; defaults ON
    (the page ships enabled) unless a tenant explicitly turns it off.
    """
    if tenant is None:
        return False
    tenant_id = getattr(tenant, "id", None)
    enabled = resolve("disclosure_page_enabled", tenant_id=tenant_id, default=True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in {"1", "true", "yes", "on"}
    return bool(enabled)


def resolve_message_disclosure_level(tenant) -> str:
    """DERIVED §4.4 message-disclosure level for the tenant.

    `full` iff LANDING_MODE=direct AND no live /d/{slug} host; else `light`. Never
    read a hand-set value — it is always computed here so the coupling holds.
    """
    tenant_id = getattr(tenant, "id", None)
    mode = resolve_landing_mode(tenant_id)
    if mode == LANDING_MODE_DIRECT and not has_live_disclosure_host(tenant):
        return DISCLOSURE_FULL
    return DISCLOSURE_LIGHT


def assert_disclosure_coupling(tenant) -> None:
    """Guard: refuse a config that opens the bypass-without-disclosure gap.

    Illegal state = LANDING_MODE=direct AND no live /d/{slug} AND a hand-set
    message_disclosure_level of `light`. In that case the derived level MUST be
    `full`; a stored `light` override is a compliance gap and is rejected.
    """
    tenant_id = getattr(tenant, "id", None)
    mode = resolve_landing_mode(tenant_id)
    if mode != LANDING_MODE_DIRECT or has_live_disclosure_host(tenant):
        return  # not a bypass situation — nothing to enforce
    # direct + no live /d/ : the only compliant message level is `full`.
    stored = resolve("message_disclosure_level", tenant_id=tenant_id, default=None)
    if stored is not None and str(stored).strip().lower() == DISCLOSURE_LIGHT:
        raise DisclosureCouplingError(
            "LANDING_MODE=direct with no live /d/{slug} host requires "
            "MESSAGE_DISCLOSURE_LEVEL=full; a `light` override opens the "
            "bypass-without-disclosure gap (S2-03 §3b / ADR-032)."
        )
