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
from django.utils import timezone

from apps.common.phone import normalize_phone
from apps.events import vocab
from apps.events.models import Event
from apps.integrations.wati.notify import queue_lead_notifications
from apps.integrations.zoho.adapter import get_zoho_adapter, gorefer_reference_for
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

    # Zoho mirror (M6). Behind the flag → log-only in demo mode; request still ok.
    _mirror_to_zoho(lead=lead, prospect=prospect, referral=referral)
    return lead


def _referrer_client_id(referral) -> str:
    identity = referral.referral_identity
    return identity.client_id if identity is not None else ""


def _mirror_to_zoho(*, lead, prospect, referral):
    """UPSERT the Lead into Zoho (M6 + Model 2), stamping a journey-reference (#10).

    Model 2 (DA 2026-07-15, supersedes DF-9): never a blind create. The adapter
    upserts keyed on the normalized mobile, so Zoho decides create-vs-update
    server-side and a repeat submit UPDATES the same lead instead of twinning it.

    Behind ENABLE_ZOHO_WRITE — log-only in demo. Captures the returned zoho_lead_id
    on the Lead so a later conversion can be joined back. Never sets account status
    (that comes ONLY from the webhook ingest path — guardrail #2).

    A Zoho failure must NOT lose the lead: it is already durably captured locally
    (capture-first, 06-API §5.3), so we log and move on rather than fail the request.
    """
    adapter = get_zoho_adapter()
    gref = gorefer_reference_for(referral)
    try:
        result = adapter.upsert_lead(
            payload={
                "name": prospect.name, "mobile": prospect.mobile, "email": prospect.email,
                "city": prospect.city, "referred_by": _referrer_client_id(referral),
            },
            gorefer_reference=gref,
        )
    except Exception:
        logger.exception(
            "Zoho upsert failed for lead=%s — lead stays captured locally, retry later", lead.pk
        )
        return

    if not result:
        return
    # Persist the journey-reference alongside the id: re-running must never LOSE the
    # reference (#10) — it is what joins a later Zoho conversion back to this journey.
    fields = []
    if result.zoho_lead_id and lead.zoho_lead_id != result.zoho_lead_id:
        lead.zoho_lead_id = result.zoho_lead_id
        fields.append("zoho_lead_id")
    if result.gorefer_reference and lead.gorefer_reference != result.gorefer_reference:
        lead.gorefer_reference = result.gorefer_reference
        fields.append("gorefer_reference")
    if fields:
        lead.save(update_fields=[*fields, "updated_at"])
