"""Detection + self-heal: accounts_opened rollup drifting from the live Conversion count.

Compares the accounts_opened rollup totals (Daily + Monthly) with the count of
non-reversed Conversions that carry an open date, per tenant/program. On drift it marks
every live conversion's IST open day of that tenant/program dirty, recomputes and
re-checks, printing before/after.

Exit 0: no drift. Exit 1: drift was found (the output says HEALED or STILL DRIFTING).

    python manage.py check_rollup_conversions                 # drain dirty days, check, heal
    python manage.py check_rollup_conversions --no-heal       # report only
    python manage.py check_rollup_conversions --no-recompute --no-heal   # pure read
"""
from __future__ import annotations

import sys

from django.core.management.base import BaseCommand

from apps.events.rollup_audit import format_drift, run_audit


class Command(BaseCommand):
    help = "Exit 1 if the accounts_opened rollup differs from the live Conversion count (heals it)."

    def add_arguments(self, parser):
        parser.add_argument("--no-recompute", action="store_true",
                            help="Do not drain pending dirty days before checking.")
        parser.add_argument("--no-heal", action="store_true",
                            help="Report drift without marking days dirty / recomputing.")

    def handle(self, *args, **options):
        result = run_audit(recompute=not options["no_recompute"], do_heal=not options["no_heal"])
        if not result["before"]:
            self.stdout.write("OK: accounts_opened rollup matches live conversions")
            return
        self.stdout.write("DRIFT (before):")
        self.stdout.write(format_drift(result["before"]))
        if result["after"] is None:
            self.stdout.write("not healed (--no-heal)")
        elif result["healed"]:
            self.stdout.write("HEALED: all tenants/programs match after recompute")
        else:
            self.stdout.write("STILL DRIFTING (after heal):")
            self.stdout.write(format_drift(result["after"]))
        sys.exit(1)
