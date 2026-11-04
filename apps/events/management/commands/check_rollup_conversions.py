"""Detection: accounts_opened rollup drifting from the live Conversion count.

Compares the accounts_opened rollup totals (Daily + Monthly) with the count of
non-reversed Conversions that carry an open date, per tenant/program. Exit 0 when they
match; exit 1 and print every differing tenant/program otherwise.

    python manage.py check_rollup_conversions                 # drains dirty days first
    python manage.py check_rollup_conversions --no-recompute  # read-only comparison
"""
from __future__ import annotations

import sys

from django.core.management.base import BaseCommand

from apps.events.rollup_audit import find_drift, format_drift


class Command(BaseCommand):
    help = "Exit 1 if the accounts_opened rollup differs from the live Conversion count."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-recompute", action="store_true",
            help="Do not drain pending dirty days first (pure read).",
        )

    def handle(self, *args, **options):
        drift = find_drift(recompute=not options["no_recompute"])
        if not drift:
            self.stdout.write("OK: accounts_opened rollup matches live conversions")
            return
        self.stdout.write("DRIFT: accounts_opened rollup differs from live conversions")
        self.stdout.write(format_drift(drift))
        sys.exit(1)
