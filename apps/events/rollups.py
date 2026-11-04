"""Dirty-days rollup recompute (#6/#34).

Rollups (DailyMetric/MonthlyMetric) are NOT updated inline. Any add/fix/removal
marks the affected day (and its month) dirty; a worker recomputes exactly those
periods from the raw immutable events — no full rebuild, consistent after
out-of-order/backdated data. Dashboards read the rollups.

mark_dirty() is called by producers (or a signal) when an event lands; recompute
processes the dirty set. account_opened stays source-only (0 until Zoho, M6).
"""
from __future__ import annotations

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
    """Record a day (its month derived) as needing recompute. Idempotent per day."""
    DirtyPeriod.objects.get_or_create(
        tenant=tenant, program=program, period_date=on_date, processed_at__isnull=True,
        defaults={},
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


def recompute_dirty(limit: int | None = None) -> int:
    """Recompute all unprocessed dirty periods (day + its month). Returns count done."""
    qs = DirtyPeriod.objects.filter(processed_at__isnull=True).order_by("id")
    if limit:
        qs = qs[:limit]
    done = 0
    for dp in list(qs):
        # CLAIM the row before counting, not after. `mark_dirty` is get_or_create on the
        # UNPROCESSED row, so a conversion written while this day was being counted used
        # to find this in-flight row, add nothing, and then be closed out with the stale
        # count. Once claimed, a concurrent mark creates a fresh row the next run picks
        # up. The conditional update also stops two workers recomputing the same row.
        claimed = DirtyPeriod.objects.filter(pk=dp.pk, processed_at__isnull=True).update(
            processed_at=timezone.now()
        )
        if not claimed:
            continue
        try:
            _recompute_day(tenant=dp.tenant, program=dp.program, day=dp.period_date)
            _recompute_month(
                tenant=dp.tenant, program=dp.program,
                year=dp.period_date.year, month=dp.period_date.month,
            )
        except Exception:
            # Un-claim so the day is retried, never silently dropped.
            DirtyPeriod.objects.filter(pk=dp.pk).update(processed_at=None)
            raise
        done += 1
    return done
