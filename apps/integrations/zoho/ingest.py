"""Zoho conversion ingest — the truth layer (M6). THE ONLY writer of conversion
status (guardrail #2).

ingest_conversion(payload) mirrors Zoho as-mapped:
  - idempotency guard (#8): dedupe by the Zoho event id (or composite) — a repeat
    delivery is a no-op.
  - referrer credited by Zerodha CLIENT ID (#10) — NOT mobile.
  - opener upserted by Zerodha ACCOUNT ID (fallback zoho_lead_id, #11) — one
    account never becomes two.
  - off-platform zero-click conversion auto-creates the referral/journey with
    source=zoho_import (#7, ADR-016) — a conversion can exist with zero clicks.
  - explicit Zoho-status → stage map (#12); account_opened is the default terminal;
    reward only if Zoho signals it (no amounts).
  - TRUE account-opening date stored (ADR-017); analytics run off it.
  - removals propagate: a reversal payload sets is_reversed + emits
    conversion_removed + dirties the affected day/month rollups (#6).
  - every status change carries a source/origin tag (#18).

NOTHING here is called by internal business flows — only by the webhook receiver
(and fixtures fed through the same path). No internal code advances a stage.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.events import vocab
from apps.events.models import Event
from apps.events.rollups import mark_dirty
from apps.integrations.models import Conversion, ZohoSyncIdempotency
from apps.referrals.models import Referral, ReferralIdentity, ReferralProgram

from . import statusmap

logger = logging.getLogger("gorefer.zoho.ingest")

SOURCE = "zoho"


class DuplicateDelivery(Exception):
    """The payload was already processed (idempotency guard)."""


def _dedupe_key(payload: dict) -> str:
    if payload.get("event_id"):
        return f"evt:{payload['event_id']}"
    # composite fallback: account + referrer + date
    return "cmp:{}:{}:{}".format(
        payload.get("opener_zerodha_account_id", ""),
        payload.get("referrer_client_id", ""),
        payload.get("account_opened_at", ""),
    )


def _active_program(tenant) -> ReferralProgram:
    qs = ReferralProgram.objects.filter(status="active", deleted_at__isnull=True)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    return qs.order_by("id").first()


def _find_or_autocreate_referral(tenant, program, referrer_client_id: str) -> Referral | None:
    """Resolve the credited referrer's journey; auto-create (zoho_import) if none.

    Off-platform conversion (zero GoRefer clicks) → lazily create the referrer
    identity + a source=zoho_import referral (#7/ADR-016). If Zoho names no
    referrer, credit NO ONE (return None) — never guess.
    """
    if not referrer_client_id:
        return None
    identity = ReferralIdentity.objects.filter(
        tenant=tenant, client_id=referrer_client_id, id_source="native"
    ).first()
    referral = None
    if identity is not None:
        referral = identity.referrals.order_by("id").first()
    if referral is not None:
        return referral
    # Auto-create the off-platform journey (zero clicks).
    if identity is None:
        identity = ReferralIdentity.objects.create(
            tenant=tenant, partner=program.partner, program=program,
            client_id=referrer_client_id, id_source="native", status="active",
        )
    return Referral.objects.create(
        tenant=tenant, referral_identity=identity, program=program,
        source="zoho_import", status="opened",
    )


@transaction.atomic
def ingest_conversion(*, tenant, payload: dict) -> Conversion | None:
    """Ingest one Zoho conversion/status update. Idempotent. Returns the Conversion.

    A reversal payload (`reversed: true`) tombstones the matching conversion.
    """
    key = _dedupe_key(payload)
    # Idempotency guard (#8): check-before-apply.
    _idem, created = ZohoSyncIdempotency.objects.get_or_create(
        tenant=tenant, dedupe_key=key, defaults={"result": "pending"}
    )
    if not created and _idem.processed_at is not None:
        raise DuplicateDelivery(key)

    program = _active_program(tenant)
    account_id = payload.get("opener_zerodha_account_id", "") or ""
    zoho_lead_id = payload.get("zoho_lead_id", "") or ""
    referrer_client_id = payload.get("referrer_client_id", "") or ""

    # Resolve/upsert the conversion by opener account id (fallback zoho_lead_id).
    conversion = _get_conversion(tenant, account_id, zoho_lead_id)

    if payload.get("reversed"):
        result = _apply_reversal(tenant, program, conversion, payload)
    else:
        result = _apply_upsert(
            tenant, program, conversion, payload, account_id, zoho_lead_id, referrer_client_id
        )

    _idem.processed_at = timezone.now()
    _idem.result = "ok"
    _idem.save(update_fields=["processed_at", "result"])
    return result


def _get_conversion(tenant, account_id, zoho_lead_id) -> Conversion | None:
    qs = Conversion.objects.filter(tenant=tenant)
    if account_id:
        row = qs.filter(opener_zerodha_account_id=account_id).first()
        if row:
            return row
    if zoho_lead_id:
        return qs.filter(zoho_lead_id=zoho_lead_id).first()
    return None


def _apply_upsert(tenant, program, conversion, payload, account_id, zoho_lead_id, referrer_client_id):
    stage = statusmap.map_zoho_status(payload.get("status", "account opened")) or "account_opened"
    referral = _find_or_autocreate_referral(tenant, program, referrer_client_id)
    open_dt = _parse_dt(payload.get("account_opened_at"))
    now = timezone.now()

    if conversion is None:
        conversion = Conversion(tenant=tenant, program=program)
    conversion.opener_zerodha_account_id = account_id
    conversion.zoho_lead_id = zoho_lead_id
    conversion.opener_name = payload.get("opener_name") or ""
    conversion.referrer_client_id = referrer_client_id
    conversion.referral = referral
    conversion.status = stage
    conversion.account_opened_at = open_dt
    conversion.reward_status = payload.get("reward_status") or ""  # only if Zoho signals
    conversion.source_origin = SOURCE
    conversion.status_changed_at = now
    conversion.is_reversed = False
    conversion.synced_at = now
    conversion.save()

    # Mirror onto the referral (Zoho-sourced only). Never advance internally.
    if referral is not None:
        referral.conversion_status = stage
        referral.conversion_source = SOURCE
        referral.credited_referrer = referrer_client_id
        referral.reward_status = conversion.reward_status
        referral.account_opened_at = open_dt
        referral.conversion_synced_at = now
        if stage == statusmap.TERMINAL_ACCOUNT_STAGE:
            referral.status = "confirmed"
        referral.save(update_fields=[
            "conversion_status", "conversion_source", "credited_referrer", "reward_status",
            "account_opened_at", "conversion_synced_at", "status", "updated_at",
        ])
        _emit_conversion_events(tenant, referral, stage, conversion, open_dt)
    return conversion


def _apply_reversal(tenant, program, conversion, payload):
    """A removed/de-mapped conversion → tombstone (is_reversed) + conversion_removed
    event + dirty the affected day/month. Audit retained (row not deleted)."""
    if conversion is None:
        return None
    conversion.is_reversed = True
    conversion.status_changed_at = timezone.now()
    conversion.source_origin = SOURCE
    conversion.save(update_fields=["is_reversed", "status_changed_at", "source_origin", "updated_at"])

    referral = conversion.referral
    if referral is not None:
        Event.objects.create(
            tenant=tenant, event_type=vocab.CONVERSION_REMOVED, source=vocab.SRC_ZOHO,
            referral=referral, user_type="system",
            metadata={"account": conversion.opener_zerodha_account_id},
        )
        # Un-mirror onto the referral — but ONLY when this was its LAST live conversion.
        #
        # The forward path above mirrors conversion state onto the Referral; the reversal
        # used to tombstone the Conversion and stop there, leaving the Referral still
        # reading conversion_status="account_opened" with the referrer still credited and
        # zero live conversions behind it. Demonstrated live 2026-07-26 on referral 17:
        # the referrer stayed credited, the dashboard still showed a conversion, and
        # `followups.services.has_converted()` kept returning True, so the prospect was
        # permanently suppressed from follow-ups over a conversion Zoho had de-mapped.
        #
        # Conditional because a referral may carry several conversions (referral 1 has a
        # live ZA9001 plus a reversed row) — reversing one must not un-credit a referral
        # that is still legitimately converted by another.
        still_live = Conversion.objects.filter(referral=referral, is_reversed=False).exists()
        if not still_live:
            referral.conversion_status = ""
            referral.credited_referrer = ""
            referral.reward_status = ""
            referral.account_opened_at = None
            referral.conversion_source = SOURCE  # Zoho remains the source of the change
            referral.conversion_synced_at = timezone.now()
            referral.status = "opened"  # back to an in-progress journey, not "confirmed"
            referral.save(update_fields=[
                "conversion_status", "credited_referrer", "reward_status", "account_opened_at",
                "conversion_source", "conversion_synced_at", "status", "updated_at",
            ])
        # Recompute the affected period off the TRUE open date, in IST.
        #
        # `.date()` alone is a TRAP here (P0-H). `account_opened_at` is IST midnight stored
        # as UTC — 1 Aug 2026 IST is `2026-07-31T18:30Z` — so `.date()` yields the UTC date
        # (31 Jul) and would mark the WRONG MONTH dirty, leaving the right month never
        # recomputed. It happens to be correct on THIS path only because the value still
        # carries its parsed IST offset in-memory; the moment a Conversion is re-read from
        # the DB (the reconciler, any backfill) `.date()` flips to the UTC date. Verified by
        # probe: in-memory `.date()` -> 2026-08-01, after `refresh_from_db()` -> 2026-07-31.
        # `localtime()` is correct regardless of how the value was obtained.
        if conversion.account_opened_at:
            mark_dirty(
                tenant=tenant, program=program,
                on_date=timezone.localtime(conversion.account_opened_at).date(),
            )
    return conversion


def _emit_conversion_events(tenant, referral, stage, conversion, open_dt):
    """Emit account_opened (and reward) events — source-tagged, dated to TRUE open
    date so rollups land in the real period (no fake day-1 spike)."""
    if stage == statusmap.TERMINAL_ACCOUNT_STAGE:
        Event.objects.create(
            tenant=tenant, event_type=vocab.ACCOUNT_OPENED, source=vocab.SRC_ZOHO,
            referral=referral, user_type="system",
            metadata={"account": conversion.opener_zerodha_account_id},
        )
        if open_dt:
            # IST date, not `.date()` — see the P0-H note in apply_conversion above.
            mark_dirty(
                tenant=tenant, program=referral.program,
                on_date=timezone.localtime(open_dt).date(),
            )
    if conversion.reward_status:  # only if Zoho supplied a reward signal
        Event.objects.create(
            tenant=tenant, event_type=vocab.REWARD_STATUS_CHANGED, source=vocab.SRC_ZOHO,
            referral=referral, user_type="system",
            metadata={"reward_status": conversion.reward_status},  # never an amount
        )


def _parse_dt(raw):
    if not raw:
        return None
    from django.utils.dateparse import parse_datetime

    dt = parse_datetime(raw) if isinstance(raw, str) else raw
    if dt is not None and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt
