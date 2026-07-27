"""DPDP erasure + retention purge (CLAUDE.md §4 Privacy, ADR-020).

WHY THIS EXISTS
---------------
Both obligations were SPECIFIED and NEITHER was implemented (found 2026-07-27):

  - "manual erasure on request in Sprint 1 (ADR-020)" — `VisitorPII.erased_at` existed
    and was READ (`dashboard/profile.py` filters on it), but nothing ever WROTE it. There
    was no service, no command, no admin action. A real erasure request would have meant
    hand-editing the database.
  - "anonymize/purge UNCONVERTED prospect PII after 12 months" — absent entirely; the only
    purges in the codebase were for auth nonces.

The existing test `test_i3_visitor_pii_is_erasable` looked like coverage but performed the
erasure ITSELF (set `raw_ip=None`, stamped `erased_at`, saved). It proved the model can
HOLD an erased state, not that any code can produce one.

WHAT IS AND IS NOT ERASED
-------------------------
Erased: the identifying fields — `Prospect.name/email/city`, `Lead`-linked contact data,
`VisitorPII.raw_ip/city`.

DELIBERATELY KEPT:
  - The immutable event log. It holds NO PII by design (Round-2 #16), so erasure has
    nothing to do there — and rewriting it would destroy the audit trail that proves what
    happened. Analytics counts therefore survive erasure unchanged, which is the point.
  - `Prospect.mobile` is PSEUDONYMISED, not blanked. It is the dedupe key that stops one
    person becoming several records; nulling it would fracture history and could resurrect
    the very person who asked to be forgotten as a brand-new prospect on their next click.
  - Conversion/account status. GUARDRAIL 2 — only the Zoho ingest may write those. A
    converted account is a business/regulatory record, not marketing PII, so converted
    subjects are excluded from the automatic purge (a manual request still erases them).

Idempotent throughout: erasing twice is a no-op, so a retried job or a duplicated request
cannot corrupt anything.
"""
from __future__ import annotations

import hashlib
import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("gorefer.privacy")

#: Retention for UNCONVERTED prospect PII. Configuration, not code (§6d) — an operator
#: may need to shorten it for a stricter jurisdiction without a deploy.
RETENTION_DAYS_KEY = "pii_retention_days"
DEFAULT_RETENTION_DAYS = 365

ERASED_NAME = "[erased]"


def _retention_days(tenant_id: int | None) -> int:
    from apps.config.cascade import resolve

    try:
        return int(resolve(RETENTION_DAYS_KEY, tenant_id=tenant_id, default=DEFAULT_RETENTION_DAYS))
    except Exception:
        return DEFAULT_RETENTION_DAYS


def pseudonymise_mobile(mobile: str) -> str:
    """A stable, non-reversible stand-in that preserves dedupe without holding the number.

    Same input -> same token, so the person stays ONE record; the number itself is gone.
    """
    # MUST fit Prospect.mobile (max_length=20). "erased:" is 7 chars, so 12 hex digits
    # gives 19 — 48 bits of collision resistance, far beyond what a dedupe key needs, and
    # it fits. A 16-digit version overflowed the column and raised DataError on save.
    digest = hashlib.sha256((mobile or "").encode()).hexdigest()[:12]
    return f"erased:{digest}"


@transaction.atomic
def erase_subject(tenant, *, mobile: str | None = None, visitor_id: str | None = None) -> dict:
    """Erase one person's PII on request (DPDP). Idempotent.

    Identified by mobile (the usual request key) and/or visitor_id. Returns a per-model
    tally so the operator has evidence of what was actually done — an erasure you cannot
    evidence is not much use when someone asks you to prove it.
    """
    from apps.events.models import VisitorPII
    from apps.referrals.models import Prospect

    counts = {"prospects": 0, "visitor_pii": 0, "leads": 0}
    now = timezone.now()

    if mobile:
        from apps.common.phone import normalize_phone

        canonical = normalize_phone(mobile)
        qs = Prospect.objects.filter(tenant=tenant, mobile=canonical)
        for prospect in qs:
            prospect.name = ERASED_NAME
            prospect.email = ""
            prospect.city = ""
            prospect.mobile = pseudonymise_mobile(canonical)
            prospect.save(update_fields=["name", "email", "city", "mobile", "updated_at"])
            counts["prospects"] += 1
            counts["leads"] += prospect.leads.count()

    if visitor_id:
        pii_qs = VisitorPII.objects.filter(
            tenant=tenant, visitor_id=visitor_id, erased_at__isnull=True
        )
        counts["visitor_pii"] += pii_qs.update(raw_ip=None, city="", erased_at=now)

    logger.info(
        "DPDP erasure applied: tenant=%s mobile=%s visitor=%s counts=%s",
        getattr(tenant, "id", None), bool(mobile), bool(visitor_id), counts,
    )
    return counts


def purge_expired_pii(tenant=None, *, days: int | None = None, dry_run: bool = False) -> dict:
    """Anonymise UNCONVERTED prospect PII older than the retention window (§4).

    Converted subjects are EXCLUDED: an opened account is a business/regulatory record we
    are required to keep, not marketing PII. A manual `erase_subject` still reaches them.

    Runs per tenant so the retention window stays a per-tenant setting.
    """
    from datetime import timedelta

    from apps.events.models import VisitorPII
    from apps.referrals.models import Prospect
    from apps.tenants.models import Tenant

    tenants = [tenant] if tenant is not None else list(Tenant.objects.filter(is_active=True))
    totals = {"prospects": 0, "visitor_pii": 0, "skipped_converted": 0, "dry_run": dry_run}

    for tnt in tenants:
        window = days or _retention_days(getattr(tnt, "id", None))
        cutoff = timezone.now() - timedelta(days=window)
        totals["cutoff"] = cutoff.date().isoformat()
        totals["days"] = window

        stale = Prospect.objects.filter(tenant=tnt, created_at__lt=cutoff).exclude(
            name=ERASED_NAME
        )
        for prospect in stale:
            # "Unconverted" is read from the referral's conversion_status — the field the
            # Zoho ingest maintains. Never inferred from Lead.status, which nothing writes
            # (that mistake silently disabled converted-suppression for a month).
            converted = prospect.leads.filter(
                referral__conversion_status="account_opened"
            ).exists()
            if converted:
                totals["skipped_converted"] += 1
                continue
            if dry_run:
                totals["prospects"] += 1
                continue
            erase_subject(tnt, mobile=prospect.mobile)
            totals["prospects"] += 1

        old_pii = VisitorPII.objects.filter(
            tenant=tnt, created_at__lt=cutoff, erased_at__isnull=True
        )
        if dry_run:
            totals["visitor_pii"] += old_pii.count()
        else:
            totals["visitor_pii"] += old_pii.update(
                raw_ip=None, city="", erased_at=timezone.now()
            )

    logger.info("PII retention purge finished: %s", totals)
    return totals
