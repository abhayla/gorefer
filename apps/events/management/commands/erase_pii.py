"""`erase_pii` — fulfil a DPDP erasure request from the shell.

    python manage.py erase_pii --mobile 9876543210 [--visitor-id abc123] [--dry-run]

Sprint 1 erasure is MANUAL on request (ADR-020); this is the sanctioned way to do it, so
nobody has to hand-edit the database. Prints a per-model tally as evidence of what was
actually erased.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.common.privacy import erase_subject
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Erase one person's PII on request (DPDP / ADR-020). Idempotent."

    def add_arguments(self, parser):
        parser.add_argument("--mobile", default=None, help="the subject's mobile (any format)")
        parser.add_argument("--visitor-id", default=None, help="first-party visitor cookie id")
        parser.add_argument("--tenant", default="pifs", help="tenant slug")
        parser.add_argument("--dry-run", action="store_true", help="report without writing")

    def handle(self, *args, **opts):
        if not (opts["mobile"] or opts["visitor_id"]):
            raise CommandError("give --mobile and/or --visitor-id")
        tenant = Tenant.objects.filter(slug=opts["tenant"]).first()
        if tenant is None:
            raise CommandError(f"no tenant with slug {opts['tenant']!r}")

        if opts["dry_run"]:
            # Report WITHOUT writing: erasure is irreversible by design, so an operator
            # must be able to see the blast radius before committing to it.
            from apps.common.phone import normalize_phone
            from apps.common.privacy import dry_run_pii_counts
            from apps.events.models import VisitorPII
            from apps.referrals.models import Prospect

            table_counts = {}
            if opts["mobile"]:
                canonical = normalize_phone(opts["mobile"])
                n_p = Prospect.objects.for_tenant(tenant).filter(mobile=canonical).count()
                table_counts = dry_run_pii_counts(tenant, canonical)
            else:
                n_p = 0
            n_v = (
                VisitorPII.objects.for_tenant(tenant).filter(
                    visitor_id=opts["visitor_id"], erased_at__isnull=True
                ).count()
                if opts["visitor_id"] else 0
            )
            self.stdout.write(f"  DRY RUN — would erase prospects={n_p} visitor_pii={n_v}")
            for key, value in table_counts.items():
                self.stdout.write(f"  DRY RUN — would erase {key}={value}")
            return

        counts = erase_subject(
            tenant, mobile=opts["mobile"], visitor_id=opts["visitor_id"]
        )
        for key, value in counts.items():
            self.stdout.write(f"  {key}: {value}")
        self.stdout.write(self.style.SUCCESS("erasure complete"))
