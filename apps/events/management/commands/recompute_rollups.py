"""Recompute rollups for all dirty periods (#6/#34).

Run by a scheduled worker in production (django-q/rq later); runnable by hand now.
Idempotent: reprocessing yields the same rollups (recompute-from-raw, not folding).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.events.rollups import recompute_dirty


class Command(BaseCommand):
    help = "Recompute DailyMetric/MonthlyMetric for every unprocessed dirty period."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **options):
        done = recompute_dirty(limit=options.get("limit"))
        self.stdout.write(self.style.SUCCESS(f"Recomputed {done} dirty period(s)."))
