"""Re-flag past datacenter/crawler-network VISITS as bots (history repair).

Every is_bot=False event of a datacenter visit (click, landing_viewed, human_confirmed...)
is flagged; clicks with no linked VisitorPII IP are skipped and counted.

    python manage.py reclassify_datacenter_clicks                 # DRY RUN (default): counts only
    python manage.py reclassify_datacenter_clicks --apply         # write is_bot=True + metadata
    python manage.py reclassify_datacenter_clicks --tenant pifs --table /path/network-ranges.tsv

Idempotent; never touches VisitorPII; marks affected rollup days dirty (the 5-minute
recompute_rollups schedule then rebuilds them). Refuses to run without a table, so a
missing table can never be mistaken for "0 datacenter clicks".
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.events import netranges
from apps.events.reclassify import reclassify_datacenter_clicks
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Re-flag historical datacenter-network clicks as bots (dry-run unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
        parser.add_argument("--tenant", default=None, help="tenant slug (default: all)")
        parser.add_argument("--table", default=None, help="table file (default: network_table_path)")

    def handle(self, *args, **opts):
        path = opts["table"] or netranges.table_path()
        table = netranges.load_table(path)
        if table is None or len(table) == 0:
            raise CommandError(f"network table missing or empty at {path}; run refresh_network_table first")
        tenant = None
        if opts["tenant"]:
            tenant = Tenant.objects.filter(slug=opts["tenant"]).first()
            if tenant is None:
                raise CommandError(f"unknown tenant {opts['tenant']!r}")
        r = reclassify_datacenter_clicks(table, tenant=tenant, apply=opts["apply"])
        mode = "APPLY" if r["applied"] else "DRY RUN (no writes; pass --apply)"
        w = self.stdout.write
        w(f"{mode} - table {path} ({len(table)} ranges)")
        w(f"  human clicks scanned: {r['scanned_clicks']}")
        w(f"  skipped (no linked IP): {r['skipped_no_linked_ip']}")
        w(f"  datacenter clicks: {r['datacenter_clicks']}")
        w(f"  datacenter visitors: {r['datacenter_visitors']}")
        for kind, n in sorted(r["by_kind"].items()):
            w(f"    {kind}: {n}")
        w("  by network:")
        for org, n in r["by_network"].items():
            w(f"    {n:5d}  {org}")
        w("  events to flag, by event_type (the whole datacenter visit):")
        for et, n in r["by_event_type"].items():
            w(f"    {et}: {n}")
        w(f"  stay human: {r['remaining_human_by_kind']}")
        if r["applied"]:
            w(f"  events written: {r['events_written']}")
            w(f"  rollup days marked dirty: {r['dirty_days']}")
        self.stdout.write(self.style.SUCCESS("done"))
