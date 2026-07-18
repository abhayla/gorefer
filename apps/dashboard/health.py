"""Background-worker (django-q qcluster) liveness for the admin topbar.

Fable5 residual: the Zoho retry/backfill, rollup recompute, WATI reconcile, and nonce
purges all run ONLY if the qcluster worker is alive (Q_ASYNC=true + the systemd unit).
If that worker dies, those sweeps silently stop — the exact silent-loss the retry layer
exists to prevent — with nothing on screen to show it. This surfaces it.

Signal: django-q stamps every completed task in the `Success` table (`stopped`), and
advances each `Schedule.next_run`. A live worker running the 5-min rollup schedule
therefore leaves a fresh `Success.stopped` within roughly the shortest schedule
interval; and no `Schedule.next_run` should be far in the past. Either being stale
means the worker is not draining — flag it red.

In sync mode (Q_ASYNC unset — dev/CI/demo) tasks run inline in the request, there is no
separate worker to be alive, and there are no schedules, so liveness is reported as
`unknown` (grey) rather than a false red.
"""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

# How stale the newest completed task may be before we call the worker dead. The
# tightest schedule is the 5-min rollup recompute; allow a couple of missed cycles for
# a heartbeat plus clock skew before alarming.
WORKER_STALE_AFTER = timedelta(minutes=20)


def worker_health() -> dict:
    """Return {'state','last_run','detail'} for the background worker.

    state: 'healthy' | 'stale' | 'unknown'. 'unknown' = sync/inline mode (no worker).
    Never raises — a health probe must not 500 the dashboard it decorates.
    """
    # Sync mode: Q_CLUSTER['sync'] True means tasks run inline; there is no worker.
    if settings.Q_CLUSTER.get("sync", True):
        return {"state": "unknown", "last_run": None, "detail": "inline mode (no worker)"}

    try:
        from django_q.models import Schedule, Success

        now = timezone.now()
        last = (
            Success.objects.order_by("-stopped").values_list("stopped", flat=True).first()
        )
        # A schedule whose next_run is far in the past means the worker isn't advancing
        # it (a live worker reschedules on each run). Compare against the stale window.
        overdue = Schedule.objects.filter(
            next_run__lt=now - WORKER_STALE_AFTER
        ).exists()

        if last is None and not Schedule.objects.exists():
            # Worker configured but nothing has run yet and no schedules registered.
            return {"state": "unknown", "last_run": None, "detail": "no runs yet"}

        fresh = last is not None and last >= now - WORKER_STALE_AFTER
        if fresh and not overdue:
            return {"state": "healthy", "last_run": last, "detail": "recent task completed"}
        # No fresh completion, or a schedule is overdue → worker likely down.
        return {
            "state": "stale",
            "last_run": last,
            "detail": "no recent task run — background worker may be down",
        }
    except Exception:  # pragma: no cover - a health probe never breaks the page
        return {"state": "unknown", "last_run": None, "detail": "unavailable"}
