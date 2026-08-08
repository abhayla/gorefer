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

# --- Records magic link (T-051; behind ENABLE_RECORDS_LINK) ------------------------
# How long a WhatsApp [Referral Records] link stays usable. A cascade key, not a
# literal (rail E-6 / §6d): shortening the window has to take effect on links ALREADY
# in people's chat history, which a code constant could never do without a re-send.
# Not on the Preferences screen yet — the surface it governs ships flag-OFF.
RECORDS_LINK_TTL_DAYS = "records_link_ttl_days"
RECORDS_LINK_TTL_DAYS_DEFAULT = 90

# --- Token mint (T-054) -----------------------------------------------------------
# `record_date` in a mint response is pasted straight into a message body ("as per our
# records dated …"), so the strftime pattern that renders it is a cascade key, not a
# literal (rail E-6 / §6d): the owner can switch "07 Aug 2026" to "07/08/2026" without
# a deploy. A pattern strftime rejects falls back to this default (api/records_tokens).
RECORDS_MINT_DATE_FORMAT = "records_mint_date_format"
RECORDS_MINT_DATE_FORMAT_DEFAULT = "%d %b %Y"

# --- Referral share hub (T-053; behind ENABLE_SHARE_HUB) ---------------------------
# Every word this page says, and the brand image its link preview uses, is a cascade
# key rather than a template literal (rail E-6 / §6d). Two reasons, both concrete:
#   * the shipped copy below is a PLACEHOLDER pending the owner's compliance review —
#     it has to be replaceable without a deploy, and it will be replaced;
#   * the incentive claim is NOT here. It resolves from REFERRER_REWARD_CLAIM (whose
#     central default is flags.REFERRAL_INCENTIVE_CLAIM), so the "10%" wording stays
#     in the ONE editable field CLAUDE.md §4 requires and is never restated.
SHARE_HUB_HEADLINE = "share_hub_headline"
SHARE_HUB_INTRO = "share_hub_intro"
SHARE_HUB_BENEFITS_HEADING = "share_hub_benefits_heading"
SHARE_HUB_BENEFITS = "share_hub_benefits"              # JSON list of bullet strings
SHARE_HUB_GUIDANCE_HEADING = "share_hub_guidance_heading"
SHARE_HUB_GUIDANCE = "share_hub_guidance"              # JSON list of bullet strings
SHARE_HUB_OG_IMAGE_URL = "share_hub_og_image_url"

# The PIFS attribution line under the partner header (T-055, owner review 2026-08-08).
# The PARTNER NAME itself is never here — it comes from the Partner DB record via the
# identity (renaming the row must change the header with no deploy, ADR-014/§4). This
# key only carries the fixed PIFS-attribution wording, which is config per rail E-6.
SHARE_HUB_PARTNER_ATTRIBUTION = "share_hub_partner_attribution"
SHARE_HUB_PARTNER_ATTRIBUTION_DEFAULT = "via PIFS - Authorised Person"

#: Static brand card for the hub's link preview. A committed placeholder asset — an
#: operator swaps in the owner-approved image by pointing this key at a new static
#: path or an absolute CDN URL, with no deploy (§6d).
SHARE_HUB_OG_IMAGE_DEFAULT = "img/referral-preview-card.png"

SHARE_HUB_HEADLINE_DEFAULT = "Your referral link is ready"
SHARE_HUB_INTRO_DEFAULT = (
    "Send it to one person today. Everyone who opens an account through this link is "
    "recorded against your Client ID automatically."
)
SHARE_HUB_BENEFITS_HEADING_DEFAULT = "What you get"
SHARE_HUB_BENEFITS_DEFAULT = [
    "Your reward is credited by the broker's own referral programme — we make sure your "
    "name is on the referral, and never touch the amount.",
    "Every referral is tracked against your Client ID automatically. No forms, no "
    "follow-up calls, nothing to remember.",
    "Your friend is guided through account opening end to end by PIFS, free of charge.",
    "Open your record any time to see exactly where each person has reached.",
]
SHARE_HUB_GUIDANCE_HEADING_DEFAULT = "How to share so it actually works"
SHARE_HUB_GUIDANCE_DEFAULT = [
    "One direct message beats ten group posts. Send it to a person, not to a crowd.",
    "Say why YOU use it in your own words, then paste the link — people act on your "
    "reason, not on an advertisement.",
    "Start with family and friends who have already asked you about investing.",
    "If someone shows interest but goes quiet, one short reminder the next day helps "
    "far more than sending the link again.",
]

# --- WhatsApp notification routing (Tier 2, admin) ---------------------------------
# Which of the three lead-time notifications actually go out (doc-08 A6 a/b/c).
# Routing only: turning one OFF suppresses that recipient; it never changes WHAT is
# sent, and it never overrides the harder gates that already exist upstream —
# ENABLE_WATI_SEND (log-only when off), opt-out state, and "referrer phone unknown ⇒
# skip, never guess". This is the admin saying "don't route this one", not a way to
# force a send past a suppression.
NOTIFY_OFFICE = "notify_office"      # (a) Ashok / the office alert
NOTIFY_PROSPECT = "notify_prospect"  # (b) the new person (warm UTILITY, opt-in-aware)
NOTIFY_REFERRER = "notify_referrer"  # (c) the referrer thank-you (only if phone known)

# Role code -> routing key. The roles match notify.queue_lead_notifications, so a new
# recipient is a row here + a notify call, not a new branch in the screen.
NOTIFY_ROLE_KEYS = {
    "office": NOTIFY_OFFICE,
    "prospect": NOTIFY_PROSPECT,
    "referrer": NOTIFY_REFERRER,
}


# --- Per-referrer (Tier 3) — STAGED, dormant until ENABLE_CUSTOMER_LOGIN ----------
# These resolve at the USER tier of the cascade (ADR-022), which the resolver only
# consults when ENABLE_CUSTOMER_LOGIN is on — so they are inert today by construction,
# not merely hidden. The screen renders them only when that flag is on (Constitution
# §4: no dead UI). Defaults below are what every referrer gets until they choose.
REFERRER_LANDING_MODE = "referrer_landing_mode"        # "" = inherit the tenant default
REFERRER_NOTIFICATIONS_ON = "referrer_notifications_on"
REFERRER_LANGUAGE = "referrer_language"
REFERRER_PROMO_OPT_OUT = "referrer_promo_opt_out"

LANG_EN = "en"
LANG_HI = "hi"
REFERRER_LANGUAGE_CHOICES = [(LANG_EN, "English"), (LANG_HI, "Hindi")]
_VALID_LANGUAGES = {code for code, _ in REFERRER_LANGUAGE_CHOICES}

# --- Lead-time WATI template names (config-over-code) -------------------------------
# The Meta-approved template each (role, language) send uses. Config-driven so a new
# approved template version (or a new partner) is swapped through config with NO deploy
# — never hardcoded in notify.py (the earlier bug: notify.py named templates that did
# not exist in Wati). Key = "notify_template_<role>_<lang>". Office is English-only
# (internal alert); prospect/referrer carry both. Central defaults are the names
# APPROVED 2026-07-17 (see Wati-Project/docs/wati-templates.json + docs/integrations/
# WATI-TEMPLATE-INVENTORY.md). A tenant override wins per the cascade.
def _notify_template_key(role: str, lang: str) -> str:
    return f"notify_template_{role}_{lang}"


# These defaults MUST name templates that actually exist at Meta.
#
# They are the fallback when no config override is set, so a default naming a deleted or
# never-created template is a live landmine: sends fail and cascade silently. That is exactly
# the P0 found 2026-07-26 — `otp_whatsapp_template` pointed at `gorefer_login_otp`, a name
# that had never existed, so every WhatsApp login OTP got HTTP 400 and silently degraded to
# the `manual` channel while the flag still read ON.
#
# Realigned 2026-07-26 to the values production actually resolves, so that deleting the
# genuinely-superseded older templates (owner decision D6) cannot resurrect that failure mode.
NOTIFY_TEMPLATE_DEFAULTS = {
    # office has no Hindi variant → both map to the English office alert.
    _notify_template_key("office", LANG_EN): "gr_brokers_zerodha_office_lead_alert_en_2026_07_19",
    _notify_template_key("office", LANG_HI): "gr_brokers_zerodha_office_lead_alert_en_2026_07_19",
    # prospect: use the v2 UTILITY re-cut (the v1 pair reclassified to MARKETING, which
    # is capped — wrong for a must-arrive welcome). v2 dropped the promo phrasing.
    _notify_template_key("prospect", LANG_EN): "gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v2",
    _notify_template_key("prospect", LANG_HI): "gr_brokers_zerodha_prospect_welcome_hi_2026_07_17_v2",
    # referrer: the live path sends the "your referral has started" UPDATE, not the older
    # thank-you. The thank-you templates still exist at Meta and are a genuinely DIFFERENT
    # message (not a superseded version), so they are kept — just not the default.
    _notify_template_key("referrer", LANG_EN): "gr_brokers_zerodha_referrer_update_en_2026_07_19",
    _notify_template_key("referrer", LANG_HI): "gr_brokers_zerodha_referrer_update_hin_2026_07_19",
}


def notify_template_name(role: str, *, lang: str = LANG_EN, tenant_id: int | None = None) -> str:
    """Resolve the Meta template name for a (role, language) lead-time notification.

    Config-driven (cascade), defaulting to the approved names. Unknown language falls
    back to English; an unknown role raises (a new role must register a default).
    """
    lang = lang if lang in _VALID_LANGUAGES else LANG_EN
    key = _notify_template_key(role, lang)
    default = NOTIFY_TEMPLATE_DEFAULTS.get(key) or NOTIFY_TEMPLATE_DEFAULTS.get(
        _notify_template_key(role, LANG_EN)
    )
    if default is None:
        raise KeyError(f"no notify template default for role={role!r}")
    return resolve(key, tenant_id=tenant_id, default=default)


# The (role, lang, label) rows the Settings screen renders + persists, in display
# order. One row per editable template-name field. Office is en-only (its hi key maps
# to the same en name, so the screen shows a single office field).
NOTIFY_TEMPLATE_FIELDS = [
    ("office", LANG_EN, "Office / Ashok alert (English)"),
    ("prospect", LANG_EN, "Prospect welcome (English)"),
    ("prospect", LANG_HI, "Prospect welcome (Hindi)"),
    ("referrer", LANG_EN, "Referrer thank-you (English)"),
    ("referrer", LANG_HI, "Referrer thank-you (Hindi)"),
]


def notify_template_fields_view(tenant_id: int | None = None) -> list[dict]:
    """Rows for the Settings 'WhatsApp Templates' section: each editable field with its
    form key, label, currently-resolved value, and whether it is an override or default."""
    rows = []
    for role, lang, label in NOTIFY_TEMPLATE_FIELDS:
        key = _notify_template_key(role, lang)
        default = NOTIFY_TEMPLATE_DEFAULTS[key]
        current = resolve(key, tenant_id=tenant_id, default=default)
        rows.append({
            "form_key": key,          # e.g. notify_template_prospect_en
            "label": label,
            "value": current,
            "default": default,
            "is_override": current != default,
        })
    return rows

# A referrer may only pick a landing mode the TENANT allows; "" means inherit. The
# ADR-032 coupling (direct needs a live /d/{slug}) is a tenant-level fact, so a
# per-referrer `direct` can never bypass it — it is re-checked on resolve.
REFERRER_LANDING_INHERIT = ""

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
        RECORDS_LINK_TTL_DAYS: RECORDS_LINK_TTL_DAYS_DEFAULT,
        RECORDS_MINT_DATE_FORMAT: RECORDS_MINT_DATE_FORMAT_DEFAULT,
        # Share hub (T-053) — placeholder copy pending owner compliance review.
        SHARE_HUB_HEADLINE: SHARE_HUB_HEADLINE_DEFAULT,
        SHARE_HUB_INTRO: SHARE_HUB_INTRO_DEFAULT,
        SHARE_HUB_BENEFITS_HEADING: SHARE_HUB_BENEFITS_HEADING_DEFAULT,
        SHARE_HUB_BENEFITS: SHARE_HUB_BENEFITS_DEFAULT,
        SHARE_HUB_GUIDANCE_HEADING: SHARE_HUB_GUIDANCE_HEADING_DEFAULT,
        SHARE_HUB_GUIDANCE: SHARE_HUB_GUIDANCE_DEFAULT,
        SHARE_HUB_OG_IMAGE_URL: SHARE_HUB_OG_IMAGE_DEFAULT,
        SHARE_HUB_PARTNER_ATTRIBUTION: SHARE_HUB_PARTNER_ATTRIBUTION_DEFAULT,
        # Notification routing defaults to ON for all three — this mirrors today's
        # behaviour exactly (doc-08 A6 fires all three), so adding the toggles changes
        # nothing until an admin turns one off.
        NOTIFY_OFFICE: True,
        NOTIFY_PROSPECT: True,
        NOTIFY_REFERRER: True,
        # Tier-3 per-referrer defaults (dormant until ENABLE_CUSTOMER_LOGIN).
        REFERRER_LANDING_MODE: REFERRER_LANDING_INHERIT,  # inherit the tenant default
        REFERRER_NOTIFICATIONS_ON: True,
        REFERRER_LANGUAGE: LANG_EN,
        REFERRER_PROMO_OPT_OUT: False,
        # OTP defaults (Q-M-OTP) — WhatsApp/Wati primary, manual fallback until SMS
        # provider is chosen. Behaviour identical to the spec defaults until an admin
        # overrides through the screen.
        OTP_PRIMARY_CHANNEL: OTP_CHANNEL_WHATSAPP_WATI,
        OTP_FALLBACK_CHANNELS: [OTP_CHANNEL_MANUAL],
        OTP_WHATSAPP_TEMPLATE: getattr(
            settings, "OTP_WHATSAPP_TEMPLATE", "gr_platform_gorefer_login_otp_en_2026_07_21"
        ),
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


def notification_routing(tenant_id: int | None) -> dict:
    """Role code -> whether that lead-time notification is routed (Tier 2).

    Consumed by notify.queue_lead_notifications. A role that is OFF is recorded as
    skipped with a reason (never silently dropped) — the funnel must still show that
    the message did not go, and why.
    """
    prefs = get_preferences(tenant_id)
    return {role: bool(prefs[key]) for role, key in NOTIFY_ROLE_KEYS.items()}


def get_referrer_preferences(tenant_id: int | None, user_id: int | None) -> dict:
    """Resolve the Tier-3 per-referrer settings through the USER tier of the cascade.

    Inert by construction, not merely hidden: `cascade.resolve()` only consults the
    user tier when ENABLE_CUSTOMER_LOGIN is on, so with the flag off every key here
    falls through to the tenant/central default no matter what a user row says. That
    is the guarantee that staging this now cannot change Sprint-1 behaviour.
    """
    defaults = central_defaults()

    def r(key):
        return resolve(key, tenant_id=tenant_id, user_id=user_id, default=defaults[key])

    mode = str(r(REFERRER_LANDING_MODE) or "").strip().lower()
    if mode not in {"page", "direct", REFERRER_LANDING_INHERIT}:
        mode = REFERRER_LANDING_INHERIT  # unknown value => inherit, never guess
    lang = str(r(REFERRER_LANGUAGE) or "").strip().lower()
    return {
        REFERRER_LANDING_MODE: mode,
        REFERRER_NOTIFICATIONS_ON: _as_bool(r(REFERRER_NOTIFICATIONS_ON)),
        REFERRER_LANGUAGE: lang if lang in _VALID_LANGUAGES else LANG_EN,
        REFERRER_PROMO_OPT_OUT: _as_bool(r(REFERRER_PROMO_OPT_OUT)),
    }


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
        # Notification routing (Tier 2) — which of the three recipients are routed.
        NOTIFY_OFFICE: _as_bool(
            resolve(NOTIFY_OFFICE, tenant_id=tenant_id, default=defaults[NOTIFY_OFFICE])
        ),
        NOTIFY_PROSPECT: _as_bool(
            resolve(NOTIFY_PROSPECT, tenant_id=tenant_id, default=defaults[NOTIFY_PROSPECT])
        ),
        NOTIFY_REFERRER: _as_bool(
            resolve(NOTIFY_REFERRER, tenant_id=tenant_id, default=defaults[NOTIFY_REFERRER])
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
