"""Lead-time WATI notification service (M5).

On `lead_captured`, fire THREE transactional notifications (doc-08 A6):
  (a) office/Ashok  — "new lead {name}, referred by {client_id}"       [UTILITY]
  (b) prospect      — warm UTILITY naming the referrer + next steps      [UTILITY]
  (c) referrer      — ONLY if the referrer's phone is known; else skip    [UTILITY]

Rules:
  - Deduped: one Notification row per (recipient + template + journey) idempotency
    key — a repeat trigger never re-sends.
  - Opt-in-aware: honour Do_not_contact / opt-out before sending; first message to a
    non-opted-in prospect is a warm UTILITY notice naming the referrer (never a cold
    marketing blast) — Meta rule (A4).
  - Phone normalized one canonical way (91-prefix) via the shared helper.
  - "Referrer phone known" = GoRefer actually has it (Abhay's own customers / Zoho).
    In Sprint 1 (no Zoho yet, M6) it is almost always unknown → SKIP, never guess.
  - Sends are enqueued (django-q) and verified by TERMINAL status, never HTTP 200.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import IntegrityError

from apps.common.phone import normalize_phone
from apps.integrations.models import Notification
from apps.referrals.models import Customer  # optional referrer identity source (may be absent)

logger = logging.getLogger("gorefer.wati.notify")

# Fallbacks for template variables that may be absent — a Meta template has no optional
# variables, so every slot is always filled (never an empty string). See the
# wati-template design standard.
FALLBACK_EMAIL = "not provided"
FALLBACK_REFERRER = "not on file"


def _office_mobile() -> str:
    return normalize_phone(getattr(settings, "OFFICE_ALERT_NUMBER", ""))


def _referrer_if_known(tenant, client_id: str):
    """Return the referrer's Customer row ONLY if GoRefer actually knows it (has a phone).

    Sprint 1 source: a Customer row (Abhay's own customers). Zoho lookup is M6.
    Unknown → None → the referrer notification is skipped, and the office alert shows
    the referrer fields as "not on file" (never guessed).
    """
    return (
        Customer.objects.filter(tenant=tenant, client_id=client_id, deleted_at__isnull=True)
        .exclude(mobile="")
        .first()
    )


def _referrer_display_name(customer) -> str:
    if customer is None:
        return ""
    name = f"{customer.first_name} {customer.last_name}".strip()
    return name


def _params(pairs: list[tuple[str, str]]) -> list[dict]:
    """Build the ordered [{"name","value"}] list the adapter sends as template vars."""
    return [{"name": n, "value": (v if (v is not None and str(v) != "") else "")} for n, v in pairs]


def _create_notification(*, tenant, referral, role, mobile, template, journey_key,
                         template_params=None, skip_reason=""):
    """Idempotent create: one row per (role + template + journey). Returns row or None."""
    idem = f"{role}:{template}:{journey_key}"
    try:
        return Notification.objects.create(
            tenant=tenant,
            referral=referral,
            recipient_role=role,
            recipient_mobile=mobile,
            template=template,
            category="UTILITY",
            template_params=template_params or [],
            idempotency_key=idem,
            status="skipped" if skip_reason else "queued",
            skip_reason=skip_reason,
        )
    except IntegrityError:
        # Already created for this journey — dedup, no re-send.
        logger.info("notification dedup: %s already exists", idem)
        return None


def queue_lead_notifications(*, tenant, referral, prospect, client_id: str) -> list[int]:
    """Create the three notifications (deduped, opt-in-aware) and enqueue their sends.

    Returns the list of Notification ids that were newly queued (excludes skipped +
    deduped). Enqueue happens via the background queue; in sync/demo mode the task
    runs inline and verifies terminal status.
    """
    from apps.config.preferences import (
        LANG_EN,
        SUPPORT_HELPLINE_PHONE,
        get_preferences,
        notification_routing,
        notify_template_name,
    )

    from .tasks import enqueue_send  # local import to avoid app-loading cycles

    tenant_id = getattr(tenant, "id", None)
    journey_key = str(referral.pk)
    queued_ids: list[int] = []
    # Admin routing toggles (Settings → Notifications). A role switched OFF is recorded
    # as SKIPPED WITH A REASON rather than not created: the funnel must still show the
    # message did not go and why. Routing is additive to the existing suppressions
    # (opt-out, unknown phone) — it can only ever suppress, never force a send.
    routed = notification_routing(tenant_id)

    def _routing_skip(role: str) -> str:
        return "" if routed.get(role, True) else "turned off in settings"

    # Language for the customer-facing templates. Sprint 1 has no per-referrer language
    # yet (that Tier-3 pref is dormant until ENABLE_CUSTOMER_LOGIN), so default English.
    lang = LANG_EN

    # Resolve the shared field values once (the office alert + the prospect message both
    # reference the referrer / office number). Referrer identity is best-effort.
    prospect_name = (prospect.name if prospect and prospect.name else "") or ""
    prospect_mobile = normalize_phone(prospect.mobile) if prospect else ""
    referrer = _referrer_if_known(tenant, client_id)
    referrer_name = _referrer_display_name(referrer)
    office_number = get_preferences(tenant_id).get(SUPPORT_HELPLINE_PHONE) or ""

    # (a) office / Ashok — internal alert. Vars (approved order):
    # prospect_name, prospect_mobile, referrer_name, referrer_client_id.
    office_skip = _routing_skip("office") or (
        "" if _office_mobile() else "office number not configured"
    )
    office_params = _params([
        ("prospect_name", prospect_name or "A new lead"),
        ("prospect_mobile", prospect_mobile or "not provided"),
        ("referrer_name", referrer_name or FALLBACK_REFERRER),
        ("referrer_client_id", client_id),
    ])
    office = _create_notification(
        tenant=tenant, referral=referral, role="office", mobile=_office_mobile(),
        template=notify_template_name("office", lang=LANG_EN, tenant_id=tenant_id),
        journey_key=journey_key, template_params=office_params, skip_reason=office_skip,
    )
    _maybe_enqueue(office, queued_ids, enqueue_send)

    # (b) prospect — warm notice naming the referrer + callback number (opt-in-aware).
    # Vars (approved order): prospect_name, referrer_name, office_number.
    prospect_skip = "" if prospect_mobile else "prospect mobile unknown"
    if prospect and _is_opted_out(prospect):
        prospect_skip = "prospect opted out"
    # Routing is checked LAST so it can add a skip but never clear one: an opted-out
    # prospect stays opted out regardless of the toggle (BR-008 / doc-08 A4).
    prospect_skip = prospect_skip or _routing_skip("prospect")
    prospect_params = _params([
        ("prospect_name", prospect_name or "there"),
        ("referrer_name", referrer_name or "A friend"),
        ("office_number", office_number),
    ])
    prospect_n = _create_notification(
        tenant=tenant, referral=referral, role="prospect", mobile=prospect_mobile,
        template=notify_template_name("prospect", lang=lang, tenant_id=tenant_id),
        journey_key=journey_key, template_params=prospect_params, skip_reason=prospect_skip,
    )
    _maybe_enqueue(prospect_n, queued_ids, enqueue_send)

    # (c) referrer — ONLY if phone known; else skip (never guess).
    # Vars (approved order): referrer_name, prospect_name.
    referrer_mobile = normalize_phone(referrer.mobile) if referrer else ""
    referrer_skip = "" if referrer_mobile else "referrer phone unknown"
    referrer_skip = referrer_skip or _routing_skip("referrer")
    referrer_params = _params([
        ("referrer_name", referrer_name or "there"),
        ("prospect_name", prospect_name or "someone"),
    ])
    referrer_n = _create_notification(
        tenant=tenant, referral=referral, role="referrer", mobile=referrer_mobile,
        template=notify_template_name("referrer", lang=lang, tenant_id=tenant_id),
        journey_key=journey_key, template_params=referrer_params, skip_reason=referrer_skip,
    )
    _maybe_enqueue(referrer_n, queued_ids, enqueue_send)

    return queued_ids


def _is_opted_out(prospect) -> bool:
    # Sprint 1 has no explicit opt-out field on Prospect; a first warm UTILITY is
    # permitted (A4). Hook kept so a future opt-out field suppresses cleanly.
    return getattr(prospect, "whatsapp_opt_out", False)


def _maybe_enqueue(notification, queued_ids, enqueue_send):
    if notification is not None and notification.status == "queued":
        enqueue_send(notification.id)
        queued_ids.append(notification.id)
