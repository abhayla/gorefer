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


def _mask_clicks(rows: list[dict]) -> list[dict]:
    """ADR-026/S2-01: customer view masks IP (city stays). Mutates copies, not admin data."""
    masked = []
    for row in rows:
        row = dict(row)
        row["ip"] = "—"
        masked.append(row)
    return masked


def my_referrals_ctx(tenant, client_id: str) -> dict:
    """The full profile ctx, referrer-scoped + masked. Works with ZERO activity too
    (a just-bound referrer with no clicks sees zeros + their link, not an error)."""
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
        "cards": profile.per_link_cards(tenant, client_id),
        "clicks": clicks,
        "people": profile.referred_people(tenant, client_id),
        "config": profile.PROFILE_CONFIG,
        "role": "referrer",
        "base_template": "accounts/my_base.html",
        "my_link": my_link,
        # WhatsApp share prefill: routed via gorefer.in with the wa channel prefix
        # (ADR-030 — never direct-to-Zerodha; ADR-028 B1 attribution), plus the §4.4
        # disclosure host (ADR-031/032 — the light message's compliance anchor).
        "share_text": (
            f"Open your free Zerodha account with my referral link: "
            f"https://{profile.PROFILE_CONFIG['link_base']}wa/{client_id} "
            f"· Disclosures: {disclosure}"
        ),
    }
