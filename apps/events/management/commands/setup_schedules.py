"""Register recurring django-q schedules (idempotent). Run once after deploy.

Schedules:
  - the M4 dirty-day rollup recompute (the async infra that landed in M5);
  - the Zoho WRITE backfill sweep, which re-enqueues leads that never reached Zoho
    (e.g. stranded by an outage) so none is silently left out of the CRM.

In production run `python manage.py qcluster` to execute scheduled jobs; in dev/CI
(Q_CLUSTER sync=True) schedules are inert.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

# name -> (dotted task path, every N minutes)
SCHEDULES = {
    "recompute_rollups": ("apps.events.rollups.recompute_dirty", 5),
    # Every 10 min: frequent enough that a recovered Zoho drains the backlog promptly,
    # sparse enough that a long outage doesn't hammer it. Each sweep is bounded.
    "zoho_backfill_unsynced": ("apps.integrations.zoho.tasks.backfill_unsynced", 10),
    # Hourly: burnt wax-seal nonces past the freshness window are dead weight (a nonce
    # that old already fails the timestamp check), so purging them can't enable a
    # replay — it just stops the table growing forever.
    "zoho_purge_expired_nonces": ("apps.integrations.zoho.waxseal.purge_expired_nonces", 60),
    # Hourly (Fable5 H3): every /r/{id} hit mints a ClickNonce; without a purge the
    # click_nonces table grows unbounded under crawling. Only rows past TTL+grace go.
    "click_purge_expired_nonces": ("apps.events.nonces.purge_expired_nonces", 60),
    # Every 15 min (Fable5 H4): re-poll WATI notifications stranded at ACCEPTED so a
    # delivery that wasn't terminal at first read gets finalized (or expired), not left
    # 'accepted' forever — otherwise the funnel silently under-reports delivery.
    "wati_reconcile_pending": ("apps.integrations.wati.tasks.reconcile_pending_deliveries", 15),
    # Daily: fill Customer names from Zoho Contacts (READ leg) so the Explorer and
    # leaderboard show real referrer names instead of "name not on file" for anyone
    # Zoho knows. Unmatched ClientIds stay honestly nameless; never overwrites.
    "zoho_sync_referrer_names": ("apps.integrations.zoho.tasks.sync_referrer_names", 1440),
}


class Command(BaseCommand):
    help = "Idempotently register recurring django-q schedules (rollups + Zoho backfill)."

    def handle(self, *args, **options):
        from django_q.models import Schedule
        from django_q.tasks import schedule

        for name, (func, minutes) in SCHEDULES.items():
            if Schedule.objects.filter(name=name).exists():
                self.stdout.write(self.style.WARNING(f"Schedule '{name}' already exists — no-op."))
                continue
            schedule(func, name=name, schedule_type=Schedule.MINUTES, minutes=minutes)
            self.stdout.write(self.style.SUCCESS(f"Scheduled '{name}' every {minutes} minutes."))
