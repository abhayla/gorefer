"""My Referrals — the referrer-role rendering of the ONE profile template (ADR-026).

Same template, same ctx builders as the admin Referral Profile (M9); difference is
config, not code: role="referrer" locks the record to the session's own client_id,
hides admin chrome (base template + breadcrumbs + admin note), and applies
`PII_MASK_FOR_CUSTOMER_VIEW` at the DATA level before the template ever sees it
(IP → city-only). Admin view stays full and untouched.
"""
from __future__ import annotations

from django.conf import settings

from apps.dashboard import profile
from gorefer.flags import flags


def _program_brand(tenant, client_id: str) -> str:
    """T-059: the T-056 fallback chain for this referrer's own program, falling back
    to the tenant's single active program when no ReferralIdentity exists yet (a
    just-bound referrer with zero clicks still sees a correctly-branded share line)."""
    from apps.referrals.branding import brand_for_program, brand_for_tenant_id

    identity = identity_for(tenant, client_id)
    if identity is not None and identity.program is not None:
        return brand_for_program(identity.program)
    return brand_for_tenant_id(getattr(tenant, "id", None))


def _mask_clicks(rows: list[dict]) -> list[dict]:
    """ADR-026/S2-01: customer view masks IP (city stays). Mutates copies, not admin data."""
    masked = []
    for row in rows:
        row = dict(row)
        row["ip"] = "—"
        masked.append(row)
    return masked


def _strip_partner_code(cards: list[dict]) -> list[dict]:
    """GUARDRAIL 3: the partner code is server-side only — never a client-facing body.

    `/my/referrals` and the admin Referral Profile share ONE template (ADR-026), and
    that template renders `{{ card.partner_code }}` as a badge. Harmless on the
    staff screen; on the referrer's own page it published PIFS's Zerodha partner code
    `ZMPHZC` to every logged-in referrer (found live 2026-07-26 during D8).

    Stripped HERE, at the data level, for the same reason `_mask_clicks` is — the
    template must never receive what the referrer may not see, so a future template
    edit cannot re-expose it. The card still shows `partner_name` ("Zerodha"), which
    is what the referrer actually needs; the code carried no meaning for them.
    """
    return [{**card, "partner_code": ""} for card in cards]


def identity_for(tenant, client_id: str):
    """The session referrer's own `ReferralIdentity`, or None (T-075).

    THE session→identity path. `/my/referrals`, its hub-CTA builder and the
    login-gated `/hub` all resolve through this one function, so "which record does
    this session own" has exactly one answer in the codebase.

    `client_id` always comes from the bound `ReferrerAccount`, never from a URL or a
    form — that is what makes cross-identity access impossible by construction rather
    than by a check. None means the referrer is bound but has no identity row yet
    (never clicked, no Zoho-imported conversion): identities are created at CLICK time
    (ADR-008) and rendering a page must not create one.
    """
    from apps.referrals.models import ReferralIdentity

    return (
        ReferralIdentity.objects.for_tenant(tenant)
        .filter(client_id=client_id, status="active", deleted_at__isnull=True)
        .select_related("program", "program__partner", "partner", "tenant")
        .order_by("id")
        .first()
    )


def hub_url_for(tenant, client_id: str) -> str:
    """The logged-in referrer's own `/hub/{token}` link, or "" (T-054).

    Until now the share hub had no door for someone who was already logged in — it was
    reachable only by tapping a WhatsApp button. This mints that door AT RENDER, which
    is safe and cheap because the token is a stateless signature: nothing is persisted,
    and a fresh string every page load is as valid as the last one.

    The token is minted for the identity the SESSION'S account owns, resolved from the
    account's bound `client_id` (the caller passes `account.client_id`, never a URL
    parameter — `views.my_referrals` has no parameter to tamper with). A referrer whose
    client_id has no `ReferralIdentity` row yet — bound by login but never clicked, and
    with no Zoho-imported conversion — gets "" and no link renders: identities are
    created at CLICK time (ADR-008), and rendering a page must not create one.

    Returns "" when ENABLE_SHARE_HUB is off, so the flag-off tree has no dead link.
    """
    if not flags.ENABLE_SHARE_HUB:
        return ""
    from .records_link import mint_records_token

    identity = identity_for(tenant, client_id)
    if identity is None:
        return ""
    return f"/hub/{mint_records_token(identity)}"


def my_referrals_ctx(tenant, client_id: str) -> dict:
    """The full profile ctx, referrer-scoped + masked. Works with ZERO activity too
    (a just-bound referrer with no clicks sees zeros + their link, not an error)."""
    from apps.config.cascade import resolve as resolve_config
    from apps.config.preferences import MY_REFERRALS_HUB_CTA, MY_REFERRALS_HUB_CTA_DEFAULT

    band = profile.top_band(tenant, client_id)
    clicks = profile.clicks_rows(tenant, client_id)
    if getattr(settings, "PII_MASK_FOR_CUSTOMER_VIEW", True):
        clicks = _mask_clicks(clicks)
    my_link = f"https://{profile.PROFILE_CONFIG['link_base']}{client_id}"
    disclosure = f"https://{profile.PROFILE_CONFIG['disclosure_url']}"
    return {
        "client_id": client_id,
        "band": band,
        "ring_fractions": profile.ring_fractions(band["aggregates"]),
        "cards": _strip_partner_code(profile.per_link_cards(tenant, client_id)),
        "clicks": clicks,
        "people": profile.referred_people(tenant, client_id),
        "config": profile.PROFILE_CONFIG,
        "role": "referrer",
        "base_template": "accounts/my_base.html",
        "my_link": my_link,
        # T-054: the logged-in door to the share hub. Blank when the flag is off or the
        # referrer has no identity row — the template renders nothing in either case.
        "hub_url": hub_url_for(tenant, client_id),
        # T-060 (rail E-6 / §6e): the CTA label was a literal — now cascade-resolved
        # so the owner can re-word it with no deploy. Default unchanged.
        "hub_cta": resolve_config(
            MY_REFERRALS_HUB_CTA,
            tenant_id=getattr(tenant, "id", None),
            default=MY_REFERRALS_HUB_CTA_DEFAULT,
        ),
        # WhatsApp share prefill: routed via gorefer.in with the wa channel prefix
        # (ADR-030 — never direct-to-Zerodha; ADR-028 B1 attribution), plus the §4.4
        # disclosure host (ADR-031/032 — the light message's compliance anchor).
        "share_text": (
            f"Open your free {_program_brand(tenant, client_id)} account with my referral link: "
            f"https://{profile.PROFILE_CONFIG['link_base']}wa/{client_id} "
            f"· Disclosures: {disclosure}"
        ),
    }
