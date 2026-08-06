"""Backfill helpers for `Referral` fields that a code fix alone cannot repair —
existing rows created before the fix landed need a one-time (but re-runnable) sweep.
"""
from __future__ import annotations

from django.db.models import Min

from apps.events import vocab
from apps.events.models import Event
from apps.referrals.models import Referral


def backfill_first_click_at(tenant=None, *, dry_run: bool = False) -> dict:
    """Stamp `Referral.first_click_at` for rows that are NULL but have an earlier
    non-bot click Event on record (OQ2).

    Idempotent: only ever touches rows still NULL, via the same conditional
    `.filter(first_click_at__isnull=True).update(...)` the live request-time stamp
    uses (redirect_service._stamp_first_click) — a re-run, or a run against a row
    already stamped since, is always a safe no-op. Bot clicks are excluded
    (`is_bot=False`) so a crawler that happened to arrive first can never poison the
    backfilled value — the same guardrail the live stamp gets for free by only ever
    recording real clicks.
    """
    referrals = Referral.objects.filter(first_click_at__isnull=True)
    if tenant is not None:
        referrals = referrals.for_tenant(tenant)

    candidates = 0
    stamped = 0
    for referral_id in referrals.values_list("pk", flat=True).iterator():
        earliest = Event.objects.filter(
            referral_id=referral_id, event_type=vocab.CLICK, is_bot=False,
        ).aggregate(Min("timestamp"))["timestamp__min"]
        if earliest is None:
            continue
        candidates += 1
        if dry_run:
            continue
        stamped += Referral.objects.filter(
            pk=referral_id, first_click_at__isnull=True
        ).update(first_click_at=earliest)

    return {"candidates": candidates, "stamped": stamped}
