"""Lead capture API (M3) — POST /api/leads.

Capture-first: save the lead to GoRefer, then (M6) mirror to Zoho. Returns a
continue token the page uses to trigger the server-side 302 to Zerodha. The raw
Zerodha URL / partner code are never returned here.
"""
from __future__ import annotations

import re

from ninja import Router, Schema
from ninja.errors import HttpError

from apps.referrals.lead_service import capture_lead
from apps.referrals.models import ReferralIdentity
from apps.referrals.validators import InvalidClientId, validate_client_id
from apps.tenants.resolve import get_current_tenant

router = Router()

_MOBILE_OK = re.compile(r"^[6-9]\d{9}$")


class LeadIn(Schema):
    client_id: str
    name: str
    mobile: str
    email: str | None = ""
    city: str | None = ""
    consent: bool
    submitted_by: str = "friend"


class LeadOut(Schema):
    lead_id: int
    status: str
    continue_url: str


@router.post("/", response={201: LeadOut})
def create_lead(request, payload: LeadIn):
    try:
        client_id = validate_client_id(payload.client_id)
    except InvalidClientId:
        raise HttpError(400, "invalid client_id")

    name = (payload.name or "").strip()
    if not (2 <= len(name) <= 80):
        raise HttpError(422, "name must be 2–80 characters")
    digits = "".join(ch for ch in (payload.mobile or "") if ch.isdigit())[-10:]
    if not _MOBILE_OK.match(digits):
        raise HttpError(422, "mobile must be a 10-digit Indian number starting 6–9")
    if not payload.consent:
        raise HttpError(422, "consent is required")

    tenant = get_current_tenant(request)
    # The referral/identity must already exist from the landing view (lazy M2/M3).
    identity = ReferralIdentity.objects.filter(
        tenant=tenant, client_id=client_id, id_source="native"
    ).first()
    if identity is None:
        raise HttpError(400, "no active referral journey for this client_id")
    referral = identity.referrals.filter(source="referral_link").order_by("id").first()
    if referral is None:
        raise HttpError(400, "no referral journey for this client_id")

    lead = capture_lead(
        tenant=tenant,
        referral=referral,
        name=name,
        mobile=digits,
        email=(payload.email or "").strip(),
        city=(payload.city or "").strip(),
        consent=payload.consent,
        submitted_by=payload.submitted_by,
    )
    # The page follows continue_url to trigger the server-side 302 (M2 engine).
    return {"lead_id": lead.pk, "status": lead.status, "continue_url": f"/r/{client_id}/continue"}
