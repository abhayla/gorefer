"""Dirty-days rollup recompute (#6/#34).

Rollups (DailyMetric/MonthlyMetric) are NOT updated inline. Any add/fix/removal
marks the affected day (and its month) dirty; a worker recomputes exactly those
periods from the raw immutable events — no full rebuild, consistent after
out-of-order/backdated data. Dashboards read the rollups.

mark_dirty() is called by producers (or a signal) when an event lands; recompute
processes the dirty set. account_opened stays source-only (0 until Zoho, M6).
"""
from __future__ import annotations

from django.db import connection, transaction
from django.db.models import Count
from django.utils import timezone

from . import vocab
from .models import DailyMetric, DirtyPeriod, Event, MonthlyMetric

# Map observed funnel event types -> the rollup column they increment. These are
# counted by EVENT timestamp (the observed moment). `accounts_opened` is NOT here:
# it is Zoho-sourced and must be counted by the TRUE account-opening date
# (ADR-017), so it is rolled up from Conversion.account_opened_at separately.
_COLUMN_FOR_EVENT = {
    vocab.LINK_CREATED: "links_created",
    vocab.CLICK: "clicks",
    vocab.LANDING_VIEWED: "landing_views",
    vocab.REDIRECT_COMPLETED: "redirects",
    vocab.LEAD_CAPTURED: "leads",
}


def _accounts_opened_for_range(*, tenant, program, start, end):
    """Count Zoho conversions by their TRUE account-opening date (ADR-017), not the
    import/event date — so a backdated conversion lands in its real period."""
    from apps.integrations.models import Conversion

    return Conversion.objects.for_tenant(tenant).filter(
        program=program, is_reversed=False,
        account_opened_at__gte=start, account_opened_at__lt=end,
    ).count()


def mark_dirty(*, tenant, program, on_date):
    """Record a day (its month derived) as needing recompute.

    Every call inserts a NEW unprocessed row. Duplicates for the same day are expected
    and harmless: `recompute_dirty` collapses them (one recompute per distinct day)."""
    mark_dirty_ids(
        tenant_id=getattr(tenant, "pk", tenant), program_id=getattr(program, "pk", program),
        on_date=on_date,
    )


def mark_dirty_ids(*, tenant_id, program_id, on_date):
    """`mark_dirty` by primary keys (safe to capture in a `transaction.on_commit`).

    Always INSERTS a fresh row, never reuses an existing unprocessed one: a mark that
    arrives while `recompute_dirty` is between counting the day and closing its rows
    would otherwise ride on a row the worker is about to close, and be lost. The worker
    closes only the ids it snapshotted before counting, so this new row survives to the
    next run. There is no unique constraint, so duplicates are normal."""
    DirtyPeriod.objects.create(
        tenant_id=tenant_id, program_id=program_id, period_date=on_date,
    )


def _counts_for_range(*, tenant, program, start, end):
    """event_type -> count over [start, end) from raw events (bots + synthetic excluded)."""
    from apps.events.bots import exclude_synthetic

    qs = Event.objects.for_tenant(tenant).filter(
        referral__program=program, is_bot=False,
        timestamp__gte=start, timestamp__lt=end,
    )
    qs = exclude_synthetic(qs)
    return dict(qs.values_list("event_type").annotate(n=Count("id")).values_list("event_type", "n"))


def _recompute_day(*, tenant, program, day):
    start = timezone.make_aware(timezone.datetime(day.year, day.month, day.day))
    end = start + timezone.timedelta(days=1)
    counts = _counts_for_range(tenant=tenant, program=program, start=start, end=end)
    values = {col: counts.get(ev, 0) for ev, col in _COLUMN_FOR_EVENT.items()}
    values["accounts_opened"] = _accounts_opened_for_range(
        tenant=tenant, program=program, start=start, end=end
    )
    DailyMetric.objects.update_or_create(
        tenant=tenant, program=program, metric_date=day, defaults=values
    )


def _recompute_month(*, tenant, program, year, month):
    start = timezone.make_aware(timezone.datetime(year, month, 1))
    end = timezone.make_aware(
        timezone.datetime(year + (month == 12), (month % 12) + 1, 1)
    )
    counts = _counts_for_range(tenant=tenant, program=program, start=start, end=end)
    values = {col: counts.get(ev, 0) for ev, col in _COLUMN_FOR_EVENT.items()}
    values["accounts_opened"] = _accounts_opened_for_range(
        tenant=tenant, program=program, start=start, end=end
    )
    MonthlyMetric.objects.update_or_create(
        tenant=tenant, program=program, year=year, month=month, defaults=values
    )


#: Postgres advisory-lock key serialising every `recompute_dirty` run (arbitrary constant).
RECOMPUTE_LOCK_KEY = 0x67526F6C


def _acquire_recompute_lock(*, wait: bool) -> bool:
    """Transaction-scoped advisory lock: True when held. `wait=False` never blocks."""
    fn = "pg_advisory_xact_lock" if wait else "pg_try_advisory_xact_lock"
    with connection.cursor() as cur:
        cur.execute(f"SELECT {fn}(%s)", [RECOMPUTE_LOCK_KEY])
        row = cur.fetchone()
    return True if wait else bool(row[0])


def recompute_dirty(limit: int | None = None, *, wait: bool = True) -> int:
    """Recompute unprocessed dirty periods (day + its month). Returns rows closed.

    Snapshot the unprocessed row ids FIRST (limit applies to rows), recompute each
    distinct day and each distinct month once, then close ONLY the snapshot ids. A mark
    inserted after the snapshot is a new row, left unprocessed for the next run, so it
    can never be closed without having been counted.

    Runs are SERIALISED by an advisory lock: two overlapping runs (the 5-minute job and a
    dashboard page-load) could otherwise count, then write, in the wrong order and leave
    the older count as final. `wait=False` (dashboard page-load) skips and returns 0 when
    another run holds the lock; its rows stay for that run or the next."""
    with transaction.atomic():
        if not _acquire_recompute_lock(wait=wait):
            return 0
        return _recompute_snapshot(limit)


def _recompute_snapshot(limit: int | None) -> int:
    qs = (
        DirtyPeriod.objects.filter(processed_at__isnull=True)
        .select_related("tenant", "program").order_by("id")
    )
    if limit:
        qs = qs[:limit]
    rows = list(qs)
    if not rows:
        return 0
    days = {}
    months = {}
    for dp in rows:
        days.setdefault((dp.tenant_id, dp.program_id, dp.period_date), dp)
        d = dp.period_date
        months.setdefault((dp.tenant_id, dp.program_id, d.year, d.month), dp)
    for (_t, _p, day), dp in days.items():
        _recompute_day(tenant=dp.tenant, program=dp.program, day=day)
    for (_t, _p, year, month), dp in months.items():
        _recompute_month(tenant=dp.tenant, program=dp.program, year=year, month=month)
    DirtyPeriod.objects.filter(id__in=[dp.id for dp in rows]).update(
        processed_at=timezone.now()
    )
    return len(rows)
