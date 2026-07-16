"""Lead capture service (M3) — capture-FIRST (06-API §5.3).

On "Continue to Zerodha": save the lead to GoRefer FIRST (Prospect + Lead + a
`lead_captured` event), THEN mirror to Zoho ASYNCHRONOUSLY (M6 + Model 2) — the
upsert is enqueued on_commit, so the submit never waits on Zoho and a Zoho outage
leaves the lead `pending` for the retry/backfill sweep rather than stranding it.
The Zoho write stays behind ENABLE_ZOHO_WRITE=false — the adapter logs the intended
call in demo mode, so the whole flow works offline.

Guardrails:
  - Account/reward STATUS is never set here — that comes only from Zoho (M6).
  - PII (name/mobile/email/city) lives on the erasable Prospect/Lead, never in the
    immutable event log.
  - Phone normalized one canonical way via the shared helper.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.common.phone import normalize_phone
from apps.events import vocab
from apps.events.models import Event
from apps.integrations.wati.notify import queue_lead_notifications
from apps.integrations.zoho.tasks import enqueue_upsert
from apps.referrals.models import Lead, Prospect, Referral

logger = logging.getLogger("gorefer.leads")


@transaction.atomic
def capture_lead(*, tenant, referral: Referral, name: str, mobile: str, email: str, city: str,
                 consent: bool, submitted_by: str = "friend", lead_source: str = "landing") -> Lead:
    """Persist the prospect + lead in GoRefer (capture-first), emit lead_captured.

    Idempotent-ish: an existing live lead for the same (referral, normalized mobile)
    is returned unchanged rather than duplicated.

    `lead_source` marks how the lead entered — 'landing' (self-serve form) or
    'whatsapp_assisted' (B4). For the assisted branch `consent=True` records the
    referrer-obtained DPDP consent, stamped with consent_captured_at. NEVER a
    password — name/mobile/email only.
    """
    canonical_mobile = normalize_phone(mobile)

    prospect, _ = Prospect.objects.get_or_create(
        tenant=tenant,
        mobile=canonical_mobile,
        defaults={"name": name, "email": email, "city": city, "lead_source": lead_source},
    )

    existing = Lead.objects.filter(
        tenant=tenant, referral=referral, prospect=prospect, deleted_at__isnull=True
    ).first()
    if existing is not None:
        return existing

    consent_at = timezone.now() if consent else None
    lead = Lead.objects.create(
        tenant=tenant,
        referral=referral,
        prospect=prospect,
        status="new",
        submitted_by=submitted_by,
        lead_source=lead_source,
        consent=consent,
        consent_captured_at=consent_at,
    )

    # Immutable event — NO PII (name/mobile/email live only on prospect/lead).
    transaction.on_commit(
        lambda: Event.objects.create(
            tenant=tenant,
            event_type=vocab.LEAD_CAPTURED,
            source=vocab.SRC_FORM,
            referral=referral,
            user_type="prospect",
            person_ref_id=prospect.pk,
            metadata={},
        )
    )

    # Fire the three lead-time WATI notifications (M5) — deduped, opt-in-aware,
    # behind ENABLE_WATI_SEND (log-only in demo). on_commit so the send is enqueued
    # only after the lead is durably saved (capture-first).
    referrer_client_id = _referrer_client_id(referral)
    transaction.on_commit(
        lambda: queue_lead_notifications(
            tenant=tenant, referral=referral, prospect=prospect, client_id=referrer_client_id
        )
    )

    # Zoho mirror (M6) — ASYNC. Enqueued on_commit so the form submit never waits on
    # Zoho, and so the task can only ever see a durably-saved lead. A Zoho outage now
    # leaves the lead `pending` for the retry/backfill sweep instead of stranding it
    # local-only. Behind ENABLE_ZOHO_WRITE → log-only adapter in demo (no network).
    transaction.on_commit(lambda: enqueue_upsert(lead.pk))
    return lead


def _referrer_client_id(referral) -> str:
    identity = referral.referral_identity
    return identity.client_id if identity is not None else ""
