"""Rebuild the datacenter/crawler network table from the iptoasn.com dumps.

    python manage.py refresh_network_table                     # download + rebuild
    python manage.py refresh_network_table --source v4.tsv.gz --source v6.tsv.gz   # offline

Keeps only AS ranges matching the `datacenter_network_keywords` cascade key and writes
the table atomically to `network_table_path` (default var/network-ranges.tsv). On any
failure the old table is kept and the command exits non-zero. Also scheduled weekly
(setup_schedules: network_table_refresh).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.events.netranges_refresh import RefreshError, refresh_table


class Command(BaseCommand):
    help = "Rebuild the datacenter network table (iptoasn.com dumps -> var/network-ranges.tsv)."

    def add_arguments(self, parser):
        parser.add_argument("--source", action="append", default=None,
                            help="local ip2asn dump (.tsv or .tsv.gz) instead of downloading; repeatable")
        parser.add_argument("--path", default=None, help="write here instead of network_table_path")

    def handle(self, *args, **options):
        try:
            summary = refresh_table(sources=options.get("source"), path=options.get("path"))
        except RefreshError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Wrote {summary['ranges']} ranges to {summary['path']}"))
        for kw, n in sorted(summary["by_keyword"].items(), key=lambda kv: -kv[1]):
            self.stdout.write(f"  {kw}: {n}")
