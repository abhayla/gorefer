"""Management command: compute + write the daily WA engagement report + owner digest (T-032).

Manual trigger for the same code path the `wa_engagement_report_daily` schedule runs
(apps.integrations.wati.engagement.run_report_for_tenant). No-ops per-tenant when
`wa_engagement_report_enabled` is False (the default); with WATI creds absent it
still writes a report, marked degraded, instead of crashing.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.integrations.wati.engagement import run_report_for_tenant
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Compute the daily WhatsApp engagement report and send the owner digest via Notifier."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default=None, help="Tenant slug (default: all active tenants)")
        parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(is_active=True)
        if options.get("tenant"):
            tenants = tenants.filter(slug=options["tenant"])

        results = {}
        for tenant in tenants:
            results[tenant.slug] = run_report_for_tenant(tenant)

        if options.get("json"):
            self.stdout.write(json.dumps(results, default=str))
            return

        for slug, result in results.items():
            if result.get("skipped"):
                self.stdout.write(self.style.WARNING(f"{slug}: skipped ({result['reason']})"))
                continue
            digest_ok = result.get("digest_result", {}).get("ok")
            self.stdout.write(self.style.SUCCESS(
                f"{slug}: report written to {result['report_path']} "
                f"(digest {'sent' if digest_ok else 'FAILED — see logs'})"
            ))
