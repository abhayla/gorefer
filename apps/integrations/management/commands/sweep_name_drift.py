"""Report Customer rows whose name disagrees with Zoho's `Referrers`-module name
for the same client_id (T-130).

    python manage.py sweep_name_drift

Read-only — cross-references the already-synced `SyncedReferrer` table (T-126,
sourced from Zoho `Referrers`), so it makes no extra Zoho call. Flags known
`seed_demo` client_ids among the mismatches as demo-seed shadow candidates —
the class of row behind the DA1707/"Amit Deshpande" incident this task exists
for. Correcting a flagged row happens on the next `zoho_sync_referrer_names`
schedule run (T-130 also fixed that job to overwrite drift, not just fill blanks).
"""
from django.core.management.base import BaseCommand

from apps.integrations.zoho.tasks import sweep_customer_name_drift


class Command(BaseCommand):
    help = "Report Customer rows whose name disagrees with Zoho's Referrers-module name."

    def handle(self, *args, **opts):
        result = sweep_customer_name_drift()
        self.stdout.write(f"checked: {result['checked']}  mismatched: {result['mismatched']}")
        for row in result["rows"]:
            flag = " [demo-seed shadow candidate]" if row["demo_seed_shadow"] else ""
            self.stdout.write(
                f"  {row['client_id']}: local={row['local_name']!r} zoho={row['zoho_name']!r}{flag}"
            )
        if result["rows"]:
            self.stdout.write(self.style.WARNING(f"{result['mismatched']} name mismatch(es) found"))
        else:
            self.stdout.write(self.style.SUCCESS("no name drift found"))
