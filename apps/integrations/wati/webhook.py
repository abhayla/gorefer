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

import hmac
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
    """Static shared-key + IP allowlist. Both must pass.

    FAILS CLOSED: if WATI_WEBHOOK_KEY is not configured (unset/blank), EVERY request
    is rejected — the check is never skipped and never fails open. A constant-time
    compare avoids leaking the key via timing. The allowlist (when set) further
    restricts source IPs; an empty allowlist means "any IP" (dev only), but that
    never relaxes the mandatory key requirement.
    """
    expected = (getattr(settings, "WATI_WEBHOOK_KEY", "") or "").strip()
    if not expected:
        # Fail closed: no key configured => reject all (do not process the webhook).
        logger.warning("WATI webhook rejected: WATI_WEBHOOK_KEY not configured (fail-closed)")
        return False
    provided = (request.headers.get("X-Wati-Webhook-Key", "") or "").strip()
    if not hmac.compare_digest(provided, expected):
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
    # NB: this log line previously read `getattr(settings, "ENABLE_ZOHO_WRITE", False)`,
    # which ALWAYS logged False — ENABLE_ZOHO_WRITE is a flag, not a Django setting, so
    # the getattr never found it. Log-only (it gated nothing), but it would have
    # actively misled anyone debugging a write. Now reports the effective value.
    from apps.config.integration_flags import ENABLE_ZOHO_WRITE, resolve_flag

    logger.info(
        "assisted capture -> lead %s (referrer=%s, consent=%s, zoho_write=%s)",
        lead.pk, client_id, consent, resolve_flag(ENABLE_ZOHO_WRITE),
    )
    return {
        "status": "ok",
        "lead_id": lead.pk,
        "lead_source": lead.lead_source,
        "consent": lead.consent,
        "deduped": lead.status == "new" and lead.pk is not None,
    }
