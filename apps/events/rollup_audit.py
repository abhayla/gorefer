"""Detection: accounts_opened rollup drifting from the live Conversion count.

The dashboard's accounts-opened KPI reads the rollups (Daily/MonthlyMetric), which the
dirty-day worker only refreshes for days something marked dirty. Any write that skips its
mark (or any other cause of drift) is invisible there until a full recompute. One drift
(28 vs 30) was seen on prod on 2026-11-04; its cause is unexplained. This check compares,
per (tenant, program), the rollup totals with the source of truth they are built from: the
count of non-reversed Conversions that carry an open date (the exact predicate of
`rollups._accounts_opened_for_range`). Any difference is drift.

Used by `manage.py check_rollup_conversions` (exit 1 on drift) and by the daily
`rollup_conversion_audit` schedule (alerts the owner via the shared Notifier gateway).
"""
from __future__ import annotations

import logging

from django.db.models import Count, Sum

logger = logging.getLogger("gorefer.rollup_audit")


def find_drift(*, recompute: bool = True) -> list[dict]:
    """Return one dict per (tenant, program) whose rollup totals differ from the live
    Conversion count. `recompute=True` first drains pending dirty days, so a mark that
    simply has not been processed yet is not reported as drift."""
    from apps.events.models import DailyMetric, MonthlyMetric
    from apps.events.rollups import recompute_dirty
    from apps.integrations.models import Conversion

    if recompute:
        recompute_dirty()

    live = {
        (r["tenant_id"], r["program_id"]): r["n"]
        for r in Conversion.objects.filter(is_reversed=False, account_opened_at__isnull=False)
        .values("tenant_id", "program_id").annotate(n=Count("id"))
    }
    monthly = {
        (r["tenant_id"], r["program_id"]): r["n"] or 0
        for r in MonthlyMetric.objects.values("tenant_id", "program_id")
        .annotate(n=Sum("accounts_opened"))
    }
    daily = {
        (r["tenant_id"], r["program_id"]): r["n"] or 0
        for r in DailyMetric.objects.values("tenant_id", "program_id")
        .annotate(n=Sum("accounts_opened"))
    }
    drift = []
    for key in sorted(set(live) | set(monthly) | set(daily), key=str):
        row = {
            "tenant_id": key[0], "program_id": key[1],
            "conversions": live.get(key, 0),
            "monthly_total": monthly.get(key, 0),
            "daily_total": daily.get(key, 0),
        }
        if not (row["conversions"] == row["monthly_total"] == row["daily_total"]):
            drift.append(row)
    return drift


def format_drift(drift: list[dict]) -> str:
    return "\n".join(
        "tenant={tenant_id} program={program_id} conversions={conversions} "
        "monthly_total={monthly_total} daily_total={daily_total}".format(**d)
        for d in drift
    )


def scheduled_audit() -> dict:
    """Daily schedule entry: run the check; on drift, alert the owner (never raises)."""
    drift = find_drift()
    if not drift:
        logger.info("rollup audit: accounts_opened matches live conversions")
        return {"drift": []}
    body = format_drift(drift)
    logger.warning("rollup audit DRIFT:\n%s", body)
    try:
        from django.utils import timezone

        from apps.common.notify_owner import notify

        result = notify(
            project="gorefer", severity="P1",
            title="GoRefer: accounts-opened rollup differs from live conversions",
            body=body + "\nFix: python manage.py recompute_rollups; then find what wrote "
                        "or changed a Conversion without marking its day dirty.",
            type="error",
            dedupeKey=f"rollup-drift-{timezone.localdate().isoformat()}",
        )
    except Exception as exc:  # an alert failure must never fail the job
        result = {"ok": False, "error": str(exc)}
    return {"drift": drift, "notify": result}
