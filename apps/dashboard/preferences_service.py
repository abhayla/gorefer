"""Preferences screen service (Q-M-PREF / ADR-034).

The UI home for the USER/tenant tier of the config cascade (ADR-022). Reads the
current per-tenant preferences and PERSISTS a submitted form to the tenant (global)
tier — critically, `LANDING_MODE` is set HERE, through the screen, never via a
backend override.

Compliance coupling enforced AT THE SCREEN (ADR-032): selecting `direct` is only
allowed when the tenant has a LIVE /d/{slug} (has_live_disclosure_page). A POST that
asks for `direct` without a live disclosure page is refused and the value forced to
`page` — the same guard the backend enforces, surfaced in the UI.

Partnerships that drive /d/{slug} composition ARE the tenant's ReferralProgram rows
(there is no separate TenantPartnership table — see COORDINATION Q-M-PREF-1). Add /
activate / deactivate operate on those rows; the disclosure page composes every
ACTIVE program in regulator order.
"""
from __future__ import annotations

from django.db import transaction
from django.utils.text import slugify

from apps.config import preferences as prefkeys
from apps.config.cascade import set_tenant
from apps.config.integration_flags import (
    INTEGRATION_FLAG_KEYS,
    INTEGRATION_FLAG_META,
    RISKY_FLAG_KEYS,
    integration_flags_view,
    resolve_flag,
)
from apps.referrals.landing_mode import (
    LANDING_MODE_DIRECT,
    LANDING_MODE_PAGE,
    has_live_disclosure_page,
)
from apps.referrals.models import Partner, ReferralProgram
from gorefer.flags import SHARE_CHANNEL_LABELS, flags

# Regulators an operator may attach a partnership for (matches ReferralProgram).
REGULATOR_CHOICES = ReferralProgram.REGULATOR_CHOICES
_VALID_REGULATORS = {code for code, _ in REGULATOR_CHOICES}
# Channel codes the screen exposes (config-driven from the flag map, never inline).
SHARE_CHANNEL_CHOICES = list(SHARE_CHANNEL_LABELS.items())


class PreferencesError(ValueError):
    """A submitted preference/partnership action was invalid (surfaced in the UI)."""


# --------------------------------------------------------------------------- read


def current_view(tenant) -> dict:
    """Everything the Preferences screen needs to render for `tenant`."""
    tenant_id = getattr(tenant, "id", None)
    prefs = prefkeys.get_preferences(tenant_id)
    live_disclosure = has_live_disclosure_page(tenant)
    return {
        "prefs": prefs,
        "slug": getattr(tenant, "slug", ""),
        "live_disclosure": live_disclosure,
        # `direct` may only be *chosen* when a live /d/{slug} exists (ADR-032).
        "direct_allowed": live_disclosure,
        "channel_choices": SHARE_CHANNEL_CHOICES,
        "regulator_choices": REGULATOR_CHOICES,
        "partnerships": list_partnerships(tenant),
        # Integration flags as checkboxes (Abhay request 2026-07-16): the P3 "flip" is
        # a UI action, not a redeploy. Each row carries its effective value AND its
        # source (admin override vs env default) — "off because untouched" and "off
        # because an admin turned it off" look identical otherwise, but a deploy moves
        # only the first.
        "integration_flags": integration_flags_view(tenant_id),
        # Tier-3 per-referrer settings are STAGED: rendered only when customer login is
        # on, because until then a referrer has no way to reach a screen to set them —
        # showing the controls would be dead UI (Constitution §4). The keys resolve at
        # the cascade's USER tier, which is itself dormant behind the same flag, so
        # this is a real gate, not just a hidden div.
        "customer_login_enabled": flags.ENABLE_CUSTOMER_LOGIN,
        "referrer_defaults": prefkeys.get_referrer_preferences(tenant_id, None),
        "referrer_language_choices": prefkeys.REFERRER_LANGUAGE_CHOICES,
        # OTP config surface (Q-M-OTP) — the admin picks channel/order/limits here.
        "otp_enabled": flags.ENABLE_OTP_LOGIN,
        "otp_channel_choices": prefkeys.OTP_CHANNEL_CHOICES,
        "otp_fallback_selected": prefs[prefkeys.OTP_FALLBACK_CHANNELS],
    }


def _save_referrer_defaults(data, *, tenant, tenant_id: int, user=None) -> list[str]:
    """Persist the Tier-3 per-referrer DEFAULTS (staged; customer-login only).

    These are the tenant-tier baseline every referrer inherits until they set their
    own at the user tier (which the cascade only consults once ENABLE_CUSTOMER_LOGIN
    is on). Stored at the GLOBAL tier for the same reason the integration flags are:
    per-tenant, so AngelOne later never inherits Zerodha's choices.
    """
    notices: list[str] = []

    # Landing mode: "" = inherit the tenant default. `direct` is re-checked against the
    # ADR-032 coupling here — a per-referrer preference must never be a way to reach
    # `direct` without a live /d/{slug}, which is the whole point of that gate.
    mode = (data.get("referrer_landing_mode") or "").strip().lower()
    if mode not in {LANDING_MODE_PAGE, LANDING_MODE_DIRECT, prefkeys.REFERRER_LANDING_INHERIT}:
        mode = prefkeys.REFERRER_LANDING_INHERIT
    if mode == LANDING_MODE_DIRECT and not has_live_disclosure_page(tenant):
        mode = prefkeys.REFERRER_LANDING_INHERIT
        notices.append(
            "Referrer default “Direct to Zerodha” needs a live disclosure page "
            "(/d/{slug}) first — kept “Inherit”."
        )
    set_tenant(prefkeys.REFERRER_LANDING_MODE, mode, tenant_id=tenant_id, user=user)

    set_tenant(
        prefkeys.REFERRER_NOTIFICATIONS_ON,
        _checkbox(data, "referrer_notifications_on"),
        tenant_id=tenant_id, user=user,
    )

    lang = (data.get("referrer_language") or "").strip().lower()
    if lang not in {code for code, _ in prefkeys.REFERRER_LANGUAGE_CHOICES}:
        lang = prefkeys.LANG_EN
    set_tenant(prefkeys.REFERRER_LANGUAGE, lang, tenant_id=tenant_id, user=user)

    set_tenant(
        prefkeys.REFERRER_PROMO_OPT_OUT,
        _checkbox(data, "referrer_promo_opt_out"),
        tenant_id=tenant_id, user=user,
    )
    return notices


def _save_integration_flags(data, *, tenant_id: int, user=None) -> list[str]:
    """Persist the three integration checkboxes. Returns notices.

    Confirm-gate: turning one of the RISKY flags (WhatsApp send / Zoho write) from OFF
    to ON requires the matching `confirm_<name>` to be present, which the UI attaches
    only after the operator accepts the dialog. Without the confirmation the flag is
    LEFT AS IT WAS and a notice explains why.

    Deliberate asymmetry — the gate applies ONLY to off->on:
      - turning something ON starts real outbound effects (real WhatsApp to real
        people, real leads into the CRM), which is the irreversible direction;
      - turning it OFF is the safe direction and must never be blocked — an operator
        hitting a live problem should be able to stop sending instantly.
      - already-on staying on is not a transition, so it isn't re-gated.
    """
    notices: list[str] = []
    for key in INTEGRATION_FLAG_KEYS:
        field = key.lower()
        requested = _checkbox(data, field)
        current = resolve_flag(key, tenant_id=tenant_id)

        turning_on = requested and not current
        if turning_on and key in RISKY_FLAG_KEYS and not _checkbox(data, f"confirm_{field}"):
            notices.append(
                f"“{INTEGRATION_FLAG_META[key]['label']}” was NOT turned on — "
                "confirmation is required before real messages/leads start going out."
            )
            continue  # leave the stored state untouched

        set_tenant(key, requested, tenant_id=tenant_id, user=user)
        if turning_on and key in RISKY_FLAG_KEYS:
            notices.append(f"“{INTEGRATION_FLAG_META[key]['label']}” is now ON — this is live.")
    return notices


def list_partnerships(tenant) -> list[dict]:
    """The tenant's programs (the rows that drive /d/{slug}), ordered as the page composes them."""
    programs = (
        ReferralProgram.objects.filter(tenant=tenant, deleted_at__isnull=True)
        .select_related("partner")
        .order_by("disclosure_sequence", "id")
    )
    reg_label = dict(REGULATOR_CHOICES)
    rows = []
    for p in programs:
        rows.append(
            {
                "id": p.id,
                "name": p.display_name or p.name,
                "regulator": p.regulator,
                "regulator_label": reg_label.get(p.regulator, p.regulator),
                "active": p.status == "active",
            }
        )
    return rows


# -------------------------------------------------------------------------- write


def set_landing_mode(tenant, requested, *, user=None) -> tuple[str, list[str]]:
    """Write LANDING_MODE at the GLOBAL/tenant tier. Returns (mode_written, notices).

    THE single write path for landing mode — used by both the Preferences screen and
    `manage.py set_landing_mode`, so the UI and the command can never drift into
    disagreeing about validation or the ADR-032 coupling. Two callers enforcing the
    same rule separately is how a CLI ends up able to set a state the screen forbids.

    Enforces:
      - ADR-032 coupling: `direct` requires a live /d/{slug} disclosure host; without
        one it is forced back to `page` with a notice. `direct` skips the landing
        page, so the disclosure must be reachable somewhere or the compliance
        surface silently disappears.
      - Unknown/blank -> `page` (never guess; `page` is the safe default).
    Idempotent: writing the current value is a no-op write of the same value.
    """
    notices: list[str] = []
    mode = (requested or LANDING_MODE_PAGE).strip().lower()
    if mode == LANDING_MODE_DIRECT and not has_live_disclosure_page(tenant):
        mode = LANDING_MODE_PAGE
        notices.append(
            "“Direct to Zerodha” needs a live disclosure page (/d/{slug}) first — "
            "add an active partnership, then you can switch to Direct. Kept “Show landing page”."
        )
    if mode not in {LANDING_MODE_PAGE, LANDING_MODE_DIRECT}:
        mode = LANDING_MODE_PAGE
    set_tenant(prefkeys.LANDING_MODE, mode, tenant_id=tenant.id, user=user)
    return mode, notices


@transaction.atomic
def save_preferences(tenant, data, *, user=None) -> list[str]:
    """Persist the submitted preference form to the tenant tier. Returns notices.

    `data` is a request.POST-like mapping. Every control maps to a cascade key at the
    GLOBAL (tenant) tier. Enforces the ADR-032 coupling: `direct` is forced back to
    `page` (with a notice) when no live /d/{slug} exists.
    """
    tenant_id = tenant.id
    notices: list[str] = []

    # --- Landing mode (LANDING_MODE) + the ADR-032 compliance coupling -----------
    _mode, mode_notices = set_landing_mode(
        tenant, data.get("landing_mode"), user=user
    )
    notices.extend(mode_notices)

    # --- Rewards -----------------------------------------------------------------
    set_tenant(
        prefkeys.SHARE_SHOW_REWARD,
        _checkbox(data, "share_show_reward"),
        tenant_id=tenant_id,
        user=user,
    )
    set_tenant(
        prefkeys.REFERRER_REWARD_CLAIM,
        (data.get("referrer_reward_claim") or "").strip(),
        tenant_id=tenant_id,
        user=user,
    )

    # --- Contact numbers ---------------------------------------------------------
    set_tenant(
        prefkeys.SUPPORT_HELPLINE_PHONE,
        (data.get("support_helpline_phone") or "").strip(),
        tenant_id=tenant_id,
        user=user,
    )
    set_tenant(
        prefkeys.WATI_BUSINESS_NUMBER,
        (data.get("wati_business_number") or "").strip(),
        tenant_id=tenant_id,
        user=user,
    )

    # --- Share channels allow-list ----------------------------------------------
    submitted = data.getlist("share_channels") if hasattr(data, "getlist") else data.get("share_channels", [])
    channels = [c for c in submitted if c in SHARE_CHANNEL_LABELS]
    # WhatsApp + Copy are always available (the primary CTAs); never empty the list.
    for always_on in prefkeys.DEFAULT_SHARE_CHANNELS:
        if always_on not in channels:
            channels.append(always_on)
    set_tenant(prefkeys.SHARE_CHANNELS_ALLOWLIST, channels, tenant_id=tenant_id, user=user)

    # --- Allow "Refer directly" (assisted) --------------------------------------
    set_tenant(
        prefkeys.ENABLE_ASSISTED_REFERRAL,
        _checkbox(data, "enable_assisted_referral"),
        tenant_id=tenant_id,
        user=user,
    )

    # --- WhatsApp notification routing (Tier 2) ----------------------------------
    # Which of the three lead-time notifications are routed. Suppression-only: an
    # opted-out prospect or an unknown referrer phone still skips regardless.
    for role, key in prefkeys.NOTIFY_ROLE_KEYS.items():
        set_tenant(key, _checkbox(data, key), tenant_id=tenant_id, user=user)

    # --- Per-referrer defaults (Tier 3) ------------------------------------------
    # Only writable while customer login is on. Writing them otherwise would persist
    # settings no referrer can reach or change — and the user tier that reads them is
    # dormant anyway, so the rows would be invisible AND inert (silently misleading).
    if flags.ENABLE_CUSTOMER_LOGIN:
        notices.extend(_save_referrer_defaults(data, tenant=tenant, tenant_id=tenant_id, user=user))

    # --- Integration flags (WATI send / Zoho write / Zoho read) ------------------
    notices.extend(_save_integration_flags(data, tenant_id=tenant_id, user=user))

    # --- OTP login channel (Q-M-OTP) — config-over-code: swap channel/order/limits
    # here, no deploy. Persisted at the tenant tier of the same cascade the OtpService
    # reads, so a change takes effect immediately.
    _save_otp(tenant_id, data, user=user)
    return notices


def _save_otp(tenant_id, data, *, user=None) -> None:
    """Persist the OTP config block (validated) to the tenant tier."""
    # Primary channel — must be a known channel code, else keep the default.
    primary = (data.get("otp_primary_channel") or "").strip().lower()
    if primary in prefkeys._VALID_OTP_CHANNELS:
        set_tenant(prefkeys.OTP_PRIMARY_CHANNEL, primary, tenant_id=tenant_id, user=user)

    # Fallback channels — ordered, de-duplicated, validated, and never the primary.
    submitted = (
        data.getlist("otp_fallback_channels")
        if hasattr(data, "getlist")
        else data.get("otp_fallback_channels", [])
    )
    fallback: list[str] = []
    for c in submitted:
        c = (c or "").strip().lower()
        if c in prefkeys._VALID_OTP_CHANNELS and c != primary and c not in fallback:
            fallback.append(c)
    set_tenant(prefkeys.OTP_FALLBACK_CHANNELS, fallback, tenant_id=tenant_id, user=user)

    # Auth template name (free text — the Meta-approved AUTHENTICATION template).
    template = (data.get("otp_whatsapp_template") or "").strip()
    if template:
        set_tenant(prefkeys.OTP_WHATSAPP_TEMPLATE, template, tenant_id=tenant_id, user=user)

    # Numeric knobs — clamped to sane bounds so a bad admin entry can't disable OTP
    # security (e.g. TTL=0 or attempts=0).
    for key, field, lo, hi in (
        (prefkeys.OTP_CODE_LENGTH, "otp_code_length", 4, 8),
        (prefkeys.OTP_CODE_TTL_SECONDS, "otp_code_ttl_seconds", 60, 1800),
        (prefkeys.OTP_MAX_VERIFY_ATTEMPTS, "otp_max_verify_attempts", 1, 10),
        (prefkeys.OTP_RESEND_COOLDOWN_SECONDS, "otp_resend_cooldown_seconds", 0, 600),
        (prefkeys.OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR, "otp_rate_limit_per_identity_per_hour", 1, 50),
    ):
        raw = data.get(field)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            val = int(str(raw).strip())
        except ValueError:
            continue
        val = max(lo, min(val, hi))
        set_tenant(key, val, tenant_id=tenant_id, user=user)


# ---------------------------------------------------------------- partnerships


@transaction.atomic
def add_partnership(tenant, *, name: str, regulator: str, user=None) -> ReferralProgram:
    """Add a partnership (Partner + ReferralProgram) that will compose on /d/{slug}.

    Config-over-code: a new partner/regulator is a data row, never a code change
    (ADR-031). The new program is created ACTIVE so its block appears immediately.
    """
    name = (name or "").strip()
    regulator = (regulator or "").strip().lower()
    if not name:
        raise PreferencesError("Partnership name is required.")
    if regulator not in _VALID_REGULATORS:
        raise PreferencesError("Unknown regulator.")

    code = _unique_partner_code(name)
    partner = Partner.objects.create(
        tenant=tenant,
        name=name,
        code=code,
        status="active",
        created_by=getattr(user, "pk", None),
    )
    # Sequence after existing programs so regulator order stays deterministic.
    next_seq = 10 * (
        ReferralProgram.objects.filter(tenant=tenant, deleted_at__isnull=True).count() + 2
    )
    program = ReferralProgram.objects.create(
        tenant=tenant,
        partner=partner,
        name=name,
        display_name=name,
        status="active",
        regulator=regulator,
        disclosure_sequence=next_seq,
        created_by=getattr(user, "pk", None),
    )
    return program


@transaction.atomic
def set_partnership_active(tenant, *, program_id: int, active: bool, user=None) -> None:
    """Activate/deactivate a partnership. Deactivating drops its block from /d/{slug}.

    Refuses to deactivate the LAST active partnership while LANDING_MODE=direct — that
    would strand a `direct` bypass with no disclosure host (ADR-032 coupling).
    """
    program = ReferralProgram.objects.filter(
        tenant=tenant, id=program_id, deleted_at__isnull=True
    ).first()
    if program is None:
        raise PreferencesError("Partnership not found.")

    if not active:
        remaining = (
            ReferralProgram.objects.filter(tenant=tenant, status="active", deleted_at__isnull=True)
            .exclude(id=program_id)
            .exists()
        )
        current_mode = prefkeys.get_preferences(tenant.id)[prefkeys.LANDING_MODE]
        if not remaining and current_mode == LANDING_MODE_DIRECT:
            raise PreferencesError(
                "Can’t deactivate the last active partnership while landing mode is "
                "“Direct to Zerodha” — the disclosure page would have nothing to show. "
                "Switch to “Show landing page” first."
            )

    program.status = "active" if active else "inactive"
    program.updated_by = getattr(user, "pk", None)
    program.save(update_fields=["status", "updated_by", "updated_at"])


def _checkbox(data, name: str) -> bool:
    return (data.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _unique_partner_code(name: str) -> str:
    """A stable, unique partner code derived from the name (Partner.code is unique)."""
    base = (slugify(name).upper().replace("-", "") or "PARTNER")[:40]
    code = base
    n = 1
    while Partner.objects.filter(code=code).exists():
        n += 1
        code = f"{base[:38]}{n}"
    return code
