"""Reconcile Zoho Contacts account-openings into GoRefer conversions.

    python manage.py reconcile_conversions [--since 2026-07-01] [--dry-run]

Exists because the webhook alone silently delivered nothing for a month — see
`apps/integrations/zoho/reconcile.py` for the two root causes. Safe to run repeatedly:
ingest is idempotent on `event_id`.
"""
from django.core.management.base import BaseCommand

from apps.integrations.zoho.reconcile import reconcile_conversions


class Command(BaseCommand):
    help = "Poll Zoho Contacts for account openings and ingest any GoRefer is missing."

    def add_arguments(self, parser):
        parser.add_argument("--since", default=None, help="ISO date; default from config")
        parser.add_argument("--dry-run", action="store_true", help="Report without writing")

    def handle(self, *args, **opts):
        counts = reconcile_conversions(since=opts["since"], dry_run=opts["dry_run"])
        for key, value in counts.items():
            self.stdout.write(f"  {key}: {value}")
        if counts.get("failed"):
            self.stdout.write(self.style.WARNING("completed with failures — see logs"))
        else:
            self.stdout.write(self.style.SUCCESS("reconcile complete"))
