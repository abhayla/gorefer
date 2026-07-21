"""Referrer account lifecycle (M13): create/bind, login, verification decisions.

The Django auth user behind a referrer is a plain non-staff user with an UNUSABLE
password (login only ever happens via OTP/OAuth — there is no password door to
brute-force). One user per `(tenant, client_id)`; the account row carries the bind.
"""
from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.db import transaction
from django.utils import timezone

from apps.common.phone import normalize_phone

from .models import ReferrerAccount, VerificationRequest

logger = logging.getLogger("gorefer.accounts")

# Evidence upload caps (Path B). PII discipline: small, image-only, erasable.
EVIDENCE_MAX_BYTES = 5 * 1024 * 1024
EVIDENCE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class VerificationError(Exception):
    """A verification decision that cannot be applied (surfaced to the admin)."""


def _username_for(tenant, client_id: str) -> str:
    return f"ref_{getattr(tenant, 'id', None) or 0}_{client_id}".lower()


@transaction.atomic
def get_or_create_account(
    tenant,
    client_id: str,
    *,
    bound_via: str,
    google_email: str = "",
    mobile: str = "",
) -> ReferrerAccount:
    """Idempotently create the `(tenant, client_id)` account + its auth user.

    An existing account is enriched, never re-bound: a later OAuth login may add the
    google_email to an OTP-bound account (both proofs passed), but bound_via keeps
    recording the FIRST successful proof.
    """
    account = ReferrerAccount.objects.filter(tenant=tenant, client_id=client_id).first()
    if account is not None:
        changed = []
        if google_email and not account.google_email:
            account.google_email = google_email.strip().lower()
            changed.append("google_email")
        if mobile and not account.mobile:
            account.mobile = normalize_phone(mobile)
            changed.append("mobile")
        if changed:
            account.save(update_fields=[*changed, "updated_at"])
        return account

    user_model = get_user_model()
    user, _created = user_model.objects.get_or_create(
        username=_username_for(tenant, client_id),
        defaults={"is_staff": False, "is_superuser": False},
    )
    if user.has_usable_password():
        # Never a password door: referrer users authenticate via OTP/OAuth only.
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return ReferrerAccount.objects.create(
        tenant=tenant,
        user=user,
        client_id=client_id,
        bound_via=bound_via,
        google_email=(google_email or "").strip().lower(),
        mobile=normalize_phone(mobile) if mobile else "",
    )


def login_account(request, account: ReferrerAccount) -> None:
    """Start the Django session for a verified referrer account."""
    auth_login(request, account.user, backend="django.contrib.auth.backends.ModelBackend")


def account_for_request(request) -> ReferrerAccount | None:
    """The ACTIVE referrer account behind the current session, if any."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None
    account = getattr(user, "referrer_account", None)
    if account is None or account.status != ReferrerAccount.STATUS_ACTIVE:
        return None
    return account


# --- Verification queue (ADR-027 mismatch + ADR-035 Path B) -----------------------

def submit_evidence_request(
    tenant, *, client_id: str, registered_name: str, mobile_entered: str,
    evidence_bytes: bytes, content_type: str,
) -> VerificationRequest:
    """Path B: store the (capped, image-only) evidence for human review."""
    if not evidence_bytes:
        raise VerificationError("Evidence screenshot is required.")
    if len(evidence_bytes) > EVIDENCE_MAX_BYTES:
        raise VerificationError("Screenshot too large (max 5 MB).")
    if content_type not in EVIDENCE_CONTENT_TYPES:
        raise VerificationError("Screenshot must be a JPEG, PNG, or WebP image.")
    # One open request per (tenant, client_id, kind): a re-submit replaces the
    # pending evidence rather than queueing duplicates for Ashok to reconcile.
    existing = VerificationRequest.objects.filter(
        tenant=tenant, client_id=client_id,
        kind=VerificationRequest.KIND_EVIDENCE, status=VerificationRequest.STATUS_PENDING,
    ).first()
    if existing is not None:
        existing.registered_name = registered_name.strip()
        existing.mobile_entered = normalize_phone(mobile_entered) if mobile_entered else ""
        existing.evidence = evidence_bytes
        existing.evidence_content_type = content_type
        existing.evidence_size = len(evidence_bytes)
        existing.evidence_purged_at = None
        existing.save()
        return existing
    return VerificationRequest.objects.create(
        tenant=tenant,
        kind=VerificationRequest.KIND_EVIDENCE,
        client_id=client_id,
        registered_name=registered_name.strip(),
        mobile_entered=normalize_phone(mobile_entered) if mobile_entered else "",
        evidence=evidence_bytes,
        evidence_content_type=content_type,
        evidence_size=len(evidence_bytes),
    )


def submit_oauth_mismatch_request(
    tenant, *, client_id: str, google_email: str, mobile_entered: str,
) -> VerificationRequest:
    """ADR-027: neither email nor mobile matched — queue for admin review."""
    existing = VerificationRequest.objects.filter(
        tenant=tenant, client_id=client_id,
        kind=VerificationRequest.KIND_OAUTH_MISMATCH, status=VerificationRequest.STATUS_PENDING,
    ).first()
    if existing is not None:
        existing.google_email = google_email.strip().lower()
        existing.mobile_entered = normalize_phone(mobile_entered) if mobile_entered else ""
        existing.save(update_fields=["google_email", "mobile_entered", "updated_at"])
        return existing
    return VerificationRequest.objects.create(
        tenant=tenant,
        kind=VerificationRequest.KIND_OAUTH_MISMATCH,
        client_id=client_id,
        google_email=google_email.strip().lower(),
        mobile_entered=normalize_phone(mobile_entered) if mobile_entered else "",
    )


@transaction.atomic
def approve_verification(request_obj: VerificationRequest, *, admin_user) -> ReferrerAccount:
    """Approve: bind the account, put the referrer on file, purge the evidence.

    ADR-035: on approval the referrer is upserted so FUTURE logins are Path A —
    locally as a `Customer` row (the resolver's first source), and into Zoho via the
    write adapter (log-only while ENABLE_ZOHO_WRITE is off; guardrail #2 untouched —
    identity fields only, never status).
    """
    if request_obj.status != VerificationRequest.STATUS_PENDING:
        raise VerificationError("Request already decided.")

    tenant = request_obj.tenant
    mobile = request_obj.mobile_entered
    _put_on_file(tenant, request_obj, mobile)

    account = get_or_create_account(
        tenant,
        request_obj.client_id,
        bound_via=ReferrerAccount.BOUND_VIA_ADMIN,
        google_email=request_obj.google_email,
        mobile=mobile,
    )

    request_obj.status = VerificationRequest.STATUS_APPROVED
    request_obj.decided_by = getattr(admin_user, "id", None)
    request_obj.decided_at = timezone.now()
    request_obj.purge_evidence()
    request_obj.save()
    logger.info(
        "Verification approved: %s client_id=%s by admin=%s (evidence purged)",
        request_obj.kind, request_obj.client_id, request_obj.decided_by,
    )
    return account


@transaction.atomic
def reject_verification(request_obj: VerificationRequest, *, admin_user, note: str = "") -> None:
    if request_obj.status != VerificationRequest.STATUS_PENDING:
        raise VerificationError("Request already decided.")
    request_obj.status = VerificationRequest.STATUS_REJECTED
    request_obj.decided_by = getattr(admin_user, "id", None)
    request_obj.decided_at = timezone.now()
    request_obj.decision_note = note.strip()
    request_obj.purge_evidence()
    request_obj.save()
    logger.info(
        "Verification rejected: %s client_id=%s by admin=%s (evidence purged)",
        request_obj.kind, request_obj.client_id, request_obj.decided_by,
    )


def _put_on_file(tenant, request_obj: VerificationRequest, mobile: str) -> None:
    """Create/enrich the local Customer row + upsert the Zoho Contact."""
    from apps.referrals.models import Customer, ReferralProgram

    program = (
        ReferralProgram.objects.filter(tenant=tenant, status="active", deleted_at__isnull=True)
        .select_related("partner")
        .first()
    )
    if program is None:
        raise VerificationError("No active referral program to attach the referrer to.")

    name = request_obj.registered_name.strip()
    first, _, last = name.partition(" ")
    customer, created = Customer.objects.get_or_create(
        tenant=tenant,
        program=program,
        client_id=request_obj.client_id,
        defaults={
            "partner": program.partner,
            "mobile": mobile,
            "email": request_obj.google_email,
            "first_name": first,
            "last_name": last,
        },
    )
    if not created:
        changed = []
        if mobile and not customer.mobile:
            customer.mobile = mobile
            changed.append("mobile")
        if request_obj.google_email and not customer.email:
            customer.email = request_obj.google_email
            changed.append("email")
        if changed:
            customer.save(update_fields=[*changed, "updated_at"])

    from apps.integrations.zoho.adapter import get_zoho_adapter

    try:
        get_zoho_adapter().upsert_referrer_contact(
            client_id=request_obj.client_id,
            name=name,
            mobile=mobile,
            email=request_obj.google_email,
        )
    except Exception:  # noqa: BLE001 — the local bind must not fail on a Zoho hiccup
        logger.warning(
            "Zoho referrer-contact upsert failed for %s — local bind kept; retry manually",
            request_obj.client_id, exc_info=True,
        )
