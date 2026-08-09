"""Program-brand resolution for MESSAGE copy (T-059 — the partner-#2 enabler).

T-055's checker found the WhatsApp share message hard-names "Zerodha" for any
partner's identity. Pages already resolve the brand correctly via the T-056
fallback chain (`apps.accounts.hub._brand_name`) — this module gives message-copy
builders (share prefill, hub share message, followup nudges) the SAME chain, so a
`{program_brand}` placeholder in a copy default renders the right brand with no
code change when a second program (Groww, ...) is seeded.

Not a new config tier: this is plain code that resolves what the DB already holds
(ReferralProgram.display_name / .name / Partner.name) — the cascade keeps carrying
only the template TEXT, exactly as before.
"""
from __future__ import annotations


def brand_for_program(program) -> str:
    """`program.display_name` -> `program.name` -> `program.partner.name` -> ""."""
    if program is None:
        return ""
    display_name = getattr(program, "display_name", "") or ""
    if display_name:
        return display_name
    name = getattr(program, "name", "") or ""
    if name:
        return name
    partner = getattr(program, "partner", None)
    if partner is not None:
        partner_name = getattr(partner, "name", "") or ""
        if partner_name:
            return partner_name
    return ""


def brand_for_tenant_id(tenant_id) -> str:
    """No identity/program in scope — fall back to the tenant's single active
    program (Sprint 1: Zerodha). Never a hard literal; "" if none is seeded."""
    from apps.referrals.models import ReferralProgram
    from apps.referrals.redirect_service import get_active_program

    try:
        program = get_active_program(tenant_id)
    except ReferralProgram.DoesNotExist:
        return ""
    return brand_for_program(program)
