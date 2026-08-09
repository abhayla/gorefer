"""Referrer conversion-congrats (T-058, P-01 / Gap 5 closure).

Doc 04 §4.3 always specified a one-time WATI congratulations to the referrer when a
conversion syncs; it was deferred to Sprint 2. This is that notification — hooked
ONCE, downstream of `apps.integrations.zoho.ingest` applying an `account_opened`
conversion (never on reversal/no-op/replay-refused paths).

Vendor-neutral (top-level in `apps.integrations`, not under `.wati`/`.zoho`): it uses
only the boundary ports (`get_messaging_port`, `get_crm_read_port`), same as
`apps.followups.tasks` does for the nudge engine.

Recipient: the CREDITED referrer only, exactly as Zoho names them (ADR-016). Mobile
is resolved via the CRM READ port by client_id — never guessed, never the mobile
carried on the conversion payload (a conversion carries no mobile by design).

Channel: an OPEN 24h follow-up window -> a session message through the SAME
followups send gates (quiet hours, min-gap, opt-out) the nudge engine already
enforces; otherwise a WhatsApp template, gated by a cascade key whose default is
EMPTY — so the template leg stays DORMANT until the owner configures an approved
name (template creation is not this task, owner ruling 2026-08-08).

Idempotent: one `Notification` row per conversion (unique `idempotency_key`), created
BEFORE any outbound call so a concurrent/replayed enqueue can only ever race the
insert, never double-send.
"""
from __future__ import annotations

import logging

from django.db import IntegrityError
from django.utils import timezone

from apps.common.phone import normalize_phone
from apps.events import vocab
from apps.events.models import Event
from apps.integrations.models import Notification
from apps.integrations.ports import get_crm_read_port, get_messaging_port

logger = logging.getLogger("gorefer.integrations.congrats")

ROLE = "referrer"
# Placeholder written at row-creation time (before the channel is decided) and
# overwritten with the real template/marker once resolved.
_PENDING_TEMPLATE = "pending"
SESSION_MARKER_TEMPLATE = "session:referrer_conversion_congrats"


def enqueue_referrer_congrats(*, referral_id: int, conversion_id: int) -> None:
    """Enqueue the send (runs inline when Q_CLUSTER sync=True, the dev/CI/demo default)."""
    from django_q.tasks import async_task

    async_task(
        "apps.integrations.congrats.send_referrer_congrats_task", referral_id, conversion_id
    )


def send_referrer_congrats_task(referral_id: int, conversion_id: int) -> str:
    """Send (or skip) one referrer congrats. Best-effort: NEVER raises.

    This may run synchronously inside the caller's `transaction.on_commit` (sync
    django-q mode) — an exception here must never propagate into the ingest webhook
    that scheduled it, so every branch is wrapped.
    """
    try:
        return _send(referral_id, conversion_id)
    except Exception:
        logger.warning(
            "referrer congrats send failed: referral=%s conversion=%s",
            referral_id, conversion_id, exc_info=True,
        )
        return "error"


def _send(referral_id: int, conversion_id: int) -> str:
    from apps.followups import services as fup_services
    from apps.integrations.models import Conversion
    from apps.referrals.models import Referral

    referral = (
        Referral.objects.filter(pk=referral_id, deleted_at__isnull=True)
        .select_related("referral_identity", "tenant")
        .first()
    )
    conversion = Conversion.objects.filter(pk=conversion_id).first()
    if referral is None or conversion is None or referral.referral_identity is None:
        return "noop"

    tenant = referral.tenant
    tenant_id = getattr(tenant, "id", None)
    client_id = referral.referral_identity.client_id

    notification = _reserve(tenant=tenant, referral=referral, conversion_id=conversion.pk)
    if notification is None:
        return "dedup"

    contact = get_crm_read_port().fetch_contact_by_client_id(client_id=client_id)
    mobile = normalize_phone(contact.mobile or "") if contact.matched else ""
    if not mobile:
        return _skip(notification, "referrer mobile unknown")

    if contact.whatsapp_opt_out or contact.do_not_contact:
        return _skip(notification, "referrer opted out")
    if fup_services.is_opted_out(tenant, mobile):
        return _skip(notification, "referrer opted out")

    notification.recipient_mobile = mobile
    referrer_name = (contact.full_name or "").strip() or "there"
    now = timezone.now()
    window = fup_services.get_window(tenant, mobile)

    if fup_services.window_is_open(window, now):
        if fup_services.in_quiet_hours(now, tenant_id):
            return _skip(notification, "held: quiet hours")
        if fup_services.within_min_gap(tenant, mobile, now, tenant_id):
            return _skip(notification, "held: min-gap")
        notification.template = SESSION_MARKER_TEMPLATE
        body = _session_body(tenant_id, referrer_name)
        result = get_messaging_port().send_session_text(to=mobile, message=body)
    else:
        template = _template_name(tenant_id)
        if not template:
            return _skip(notification, "no template configured")
        notification.template = template
        result = get_messaging_port().send_template(to=mobile, template=template, params={})

    if result.accepted:
        notification.status = "accepted"
        notification.provider_message_id = result.provider_message_id or ""
        notification.save(update_fields=[
            "status", "recipient_mobile", "template", "provider_message_id", "updated_at",
        ])
        _emit_event(tenant, referral, "sent")
        return "sent"

    notification.status = "failed"
    notification.save(update_fields=["status", "recipient_mobile", "template", "updated_at"])
    _emit_event(tenant, referral, "failed")
    return "failed"


def _reserve(*, tenant, referral, conversion_id: int) -> Notification | None:
    """Atomic dedupe: one row per conversion, EVER — across re-ingests, reconciler
    sweeps, and webhook replays. Created before any outbound call."""
    idem_key = f"referrer_congrats:{conversion_id}"
    try:
        return Notification.objects.create(
            tenant=tenant, referral=referral, recipient_role=ROLE,
            recipient_mobile="", template=_PENDING_TEMPLATE, category="UTILITY",
            idempotency_key=idem_key, status="queued",
        )
    except IntegrityError:
        logger.info("referrer congrats dedup: %s already exists", idem_key)
        return None


def _skip(notification: Notification, reason: str) -> str:
    notification.status = "skipped"
    notification.skip_reason = reason
    notification.save(update_fields=[
        "status", "skip_reason", "recipient_mobile", "template", "updated_at",
    ])
    _emit_event(notification.tenant, notification.referral, "skipped", reason=reason)
    return "skipped"


def _emit_event(tenant, referral, outcome: str, *, reason: str = "") -> None:
    """Observable funnel event — no PII (Round-2 #16)."""
    try:
        metadata = {"kind": "referrer_congrats", "outcome": outcome}
        if reason:
            metadata["reason"] = reason
        Event.objects.create(
            tenant=tenant, event_type=vocab.NOTIFICATION, source=vocab.SRC_WATI,
            referral=referral, user_type="system", metadata=metadata,
        )
    except Exception:
        logger.warning("referrer congrats funnel event emit failed", exc_info=True)


def _session_body(tenant_id: int | None, referrer_name: str) -> str:
    from apps.config.cascade import resolve
    from apps.config.preferences import (
        REFERRER_CONVERSION_CONGRATS_BODY_EN,
        REFERRER_CONVERSION_CONGRATS_BODY_EN_DEFAULT,
    )

    body = resolve(
        REFERRER_CONVERSION_CONGRATS_BODY_EN, tenant_id=tenant_id,
        default=REFERRER_CONVERSION_CONGRATS_BODY_EN_DEFAULT,
    )
    return str(body or REFERRER_CONVERSION_CONGRATS_BODY_EN_DEFAULT).replace("{name}", referrer_name)


def _template_name(tenant_id: int | None) -> str:
    from apps.config.cascade import resolve
    from apps.config.preferences import (
        REFERRER_CONVERSION_CONGRATS_TEMPLATE_EN,
        REFERRER_CONVERSION_CONGRATS_TEMPLATE_EN_DEFAULT,
    )

    name = resolve(
        REFERRER_CONVERSION_CONGRATS_TEMPLATE_EN, tenant_id=tenant_id,
        default=REFERRER_CONVERSION_CONGRATS_TEMPLATE_EN_DEFAULT,
    )
    return str(name or "").strip()
