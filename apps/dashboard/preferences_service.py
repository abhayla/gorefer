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
from apps.referrals.landing_mode import (
    LANDING_MODE_DIRECT,
    LANDING_MODE_PAGE,
    has_live_disclosure_page,
)
from apps.referrals.models import Partner, ReferralProgram
from gorefer.flags import SHARE_CHANNEL_LABELS

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
    }


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
    requested_mode = (data.get("landing_mode") or LANDING_MODE_PAGE).strip().lower()
    if requested_mode == LANDING_MODE_DIRECT and not has_live_disclosure_page(tenant):
        requested_mode = LANDING_MODE_PAGE
        notices.append(
            "“Direct to Zerodha” needs a live disclosure page (/d/{slug}) first — "
            "add an active partnership, then you can switch to Direct. Kept “Show landing page”."
        )
    if requested_mode not in {LANDING_MODE_PAGE, LANDING_MODE_DIRECT}:
        requested_mode = LANDING_MODE_PAGE
    set_tenant(prefkeys.LANDING_MODE, requested_mode, tenant_id=tenant_id, user=user)

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
    return notices


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
