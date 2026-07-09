"""Per-sub-broker disclosure composition (B2 / ADR-031).

The canonical §4.4 host: `/d/{slug}` composes the mandated disclosure block for
EVERY active partner/program a sub-broker (tenant) is associated with, in a fixed
REGULATOR order (SEBI/NSE → IRDAI → RBI → other), each filled with that tenant's
own values. A light WhatsApp message / `direct` bypass link is compliant because it
can point here for the full disclosures.

Config-over-code:
  - The block text is the program's `disclosure_template` (with {placeholders}); if
    blank, we fall back to the canonical central AP disclosure block + market-risk
    warning (interim single-partner behaviour, exactly what the landing page shows).
  - Ordering is driven by (disclosure_sequence, regulator rank) — a new partner is a
    data row, never a code change.

Guardrails: NO PII on the page; NO partner code / raw Zerodha URL in any block
(the compliance strings are identification + risk text only). The view creates no
event, so a crawler hit is inherently excluded from human counts.
"""
from __future__ import annotations

from django.conf import settings

from apps.tenants.models import Tenant

from .models import ReferralProgram

# Regulator display order (S2-03 §4): securities → insurance → loans → other.
_REGULATOR_RANK = {"sebi_nse": 0, "irdai": 1, "rbi": 2, "other": 9}
_REGULATOR_LABEL = dict(ReferralProgram.REGULATOR_CHOICES)


def resolve_tenant_by_slug(slug: str) -> Tenant | None:
    """Map a /d/{slug} segment to an active tenant (sub-broker). None if unknown."""
    if not slug:
        return None
    return Tenant.objects.filter(slug=slug.lower(), is_active=True).first()


def _placeholder_values() -> dict:
    """Values a disclosure_template may interpolate — config, never PII.

    Sourced from the canonical compliance settings (single source, ADR-014). Extend
    per-partner/per-tenant (ARN, DSA code…) as multi-partner composition lands.
    """
    return {
        "nse_ap_no": getattr(settings, "NSE_AP_NO", ""),
        "sebi_reg_no": "INZ000031633",
        "market_risk_warning": getattr(settings, "MARKET_RISK_WARNING", ""),
    }


def _block_for(program: ReferralProgram, values: dict) -> str:
    """The rendered disclosure text for one program.

    Uses the program's own template if set; otherwise the canonical central AP
    disclosure block (the exact text the landing page renders). Always append the
    verbatim market-risk warning so every regulator block carries §4.2.
    """
    risk = getattr(settings, "MARKET_RISK_WARNING", "")
    template = (program.disclosure_template or "").strip()
    if template:
        try:
            body = template.format(**values)
        except (KeyError, IndexError):
            # A malformed template must never 500 the compliance page — fall back.
            body = getattr(settings, "AP_DISCLOSURE_BLOCK", "")
    else:
        body = getattr(settings, "AP_DISCLOSURE_BLOCK", "")
    return body, risk


def compose_disclosures(tenant: Tenant) -> list[dict]:
    """Return the ordered disclosure blocks for a tenant's ACTIVE programs.

    Each item: {regulator, regulator_label, program, identification, risk}. Lapsed /
    inactive / soft-deleted programs are excluded (their block drops off — S2-03 §4).
    Ordered by (disclosure_sequence, regulator rank) so securities precede insurance
    precede loans, deterministically.
    """
    programs = (
        ReferralProgram.objects.filter(status="active", deleted_at__isnull=True)
        .filter(tenant=tenant)
        .select_related("partner")
    )
    values = _placeholder_values()
    blocks = []
    for program in programs:
        identification, risk = _block_for(program, values)
        blocks.append(
            {
                "regulator": program.regulator,
                "regulator_label": _REGULATOR_LABEL.get(program.regulator, program.regulator),
                "program_name": program.display_name or program.name,
                "identification": identification,
                "risk": risk,
                "_seq": program.disclosure_sequence,
                "_rank": _REGULATOR_RANK.get(program.regulator, 9),
            }
        )
    blocks.sort(key=lambda b: (b["_seq"], b["_rank"]))
    return blocks
