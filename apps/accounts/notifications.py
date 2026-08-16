"""Verification-outcome notifications (T-158).

`apps.accounts.service.approve_verification` / `reject_verification` decide a
pending ADR-027/ADR-035 verification request but, until this module, told the
referrer nothing — an approved referrer only found out by re-trying login, and a
rejected one heard nothing at all. Both `service` functions queue a call into this
module via `transaction.on_commit`, so a notification failure never blocks or
rolls back the decision itself.

Two independent legs, each best-effort (one failing never blocks the other):

  * EMAIL — ships now, over the same Django mail framework `apps.otp.adapters`
    already uses (T-078). Sent to `VerificationRequest.google_email` (the only
    email GoRefer ever holds for a pending request); a request with no email on
    file is skipped cleanly, not an error.
  * WHATSAPP — an ADDITION, not a replacement. Gated behind
    `VERIFICATION_OUTCOME_WHATSAPP_ENABLED` (cascade, default OFF) AND a
    cascade-resolved template name — no template exists at Meta yet (T-159 owns
    that), so this leg is INERT (never calls the messaging port) until BOTH are
    configured. Uses `get_messaging_port()`, which already carries the fail-closed
    computed-variable guard (T-073) — these templates use only ordinary
    (non-computed) params, so the guard is a no-op here but stays in the call path
    for free.

Copy (subject/body/reason wording) is entirely config-resolved (rail E-6 / §6d) —
see `apps.config.preferences` for the keys and their shipped defaults.
"""
from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger("gorefer.accounts.notifications")


def queue_verification_approved(*, request_id: int, account_id: int) -> None:
    """Schedule the approval outcome send, AFTER the decision transaction commits."""
    transaction.on_commit(lambda: _enqueue_approved(request_id, account_id))


def queue_verification_rejected(*, request_id: int) -> None:
    """Schedule the rejection outcome send, AFTER the decision transaction commits."""
    transaction.on_commit(lambda: _enqueue_rejected(request_id))


def _enqueue_approved(request_id: int, account_id: int) -> None:
    from django_q.tasks import async_task

    async_task(
        "apps.accounts.notifications.send_verification_approved_task", request_id, account_id
    )


def _enqueue_rejected(request_id: int) -> None:
    from django_q.tasks import async_task

    async_task("apps.accounts.notifications.send_verification_rejected_task", request_id)


# --- Task entry points (django-q calls these by dotted path; may also run inline
# synchronously under Q_ASYNC=false, i.e. right inside the caller's on_commit hook) ---


def send_verification_approved_task(request_id: int, account_id: int) -> str:
    """Never raises — a notify failure must not surface as a queue error."""
    try:
        return _send_approved(request_id, account_id)
    except Exception:
        logger.warning(
            "verification-approved notify failed: request=%s", request_id, exc_info=True
        )
        return "error"


def send_verification_rejected_task(request_id: int) -> str:
    try:
        return _send_rejected(request_id)
    except Exception:
        logger.warning(
            "verification-rejected notify failed: request=%s", request_id, exc_info=True
        )
        return "error"


def _send_approved(request_id: int, account_id: int) -> str:
    from .models import ReferrerAccount, VerificationRequest

    request_obj = VerificationRequest.objects.filter(pk=request_id).first()
    if request_obj is None:
        return "noop"
    account = ReferrerAccount.objects.filter(pk=account_id).first()

    email_result = _send_email_leg(request_obj, outcome="approved")
    whatsapp_result = _send_whatsapp_leg(request_obj, account=account, outcome="approved")
    return f"email={email_result} whatsapp={whatsapp_result}"


def _send_rejected(request_id: int) -> str:
    from .models import VerificationRequest

    request_obj = VerificationRequest.objects.filter(pk=request_id).first()
    if request_obj is None:
        return "noop"

    email_result = _send_email_leg(request_obj, outcome="rejected")
    whatsapp_result = _send_whatsapp_leg(request_obj, account=None, outcome="rejected")
    return f"email={email_result} whatsapp={whatsapp_result}"


# ------------------------------------------------------------------------ EMAIL leg


def _send_email_leg(request_obj, *, outcome: str) -> str:
    recipient = (request_obj.google_email or "").strip()
    if not recipient:
        logger.info(
            "verification %s email skipped: no on-file address (request=%s)",
            outcome, request_obj.pk,
        )
        return "skipped-no-email"

    try:
        return _send_email(request_obj, recipient=recipient, outcome=outcome)
    except Exception:  # noqa: BLE001 — a mail outage must never break the decision
        logger.warning(
            "verification %s email send failed (request=%s)",
            outcome, request_obj.pk, exc_info=True,
        )
        return "failed"


def _send_email(request_obj, *, recipient: str, outcome: str) -> str:
    from django.conf import settings
    from django.core.mail import EmailMessage

    from apps.config import preferences as prefkeys
    from apps.config.cascade import resolve

    if not _mail_configured():
        logger.info("verification %s email skipped: SMTP not configured", outcome)
        return "suppressed"

    tenant_id = getattr(request_obj.tenant, "id", None)
    name = (request_obj.registered_name or "").strip()
    name_suffix = f" {name}" if name else ""
    login_url = _absolute_login_url()

    if outcome == "approved":
        subject = resolve(
            prefkeys.VERIFICATION_OUTCOME_APPROVED_EMAIL_SUBJECT, tenant_id=tenant_id,
            default=prefkeys.VERIFICATION_OUTCOME_APPROVED_EMAIL_SUBJECT_DEFAULT,
        )
        body_template = resolve(
            prefkeys.VERIFICATION_OUTCOME_APPROVED_EMAIL_BODY, tenant_id=tenant_id,
            default=prefkeys.VERIFICATION_OUTCOME_APPROVED_EMAIL_BODY_DEFAULT,
        )
        placeholders = {"name_suffix": name_suffix, "login_url": login_url}
        default_template = prefkeys.VERIFICATION_OUTCOME_APPROVED_EMAIL_BODY_DEFAULT
    else:
        reason = (request_obj.decision_note or "").strip() or (
            "No specific reason was recorded — please try again or reply to this email "
            "with any questions."
        )
        subject = resolve(
            prefkeys.VERIFICATION_OUTCOME_REJECTED_EMAIL_SUBJECT, tenant_id=tenant_id,
            default=prefkeys.VERIFICATION_OUTCOME_REJECTED_EMAIL_SUBJECT_DEFAULT,
        )
        body_template = resolve(
            prefkeys.VERIFICATION_OUTCOME_REJECTED_EMAIL_BODY, tenant_id=tenant_id,
            default=prefkeys.VERIFICATION_OUTCOME_REJECTED_EMAIL_BODY_DEFAULT,
        )
        placeholders = {"name_suffix": name_suffix, "login_url": login_url, "reason": reason}
        default_template = prefkeys.VERIFICATION_OUTCOME_REJECTED_EMAIL_BODY_DEFAULT

    subject = str(subject or "").strip() or (
        prefkeys.VERIFICATION_OUTCOME_APPROVED_EMAIL_SUBJECT_DEFAULT if outcome == "approved"
        else prefkeys.VERIFICATION_OUTCOME_REJECTED_EMAIL_SUBJECT_DEFAULT
    )
    try:
        body = str(body_template or "").format(**placeholders)
    except (KeyError, IndexError, ValueError):
        # A bad admin-entered placeholder must never block the outcome email.
        logger.warning("verification %s email body has a bad placeholder — using default copy", outcome)
        body = default_template.format(**placeholders)

    sender_identity = getattr(settings, "EMAIL_SENDER_IDENTITY", "") or "GoRefer"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or None
    logger.info(
        "verification %s email send: to=%s subject_len=%d (sender=%s)",
        outcome, _mask_email(recipient), len(subject), sender_identity,
    )
    sent = EmailMessage(subject=subject, body=body, from_email=from_email, to=[recipient]).send(
        fail_silently=False
    )
    return "sent" if sent else "not-accepted"


def _mask_email(address: str) -> str:
    """`abhay@example.com` -> `a***y@example.com` — enough to audit, not to harvest."""
    local, _, domain = address.partition("@")
    if not domain:
        return "***"
    masked = local[:1] + "***" if len(local) <= 2 else f"{local[0]}***{local[-1]}"
    return f"{masked}@{domain}"


def _mail_configured() -> bool:
    from django.conf import settings

    backend = str(getattr(settings, "EMAIL_BACKEND", "") or "")
    if "smtp" not in backend.lower():
        return True
    return bool(getattr(settings, "EMAIL_HOST", ""))


def _absolute_login_url() -> str:
    from django.conf import settings

    from . import service as accounts_service

    path = accounts_service.login_url()
    base = str(getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    return f"{base}{path}" if base else path


# --------------------------------------------------------------------- WHATSAPP leg


def _send_whatsapp_leg(request_obj, *, account, outcome: str) -> str:
    from apps.config import preferences as prefkeys
    from apps.config.cascade import resolve
    from apps.config.i18n import resolve_stored_referrer_language

    tenant_id = getattr(request_obj.tenant, "id", None)
    enabled = resolve(
        prefkeys.VERIFICATION_OUTCOME_WHATSAPP_ENABLED, tenant_id=tenant_id,
        default=prefkeys.VERIFICATION_OUTCOME_WHATSAPP_ENABLED_DEFAULT,
    )
    if not enabled:
        return "disabled"

    # Language follows the EXISTING referrer_language cascade key (doc 15 §8) — the
    # same source every other referrer-facing send already reads — never a new signal.
    lang = resolve_stored_referrer_language(tenant_id)
    if outcome == "approved":
        key = (
            prefkeys.VERIFICATION_OUTCOME_APPROVED_TEMPLATE_HI if lang == "hi"
            else prefkeys.VERIFICATION_OUTCOME_APPROVED_TEMPLATE_EN
        )
        default_name = (
            prefkeys.VERIFICATION_OUTCOME_APPROVED_TEMPLATE_HI_DEFAULT if lang == "hi"
            else prefkeys.VERIFICATION_OUTCOME_APPROVED_TEMPLATE_EN_DEFAULT
        )
    else:
        key = (
            prefkeys.VERIFICATION_OUTCOME_NEEDSREVIEW_TEMPLATE_HI if lang == "hi"
            else prefkeys.VERIFICATION_OUTCOME_NEEDSREVIEW_TEMPLATE_EN
        )
        default_name = (
            prefkeys.VERIFICATION_OUTCOME_NEEDSREVIEW_TEMPLATE_HI_DEFAULT if lang == "hi"
            else prefkeys.VERIFICATION_OUTCOME_NEEDSREVIEW_TEMPLATE_EN_DEFAULT
        )
    template = str(resolve(key, tenant_id=tenant_id, default=default_name) or "").strip()
    if not template:
        return "no-template"

    mobile = (account.mobile if account is not None else "") or (request_obj.mobile_entered or "")
    mobile = (mobile or "").strip()
    if not mobile:
        logger.info("verification %s WhatsApp skipped: no on-file mobile (request=%s)",
                    outcome, request_obj.pk)
        return "skipped-no-mobile"

    name = (request_obj.registered_name or "").strip() or "there"
    if outcome == "approved":
        params = {"template_params": [{"name": "name", "value": name}]}
    else:
        reason = (request_obj.decision_note or "").strip() or "details could not be confirmed"
        params = {"template_params": [
            {"name": "name", "value": name},
            {"name": "reason", "value": reason},
        ]}

    try:
        from apps.integrations.ports import get_messaging_port

        result = get_messaging_port().send_template(to=mobile, template=template, params=params)
    except Exception:  # noqa: BLE001 — a vendor hiccup must never break the decision
        logger.warning(
            "verification %s WhatsApp send failed (request=%s template=%s)",
            outcome, request_obj.pk, template, exc_info=True,
        )
        return "failed"
    return "sent" if result.accepted else "not-accepted"
