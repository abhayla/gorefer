"""Register recurring django-q schedules (idempotent). Run once after deploy.

Schedules the M4 dirty-day rollup recompute on the background queue (the async
infra that landed in M5). In production run `python manage.py qcluster` to execute
scheduled jobs; in dev/CI (Q_CLUSTER sync=True) schedules are inert.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Idempotently register recurring django-q schedules (rollup recompute)."

    def handle(self, *args, **options):
        from django_q.models import Schedule
        from django_q.tasks import schedule

        name = "recompute_rollups"
        if Schedule.objects.filter(name=name).exists():
            self.stdout.write(self.style.WARNING(f"Schedule '{name}' already exists — no-op."))
            return
        schedule(
            "apps.events.rollups.recompute_dirty",
            name=name,
            schedule_type=Schedule.MINUTES,
            minutes=5,
        )
        self.stdout.write(self.style.SUCCESS(f"Scheduled '{name}' every 5 minutes."))
