"""`purge_expired_pii` — the 12-month retention sweep (CLAUDE.md §4).

    python manage.py purge_expired_pii [--days 365] [--dry-run] [--tenant pifs]

Anonymises UNCONVERTED prospect PII past the retention window. Converted subjects are
kept: an opened account is a business/regulatory record, not marketing PII.

Also registered as the scheduled job `pii_retention_purge` (setup_schedules), because a
retention obligation nobody runs is not a retention policy.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.common.privacy import purge_expired_pii
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Anonymise unconverted prospect PII past the retention window (DPDP)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None, help="override the configured window")
        parser.add_argument("--tenant", default=None, help="tenant slug (default: all active)")
        parser.add_argument("--dry-run", action="store_true", help="report without writing")

    def handle(self, *args, **opts):
        tenant = Tenant.objects.filter(slug=opts["tenant"]).first() if opts["tenant"] else None
        counts = purge_expired_pii(tenant, days=opts["days"], dry_run=opts["dry_run"])
        for key, value in counts.items():
            self.stdout.write(f"  {key}: {value}")
        self.stdout.write(self.style.SUCCESS("retention purge complete"))
