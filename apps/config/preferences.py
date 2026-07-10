"""Preference config keys — the tenant-tier settings the Preferences screen owns.

One home for the key NAMES + their central defaults (config-over-code: no scattered
string literals in views/templates). Each key is a plain (unlocked) cascade key, so a
tenant override at the GLOBAL tier wins over the central default (ADR-022, ADR-034).
Compliance-locked keys (the incentive claim, AP disclosure block, NSE AP no.) are NOT
here — they resolve from central only and the screen never writes them.

`LANDING_MODE` is set THROUGH the Preferences screen, never a backend override
(ADR-034). The ADR-032 disclosure coupling (`direct` only when a live /d/{slug}
exists) is enforced at the screen (see apps/referrals/landing_mode.has_live_disclosure_page).
"""
from __future__ import annotations

from django.conf import settings

from .cascade import resolve

# --- Key names (single source; referenced everywhere by constant, never literal) ---
LANDING_MODE = "landing_mode"
SHARE_SHOW_REWARD = "share_show_reward"
REFERRER_REWARD_CLAIM = "referrer_reward_claim"
SUPPORT_HELPLINE_PHONE = "support_helpline_phone"
WATI_BUSINESS_NUMBER = "wati_business_number"
SHARE_CHANNELS_ALLOWLIST = "share_channels_allowlist"
ENABLE_ASSISTED_REFERRAL = "enable_assisted_referral"

# The channel codes a tenant may enable (must match gorefer.flags.SHARE_CHANNEL_LABELS).
# WhatsApp + Copy are the always-on defaults; the rest are opt-in per tenant.
DEFAULT_SHARE_CHANNELS = ["wa", "copy"]


def central_defaults() -> dict:
    """Central baseline for the preference keys (seeded into config_central).

    Values are the current settings/flags so behaviour is identical to today until a
    tenant overrides one through the screen.
    """
    from gorefer.flags import flags

    return {
        LANDING_MODE: "page",
        SHARE_SHOW_REWARD: True,
        REFERRER_REWARD_CLAIM: flags.REFERRAL_INCENTIVE_CLAIM,
        SUPPORT_HELPLINE_PHONE: getattr(settings, "SUPPORT_HELPLINE_PHONE", ""),
        WATI_BUSINESS_NUMBER: settings.WATI_BUSINESS_NUMBER,
        SHARE_CHANNELS_ALLOWLIST: DEFAULT_SHARE_CHANNELS,
        ENABLE_ASSISTED_REFERRAL: False,
    }


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def get_preferences(tenant_id: int | None) -> dict:
    """Resolve every preference key for a tenant through the cascade (typed).

    This is what the Preferences screen renders and what consumers (landing page,
    WhatsApp messages) read, so a saved override takes effect immediately.
    """
    defaults = central_defaults()
    channels = resolve(
        SHARE_CHANNELS_ALLOWLIST, tenant_id=tenant_id, default=defaults[SHARE_CHANNELS_ALLOWLIST]
    )
    if isinstance(channels, str):
        channels = [c.strip() for c in channels.split(",") if c.strip()]
    return {
        LANDING_MODE: resolve(LANDING_MODE, tenant_id=tenant_id, default=defaults[LANDING_MODE]),
        SHARE_SHOW_REWARD: _as_bool(
            resolve(SHARE_SHOW_REWARD, tenant_id=tenant_id, default=defaults[SHARE_SHOW_REWARD])
        ),
        REFERRER_REWARD_CLAIM: resolve(
            REFERRER_REWARD_CLAIM, tenant_id=tenant_id, default=defaults[REFERRER_REWARD_CLAIM]
        ),
        SUPPORT_HELPLINE_PHONE: resolve(
            SUPPORT_HELPLINE_PHONE, tenant_id=tenant_id, default=defaults[SUPPORT_HELPLINE_PHONE]
        ),
        WATI_BUSINESS_NUMBER: resolve(
            WATI_BUSINESS_NUMBER, tenant_id=tenant_id, default=defaults[WATI_BUSINESS_NUMBER]
        ),
        SHARE_CHANNELS_ALLOWLIST: list(channels),
        ENABLE_ASSISTED_REFERRAL: _as_bool(
            resolve(ENABLE_ASSISTED_REFERRAL, tenant_id=tenant_id, default=defaults[ENABLE_ASSISTED_REFERRAL])
        ),
    }
