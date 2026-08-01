"""`backfill_first_click_at` — idempotent backfill for `Referral.first_click_at` (OQ2).

    python manage.py backfill_first_click_at [--tenant pifs] [--dry-run]

The live stamping fix (redirect_service._stamp_first_click, PR #52) has correctly
set `first_click_at` on every first click since 2026-07-26. The one-time recovery of
the rows that predated that fix was an ad-hoc, uncommitted, un-repeatable SQL
statement run once by hand — so a row that statement missed, or any row created in a
fresh/restored environment before the fix line existed, stays permanently NULL with
no way to re-run the recovery. This command is that missing, idempotent, re-runnable
path: only touches rows still NULL, so a re-run (or a run against a freshly restored
DB) is always safe and a no-op on anything already stamped.

Only ever set-once semantics apply here too: a referral already carrying a value is
left untouched (`first_click_at__isnull=True` on the update), matching the
`_stamp_first_click` set-once contract at request time.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.referrals.backfill import backfill_first_click_at
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Backfill Referral.first_click_at from the earliest non-bot click Event (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default=None, help="tenant slug (default: all)")
        parser.add_argument("--dry-run", action="store_true", help="report without writing")

    def handle(self, *args, **opts):
        tenant = Tenant.objects.filter(slug=opts["tenant"]).first() if opts["tenant"] else None
        result = backfill_first_click_at(tenant, dry_run=opts["dry_run"])
        self.stdout.write(f"  candidates (first_click_at NULL, has a non-bot click): {result['candidates']}")
        self.stdout.write(f"  stamped: {result['stamped']}")
        msg = "backfill complete" if not opts["dry_run"] else "dry-run complete"
        self.stdout.write(self.style.SUCCESS(msg))
