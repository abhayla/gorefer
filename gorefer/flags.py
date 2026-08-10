"""Feature flags + compliance config — the ONE place flags are read from env.

Per implementation/10 §4 and COORDINATION M1 step 2: flags are loaded from the
environment ONCE at import time into a single frozen object. No feature flag is
ever checked by a raw string literal scattered across the codebase — code imports
`flags` from here and reads an attribute.

This module is intentionally import-safe with **no Django dependency** so it can be
read from settings, management commands, and tests alike.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    return default if raw is None else raw


# ── Share-channel attribution (M11 / ADR-028, S2-01 §5.3/§7) ───────────────────
# The `?s=` param on a shared /r/{id} link records HOW the visitor arrived, then is
# STRIPPED before the 302 so it never leaks into the Zerodha destination. The param
# NAME is config (SHARE_CHANNEL_PARAM, default "s"). Allowed short codes map to the
# human-readable Channel label shown in the Referral-Profile Clicks tab (reusing the
# existing metadata["channel"] column). An unknown/unlisted code normalizes to
# "other"; an absent param means no channel key (renders as "Direct").
SHARE_CHANNEL_PARAM = _str("SHARE_CHANNEL_PARAM", "s")
SHARE_CHANNEL_LABELS = {
    "wa": "WhatsApp",
    "fb": "Facebook",
    "x": "X",
    "li": "LinkedIn",
    "tg": "Telegram",
    "ig": "Instagram",
    "email": "Email",
    "copy": "Copy",
}
SHARE_CHANNEL_OTHER = "other"

# One-tap share endpoint (M-WATI-1). Launch supports WhatsApp only — an unsupported
# or unlisted channel 404s rather than silently falling back to "other" (unlike the
# /r/ attribution tag above, this gates which channels the endpoint will SERVE).
SHARE_INTENT_CHANNELS = frozenset({"wa"})


def normalize_share_channel(raw: str | None) -> str | None:
    """Map a raw ?s= value to its canonical Channel label (config-driven).

    Returns None for an absent/blank param, the mapped label for a known code, or
    "other" for an unknown non-blank code. Case-insensitive on the code.
    """
    if not raw:
        return None
    code = raw.strip().lower()
    if not code:
        return None
    return SHARE_CHANNEL_LABELS.get(code, SHARE_CHANNEL_OTHER)


@dataclass(frozen=True)
class FeatureFlags:
    """Immutable snapshot of feature flags, resolved from env at startup.

    Defaults match implementation/10 §4 and the M1 mission brief. The not-yet-built
    capabilities default OFF so nothing half-built is reachable in production, and
    external-system adapters stay dormant (log-only) until explicitly enabled.
    """

    # Later-sprint capabilities — OFF by default (never rendered as dead UI).
    ENABLE_CUSTOMER_LOGIN: bool = False
    # Referrer self-service OTP login (Q-M-OTP). Master flag for the pluggable OTP
    # port. OFF until the Sprint-2 customer-login gate — when OFF, OtpService issues
    # through the DemoOtpAdapter (log-only, sends nothing). Independent of
    # ENABLE_WATI_SEND: even with OTP on, real WhatsApp sending still needs WATI on.
    ENABLE_OTP_LOGIN: bool = False
    # T-078 — the SECOND OTP delivery leg: the same login code also goes to the
    # referrer's ON-FILE email (Zoho Contact / Customer), never a typed address.
    # ADDITION, not fallback: WhatsApp still sends exactly as before and the two
    # legs are independent. OFF by default — prod activation waits on the Zoho Mail
    # app-specific password (TODO-Manual gorefer-email-otp-zoho-smtp-cred). With it
    # OFF, behaviour is byte-identical to WhatsApp-only.
    ENABLE_EMAIL_OTP: bool = False

    # External-system adapters — OFF until credentials/templates verified.
    # When OFF, adapters log the intended call instead of sending (demo-safe).
    ENABLE_WATI_SEND: bool = False
    ENABLE_ZOHO_WRITE: bool = False
    # Zoho READ enrichment (M9): read-only Contact/Lead enrichment for the Referral
    # Profile. INDEPENDENT of ZOHO_WRITE — the two flags move separately (DF-9 is
    # superseded: WRITE now goes ON for PIFS via Model 2 upsert-by-mobile, Abhay+DA
    # 2026-07-15). OFF in CI/demo (adapter returns seeded fixtures); ON only where
    # ZOHO_* read creds are present.
    ENABLE_ZOHO_READ: bool = False
    # DF-2 wax-seal on the Zoho status webhook. OFF = interim static key + IP
    # allowlist. ON = HMAC(payload+timestamp+nonce) REQUIRED (the static key is not a
    # fallback) + the same IP allowlist. Kept behind a flag so the seal can ship and
    # be tested before the Zoho-side Deluge signer is deployed — flipping it on
    # without the signer live would reject every real webhook.
    ENABLE_ZOHO_WEBHOOK_HMAC: bool = False

    # Sprint-1 surfaces that ARE built.
    ENABLE_ADMIN_DASHBOARD: bool = True
    ENABLE_DEMO_MODE: bool = True

    # Compliance: the single swappable "10% brokerage" claim string (ADR-014).
    # This is the ONLY place the incentive claim wording lives (default; env overrides).
    REFERRAL_INCENTIVE_CLAIM: str = "10% brokerage share + 300 reward points"

    # M-WATI-1 — one-tap share endpoint (GET /share/{channel}/{client_id}). OFF by
    # default so nothing is reachable in production until the owner flips it on.
    ENABLE_SHARE_INTENT: bool = False
    # The single swappable kit-message template (mirrors REFERRAL_INCENTIVE_CLAIM
    # above) — owner-approved EN copy. `{link}` is substituted with the tracked
    # `/r/{channel}/{client_id}` URL server-side; never partner code / raw Zerodha URL.
    # {program_brand} resolves at build time (apps.referrals.branding, T-059) via the
    # T-056 fallback chain — never a hard-coded partner name, so a second program
    # (Groww, ...) renders correctly with no code change.
    SHARE_KIT_MESSAGE_TEMPLATE: str = "Open a free {program_brand} account — my referral link:\n{link}"

    # T-051 — tokened, read-only "Referral Records" page (GET /rr/{token}), reached
    # from a WhatsApp [Referral Records] URL button. OFF until the pilot template is
    # approved; when off the ENTIRE route is absent (Constitution §4 — no dead route).
    ENABLE_RECORDS_LINK: bool = False

    # T-053 — the referral SHARE HUB (GET /hub/{token}), the destination of a
    # [Refer Link] button on a MARKETING WhatsApp template. Separate flag from
    # ENABLE_RECORDS_LINK on purpose: the two tokened pages ship independently, and
    # this one stays OFF until the owner has signed off on the page copy for
    # compliance. When off the ENTIRE route is absent (Constitution §4).
    ENABLE_SHARE_HUB: bool = False

    @classmethod
    def from_env(cls) -> "FeatureFlags":
        return cls(
            ENABLE_CUSTOMER_LOGIN=_bool("ENABLE_CUSTOMER_LOGIN", cls.ENABLE_CUSTOMER_LOGIN),
            ENABLE_OTP_LOGIN=_bool("ENABLE_OTP_LOGIN", cls.ENABLE_OTP_LOGIN),
            ENABLE_EMAIL_OTP=_bool("ENABLE_EMAIL_OTP", cls.ENABLE_EMAIL_OTP),
            ENABLE_WATI_SEND=_bool("ENABLE_WATI_SEND", cls.ENABLE_WATI_SEND),
            ENABLE_ZOHO_WRITE=_bool("ENABLE_ZOHO_WRITE", cls.ENABLE_ZOHO_WRITE),
            ENABLE_ZOHO_READ=_bool("ENABLE_ZOHO_READ", cls.ENABLE_ZOHO_READ),
            ENABLE_ZOHO_WEBHOOK_HMAC=_bool(
                "ENABLE_ZOHO_WEBHOOK_HMAC", cls.ENABLE_ZOHO_WEBHOOK_HMAC
            ),
            ENABLE_ADMIN_DASHBOARD=_bool("ENABLE_ADMIN_DASHBOARD", cls.ENABLE_ADMIN_DASHBOARD),
            ENABLE_DEMO_MODE=_bool("ENABLE_DEMO_MODE", cls.ENABLE_DEMO_MODE),
            REFERRAL_INCENTIVE_CLAIM=_str("REFERRAL_INCENTIVE_CLAIM", cls.REFERRAL_INCENTIVE_CLAIM),
            ENABLE_SHARE_INTENT=_bool("ENABLE_SHARE_INTENT", cls.ENABLE_SHARE_INTENT),
            SHARE_KIT_MESSAGE_TEMPLATE=_str(
                "SHARE_KIT_MESSAGE_TEMPLATE", cls.SHARE_KIT_MESSAGE_TEMPLATE
            ),
            ENABLE_RECORDS_LINK=_bool("ENABLE_RECORDS_LINK", cls.ENABLE_RECORDS_LINK),
            ENABLE_SHARE_HUB=_bool("ENABLE_SHARE_HUB", cls.ENABLE_SHARE_HUB),
        )

    def as_dict(self) -> dict:
        return self.__dict__.copy()


# The single, process-wide flags snapshot. Import this, don't re-read os.environ.
flags = FeatureFlags.from_env()
