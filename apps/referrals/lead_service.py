"""Lead capture service (M3) — capture-FIRST (06-API §5.3).

On "Continue to Zerodha": save the lead to GoRefer FIRST (Prospect + Lead + a
`lead_captured` event), THEN (M6) mirror to Zoho. In Sprint 1 the Zoho write stays
behind ENABLE_ZOHO_WRITE=false — the adapter logs the intended call in demo mode
and the request still succeeds because the lead is safely captured locally.

Guardrails:
  - Account/reward STATUS is never set here — that comes only from Zoho (M6).
  - PII (name/mobile/email/city) lives on the erasable Prospect/Lead, never in the
    immutable event log.
  - Phone normalized one canonical way via the shared helper.
"""
from __future__ import annotations

import logging

from django.db import transaction

from apps.common.phone import normalize_phone
from apps.events import vocab
from apps.events.models import Event
from apps.integrations.base import LogOnlyZohoAdapter
from apps.integrations.wati.notify import queue_lead_notifications
from apps.referrals.models import Lead, Prospect, Referral
from gorefer.flags import flags

logger = logging.getLogger("gorefer.leads")


@transaction.atomic
def capture_lead(*, tenant, referral: Referral, name: str, mobile: str, email: str, city: str,
                 consent: bool, submitted_by: str = "friend") -> Lead:
    """Persist the prospect + lead in GoRefer (capture-first), emit lead_captured.

    Idempotent-ish: an existing live lead for the same (referral, normalized mobile)
    is returned unchanged rather than duplicated.
    """
    canonical_mobile = normalize_phone(mobile)

    prospect, _ = Prospect.objects.get_or_create(
        tenant=tenant,
        mobile=canonical_mobile,
        defaults={"name": name, "email": email, "city": city, "lead_source": "landing"},
    )

    existing = Lead.objects.filter(
        tenant=tenant, referral=referral, prospect=prospect, deleted_at__isnull=True
    ).first()
    if existing is not None:
        return existing

    lead = Lead.objects.create(
        tenant=tenant,
        referral=referral,
        prospect=prospect,
        status="new",
        submitted_by=submitted_by,
        consent=consent,
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

    # Zoho mirror (M6). Behind the flag → log-only in demo mode; request still ok.
    _mirror_to_zoho(lead=lead, prospect=prospect, referral=referral)
    return lead


def _referrer_client_id(referral) -> str:
    identity = referral.referral_identity
    return identity.client_id if identity is not None else ""


def _mirror_to_zoho(*, lead, prospect, referral):
    if not flags.ENABLE_ZOHO_WRITE:
        LogOnlyZohoAdapter().create_lead(
            payload={"lead_id": lead.pk, "referral_id": referral.pk, "mobile": prospect.mobile}
        )
        return
    # Real Zoho adapter lands in M6.
    logger.info("ENABLE_ZOHO_WRITE=true but Zoho adapter is M6 — no-op for now.")
