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
from apps.referrals.models import Customer  # optional referrer phone source (may be absent)

logger = logging.getLogger("gorefer.wati.notify")

TPL_OFFICE = "gorefer_office_new_lead"
TPL_PROSPECT = "gorefer_prospect_welcome"
TPL_REFERRER = "gorefer_referrer_used"


def _office_mobile() -> str:
    return normalize_phone(getattr(settings, "OFFICE_ALERT_NUMBER", ""))


def _referrer_phone_if_known(tenant, client_id: str) -> str:
    """Return the referrer's canonical phone ONLY if GoRefer actually knows it.

    Sprint 1 source: a Customer row (Abhay's own customers). Zoho lookup is M6.
    Unknown → "" → the referrer notification is skipped (never guessed).
    """
    customer = Customer.objects.filter(
        tenant=tenant, client_id=client_id, deleted_at__isnull=True
    ).exclude(mobile="").first()
    return normalize_phone(customer.mobile) if customer else ""


def _create_notification(*, tenant, referral, role, mobile, template, journey_key, skip_reason=""):
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
    from .tasks import enqueue_send  # local import to avoid app-loading cycles

    journey_key = str(referral.pk)
    queued_ids: list[int] = []

    # (a) office / Ashok — always.
    office = _create_notification(
        tenant=tenant, referral=referral, role="office", mobile=_office_mobile(),
        template=TPL_OFFICE, journey_key=journey_key,
        skip_reason="" if _office_mobile() else "office number not configured",
    )
    _maybe_enqueue(office, queued_ids, enqueue_send)

    # (b) prospect — warm UTILITY naming the referrer (opt-in-aware).
    prospect_mobile = normalize_phone(prospect.mobile) if prospect else ""
    prospect_skip = "" if prospect_mobile else "prospect mobile unknown"
    if prospect and _is_opted_out(prospect):
        prospect_skip = "prospect opted out"
    prospect_n = _create_notification(
        tenant=tenant, referral=referral, role="prospect", mobile=prospect_mobile,
        template=TPL_PROSPECT, journey_key=journey_key, skip_reason=prospect_skip,
    )
    _maybe_enqueue(prospect_n, queued_ids, enqueue_send)

    # (c) referrer — ONLY if phone known; else skip (never guess).
    referrer_mobile = _referrer_phone_if_known(tenant, client_id)
    referrer_n = _create_notification(
        tenant=tenant, referral=referral, role="referrer", mobile=referrer_mobile,
        template=TPL_REFERRER, journey_key=journey_key,
        skip_reason="" if referrer_mobile else "referrer phone unknown",
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
