"""WATI assisted-referral webhook (B4 / ADR-033).

The Wati "Refer directly" flow captures a prospect's Name + Mobile (Email optional)
with the referrer's permission, and POSTs them here. GoRefer creates ONE Zoho lead
(the same capture-first pipeline as the landing form, behind ENABLE_ZOHO_WRITE —
log-only in demo), attributed to the referrer's client_id.

Guardrails (S2-03 §2 / §11):
  - DPDP consent: the lead carries consent + consent_captured_at (the referrer
    obtained the prospect's permission). NEVER a password — name/mobile/email only.
  - Deduped: a repeat post for the same (referrer, prospect mobile) does NOT
    double-create — capture_lead is idempotent on (referral, prospect).
  - PII (name/mobile/email) lives on the erasable Prospect/Lead, never in the
    immutable event log.
  - Status is never set here — account/reward status comes only from Zoho (#2).

Auth (interim R2): static shared key + IP allowlist (HMAC wax-seal deferred DF-2),
mirroring the Zoho webhook.
"""
from __future__ import annotations

import logging

from django.conf import settings

from apps.referrals.lead_service import capture_lead
from apps.referrals.redirect_service import _active_program, _lazy_get_or_create_referral
from apps.referrals.validators import InvalidClientId, validate_client_id
from apps.tenants.resolve import get_current_tenant

logger = logging.getLogger("gorefer.wati.webhook")

LEAD_SOURCE_ASSISTED = "whatsapp_assisted"

# Keys we will NEVER accept/persist from an assisted capture (defense in depth).
# Checked both at the API edge (raw body) and here (parsed payload). NEVER a password.
FORBIDDEN_KEYS = frozenset({"password", "pass", "pin", "otp", "pan", "aadhaar", "aadhar"})


def _client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def authenticate(request) -> bool:
    """Static key + IP allowlist. Both must pass (allowlist empty = allow any — dev)."""
    expected = getattr(settings, "WATI_WEBHOOK_KEY", "")
    provided = request.headers.get("X-Wati-Webhook-Key", "")
    if not expected or provided != expected:
        return False
    allowlist = [ip for ip in getattr(settings, "WATI_WEBHOOK_IP_ALLOWLIST", "").split(",") if ip]
    if allowlist and _client_ip(request) not in allowlist:
        return False
    return True


class AssistedCaptureError(ValueError):
    """Raised for a malformed assisted-capture payload (never 500)."""


def process_assisted_capture(request, payload: dict) -> dict:
    """Create one Zoho lead from an assisted-referral capture. Returns a result dict.

    payload: {client_id, name, mobile, email?, consent?}. `client_id` is the
    REFERRER's Zerodha id (who is referring); the prospect is name/mobile/email. The
    referrer identity+referral are created lazily if this is the referrer's first
    appearance (they may not have clicked their own link).
    """
    # Reject any credential-shaped field outright — never store a password (#B4).
    for key in payload:
        if str(key).lower() in FORBIDDEN_KEYS:
            raise AssistedCaptureError(f"forbidden field in assisted capture: {key}")

    try:
        client_id = validate_client_id(payload.get("client_id"))
    except InvalidClientId as exc:
        raise AssistedCaptureError(f"invalid referrer client_id: {exc}") from exc

    name = (payload.get("name") or "").strip()
    mobile = (payload.get("mobile") or "").strip()
    if not name:
        raise AssistedCaptureError("prospect name is required")
    if not mobile:
        raise AssistedCaptureError("prospect mobile is required")
    email = (payload.get("email") or "").strip()
    # Consent defaults True: the assisted flow only reaches here after the referrer
    # affirms they have the prospect's permission (DPDP). An explicit false is honoured.
    consent = bool(payload.get("consent", True))

    tenant = get_current_tenant(request)
    program = _active_program(tenant)
    # Lazily resolve/create the referrer's identity + referral (same as a first click).
    referral = _lazy_get_or_create_referral(tenant, program, client_id)

    lead = capture_lead(
        tenant=tenant,
        referral=referral,
        name=name,
        mobile=mobile,
        email=email,
        city="",
        consent=consent,
        submitted_by="referrer",
        lead_source=LEAD_SOURCE_ASSISTED,
    )
    logger.info(
        "assisted capture -> lead %s (referrer=%s, consent=%s, zoho_write=%s)",
        lead.pk, client_id, consent, getattr(settings, "ENABLE_ZOHO_WRITE", False),
    )
    return {
        "status": "ok",
        "lead_id": lead.pk,
        "lead_source": lead.lead_source,
        "consent": lead.consent,
        "deduped": lead.status == "new" and lead.pk is not None,
    }
