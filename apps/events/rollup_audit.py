"""Detection + self-heal: accounts_opened rollup drifting from the live Conversion count.

The dashboard's accounts-opened KPI reads the rollups (Daily/MonthlyMetric), which the
dirty-day worker only refreshes for days something marked dirty. Any write that skips its
mark (or any other cause of drift) is invisible there until a full recompute. One drift
(28 vs 30) was seen on prod on 2026-11-04; its cause is unexplained. This check compares,
per (tenant, program), the rollup totals with the source of truth they are built from:
the count of non-reversed Conversions that carry an open date (the exact predicate of
`rollups._accounts_opened_for_range`). Any difference is drift.

On drift it HEALS: marks the IST open day of every live conversion of that tenant/program
dirty, recomputes, and re-checks — so the KPI is right again within a day, and the alert
carries before/after numbers for the investigation.

Used by `manage.py check_rollup_conversions` and the daily `rollup_conversion_audit`
schedule (Notifier: P2 "healed", P1 "still drifting" or "audit failed").
"""
from __future__ import annotations

import logging

from django.db.models import Count, Sum

logger = logging.getLogger("gorefer.rollup_audit")


def find_drift(*, recompute: bool = True) -> list[dict]:
    """One dict per (tenant, program) whose rollup totals differ from the live Conversion
    count. `recompute=True` first drains pending dirty days, so a mark that simply has
    not been processed yet is not reported as drift."""
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


def heal(drift: list[dict]) -> list[dict]:
    """Mark the IST open day of every live conversion of each drifting tenant/program
    dirty, recompute, and return the drift that remains (empty = healed)."""
    from django.utils import timezone

    from apps.events.rollups import mark_dirty_ids, recompute_dirty
    from apps.integrations.models import Conversion

    for row in drift:
        opened = Conversion.objects.filter(
            tenant_id=row["tenant_id"], program_id=row["program_id"],
            is_reversed=False, account_opened_at__isnull=False,
        ).values_list("account_opened_at", flat=True)
        for day in {timezone.localtime(ts).date() for ts in opened}:
            mark_dirty_ids(tenant_id=row["tenant_id"], program_id=row["program_id"], on_date=day)
    recompute_dirty()
    return find_drift(recompute=False)


def run_audit(*, recompute: bool = True, do_heal: bool = True) -> dict:
    """{"before": drift, "after": drift left (None when not healed), "healed": bool}."""
    before = find_drift(recompute=recompute)
    if not before or not do_heal:
        return {"before": before, "after": None, "healed": False}
    after = heal(before)
    return {"before": before, "after": after, "healed": not after}


def format_drift(drift: list[dict]) -> str:
    return "\n".join(
        "tenant={tenant_id} program={program_id} conversions={conversions} "
        "monthly_total={monthly_total} daily_total={daily_total}".format(**d)
        for d in drift
    )


def _notify(severity: str, title: str, body: str) -> dict:
    from django.utils import timezone

    from apps.common.notify_owner import notify

    return notify(
        project="gorefer", severity=severity, title=title, body=body, type="error",
        dedupeKey=f"rollup-drift-{severity}-{timezone.localdate().isoformat()}",
    )


def scheduled_audit() -> dict:
    """Daily schedule entry. NEVER raises: any failure is logged and alerted (P1)."""
    try:
        result = run_audit()
        if not result["before"]:
            logger.info("rollup audit: accounts_opened matches live conversions")
            return result
        body = "Before:\n" + format_drift(result["before"])
        if result["healed"]:
            body += "\nAfter heal: all tenants/programs match."
            logger.warning("rollup audit HEALED drift:\n%s", body)
            result["notify"] = _notify(
                "P2", "GoRefer: accounts-opened rollup drift found and healed", body)
        else:
            body += "\nAfter heal (still drifting):\n" + format_drift(result["after"])
            logger.error("rollup audit STILL DRIFTING:\n%s", body)
            result["notify"] = _notify(
                "P1", "GoRefer: accounts-opened rollup still differs after heal", body)
        return result
    except Exception as exc:
        logger.exception("rollup audit failed")
        try:
            _notify("P1", f"GoRefer: rollup audit failed: {type(exc).__name__}", str(exc)[:500])
        except Exception:
            logger.exception("rollup audit: failure alert also failed")
        return {"error": type(exc).__name__}
