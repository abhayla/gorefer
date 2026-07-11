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

# --- OTP login keys (Q-M-OTP) — per-tenant, cascade-resolved, edited on the screen.
# The "very easily configurable for admin" requirement: swap the OTP channel/order/
# template/limits through Preferences with NO deploy (config-over-code). The master
# ENABLE_OTP_LOGIN flag stays a flags.py env flag (gates the whole feature); these
# keys tune behaviour once it's on.
OTP_PRIMARY_CHANNEL = "otp_primary_channel"
OTP_FALLBACK_CHANNELS = "otp_fallback_channels"
OTP_WHATSAPP_TEMPLATE = "otp_whatsapp_template"
OTP_CODE_LENGTH = "otp_code_length"
OTP_CODE_TTL_SECONDS = "otp_code_ttl_seconds"
OTP_MAX_VERIFY_ATTEMPTS = "otp_max_verify_attempts"
OTP_RESEND_COOLDOWN_SECONDS = "otp_resend_cooldown_seconds"
OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR = "otp_rate_limit_per_identity_per_hour"

# OTP channel codes an admin may pick (must match apps.otp.channels registry keys).
OTP_CHANNEL_WHATSAPP_WATI = "whatsapp_wati"
OTP_CHANNEL_SMS = "sms"
OTP_CHANNEL_MANUAL = "manual"
OTP_CHANNEL_CHOICES = [
    (OTP_CHANNEL_WHATSAPP_WATI, "WhatsApp (Wati)"),
    (OTP_CHANNEL_SMS, "SMS"),
    (OTP_CHANNEL_MANUAL, "Manual / assisted"),
]
_VALID_OTP_CHANNELS = {code for code, _ in OTP_CHANNEL_CHOICES}

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
        # OTP defaults (Q-M-OTP) — WhatsApp/Wati primary, manual fallback until SMS
        # provider is chosen. Behaviour identical to the spec defaults until an admin
        # overrides through the screen.
        OTP_PRIMARY_CHANNEL: OTP_CHANNEL_WHATSAPP_WATI,
        OTP_FALLBACK_CHANNELS: [OTP_CHANNEL_MANUAL],
        OTP_WHATSAPP_TEMPLATE: getattr(settings, "OTP_WHATSAPP_TEMPLATE", "gorefer_login_otp"),
        OTP_CODE_LENGTH: 6,
        OTP_CODE_TTL_SECONDS: 300,
        OTP_MAX_VERIFY_ATTEMPTS: 5,
        OTP_RESEND_COOLDOWN_SECONDS: 60,
        OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR: 5,
    }


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _valid_channel(value, fallback: str) -> str:
    """A stored primary channel, guarded to a known adapter code."""
    code = str(value).strip() if value is not None else ""
    return code if code in _VALID_OTP_CHANNELS else fallback


def _as_channel_list(value) -> list[str]:
    """Coerce a stored fallback-channels value to a clean, validated ordered list.

    Accepts a JSON list (how it is stored) or a comma-separated string (defensive).
    Drops unknown channel codes so a bad/legacy value can never route OTP to a
    non-existent adapter.
    """
    if isinstance(value, str):
        items = [c.strip() for c in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = [str(c).strip() for c in value]
    else:
        items = []
    return [c for c in items if c in _VALID_OTP_CHANNELS]


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
        # OTP (Q-M-OTP) — the same cascade the screen writes, so a saved override
        # takes effect immediately with no deploy.
        OTP_PRIMARY_CHANNEL: _valid_channel(
            resolve(OTP_PRIMARY_CHANNEL, tenant_id=tenant_id, default=defaults[OTP_PRIMARY_CHANNEL]),
            defaults[OTP_PRIMARY_CHANNEL],
        ),
        OTP_FALLBACK_CHANNELS: _as_channel_list(
            resolve(OTP_FALLBACK_CHANNELS, tenant_id=tenant_id, default=defaults[OTP_FALLBACK_CHANNELS])
        ),
        OTP_WHATSAPP_TEMPLATE: resolve(
            OTP_WHATSAPP_TEMPLATE, tenant_id=tenant_id, default=defaults[OTP_WHATSAPP_TEMPLATE]
        ),
        OTP_CODE_LENGTH: _as_int(
            resolve(OTP_CODE_LENGTH, tenant_id=tenant_id, default=defaults[OTP_CODE_LENGTH]),
            defaults[OTP_CODE_LENGTH],
        ),
        OTP_CODE_TTL_SECONDS: _as_int(
            resolve(OTP_CODE_TTL_SECONDS, tenant_id=tenant_id, default=defaults[OTP_CODE_TTL_SECONDS]),
            defaults[OTP_CODE_TTL_SECONDS],
        ),
        OTP_MAX_VERIFY_ATTEMPTS: _as_int(
            resolve(OTP_MAX_VERIFY_ATTEMPTS, tenant_id=tenant_id, default=defaults[OTP_MAX_VERIFY_ATTEMPTS]),
            defaults[OTP_MAX_VERIFY_ATTEMPTS],
        ),
        OTP_RESEND_COOLDOWN_SECONDS: _as_int(
            resolve(
                OTP_RESEND_COOLDOWN_SECONDS,
                tenant_id=tenant_id,
                default=defaults[OTP_RESEND_COOLDOWN_SECONDS],
            ),
            defaults[OTP_RESEND_COOLDOWN_SECONDS],
        ),
        OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR: _as_int(
            resolve(
                OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR,
                tenant_id=tenant_id,
                default=defaults[OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR],
            ),
            defaults[OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR],
        ),
    }
