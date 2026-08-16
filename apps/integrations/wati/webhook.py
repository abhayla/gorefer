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
from apps.referrals.validators import InvalidClientId, validate_client_id_for
from apps.tenants.resolve import get_current_tenant

logger = logging.getLogger("gorefer.wati.webhook")

LEAD_SOURCE_ASSISTED = "whatsapp_assisted"

# Keys we will NEVER accept/persist from an assisted capture (defense in depth).
# Checked both at the API edge (raw body) and here (parsed payload). NEVER a password.
FORBIDDEN_KEYS = frozenset({"password", "pass", "pin", "otp", "pan", "aadhaar", "aadhar"})


def _client_ip(request) -> str:
    # Spoof-resistant (Fable5 H2): trusted-proxy hop, not the appendable xff[0].
    from apps.common.netaddr import trusted_client_ip

    return trusted_client_ip(request)


def authenticate(request) -> bool:
    """Static shared-key + IP allowlist. Both must pass.

    FAILS CLOSED: if WATI_WEBHOOK_KEY is not configured (unset/blank), EVERY request
    is rejected — the check is never skipped and never fails open. A constant-time
    compare avoids leaking the key via timing. The allowlist further restricts source
    IPs; an EMPTY allowlist means "any IP" only in DEBUG (dev/CI) — in production
    (DEBUG=false) an empty allowlist is refused fail-closed (Fable5 H2). The key
    requirement is mandatory in every mode.

    The shared key may arrive EITHER as the `X-Wati-Webhook-Key` header OR as a
    `?token=` query param — Wati's own webhook sender delivers the secret as a query
    param (verified against the live tenant's existing webhooks, which post
    `…?token=<key>`), and it cannot attach a custom header. Both carry the SAME secret
    and are constant-time compared; the query form is what makes Wati's native
    inbound-message webhook usable without relaxing the check. (Trade-off: a query-string
    secret is visible in access logs — acceptable for a rotatable shared webhook token,
    and the same posture the pre-existing firekaro webhook already uses.)
    """
    expected = (getattr(settings, "WATI_WEBHOOK_KEY", "") or "").strip()
    if not expected:
        # Fail closed: no key configured => reject all (do not process the webhook).
        logger.warning("WATI webhook rejected: WATI_WEBHOOK_KEY not configured (fail-closed)")
        return False
    provided = (
        request.headers.get("X-Wati-Webhook-Key", "")
        or request.GET.get("token", "")
        or ""
    ).strip()
    if not hmac.compare_digest(provided, expected):
        return False
    allowlist = [ip for ip in getattr(settings, "WATI_WEBHOOK_IP_ALLOWLIST", "").split(",") if ip]
    if not allowlist:
        if not settings.DEBUG and getattr(settings, "WEBHOOK_REQUIRE_IP_ALLOWLIST", False):
            logger.warning("WATI webhook: empty IP allowlist rejected in prod (fail-closed)")
            return False
        return True  # dev/CI, or interim R2 (static key alone) until allowlist is populated
    return _client_ip(request) in allowlist


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
        # STRICT, per-partner. THIS is the path that created the junk `TALK` identity:
        # a Wati chatbot flow leaked a menu label into the client_id slot and GoRefer
        # accepted it as a referrer. The partner's id pattern now refuses it.
        client_id = validate_client_id_for(get_current_tenant(request), payload.get("client_id"))
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


# --- Inbound message → 24h-window state feed (M-FUP-1, doc 14 §2E) ------------
#
# Every CUSTOMER inbound message opens/refreshes the WhatsApp 24h window. We stamp
# `last_inbound_at` (services.stamp_inbound) so the follow-up send gate can tell an
# open window (free-form session send) from a closed one (template/skip), and on a
# FRESH open we start the AP's cadence (tasks.enqueue_followups). Enqueue is itself
# flag-gated + opt-out-gated, so this is inert until `followups_enabled` is on.


def record_inbound(tenant, mobile: str, at=None, *, prospect_id: int | None = None,
                   source_event: str = "wati_inbound", pref_lang: str = "en",
                   text: str | None = None) -> dict:
    """Stamp the window for one inbound; start the cadence on a fresh open.

    Pure of any HTTP concern so it is unit-testable and reusable (endpoint, backfill,
    or a live getMessages fallback). Returns a small result dict.

    T-149: opt-out detection runs FIRST, before `stamp_inbound` can open a window or
    `enqueue_followups` can start a cadence. A prospect replying "STOP" after >24h of
    silence must never look like a fresh "yes interested" re-engagement — so a matched
    opt-out short-circuits here: the opt-out is recorded (which also cancels every
    pending ScheduledFollowup for this contact) and NOTHING is stamped/enqueued.
    """
    from apps.common.phone import normalize_phone
    from apps.followups import services, tasks

    canonical = normalize_phone(mobile)
    if not canonical:
        return {"stamped": False, "reason": "no mobile"}

    if services.is_optout_text(text, tenant_id=getattr(tenant, "id", None)):
        services.record_opt_out(tenant, canonical, source="keyword")
        return {
            "stamped": False, "mobile": canonical, "opened_fresh": False,
            "enqueued": 0, "opted_out": True, "reason": "opt-out keyword matched",
        }

    window, opened_fresh = services.stamp_inbound(tenant, canonical, at)
    result = {"stamped": True, "mobile": canonical, "opened_fresh": opened_fresh, "enqueued": 0}
    if opened_fresh:
        enq = tasks.enqueue_followups(
            tenant.id,
            canonical,
            opened_at=window.last_inbound_at,
            prospect_id=prospect_id,
            source_event=source_event,
            pref_lang=pref_lang,
        )
        result["enqueued"] = enq.get("created", 0)
    return result
