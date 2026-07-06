"""Seed demo data (§10) so the funnel/journey/dashboard render without external calls.

Creates a handful of referrers with journeys across the funnel (clicks → landing →
redirect → lead), a partner-direct journey, and recomputes rollups. Deliberately
creates NO account_opened / conversion rows — those originate only in Zoho (M6);
the funnel shows them as 0 / "pending Zoho". Idempotent-ish: safe to re-run (uses
distinct demo client_ids; events are append-only so counts grow on re-run).

Requires `seed_program` first (tenant + program). Demo-only — never for production.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.events import vocab
from apps.events.models import Event
from apps.events.rollups import recompute_dirty
from apps.referrals.models import (
    Lead,
    Prospect,
    Referral,
    ReferralIdentity,
    ReferralProgram,
)
from apps.tenants.resolve import get_bootstrap_tenant

# (client_id, clicks, reaches_landing, reaches_redirect, becomes_lead)
DEMO_REFERRERS = [
    ("RJ4521", 4, True, True, True),
    ("DA1707", 2, True, True, False),
    ("MK9033", 5, True, False, False),
    ("SG2210", 1, True, True, True),
]


class Command(BaseCommand):
    help = "Seed demo journeys + events + rollups (no conversions — Zoho-only). Demo only."

    @transaction.atomic
    def handle(self, *args, **options):
        tenant = get_bootstrap_tenant()
        program = ReferralProgram.objects.filter(tenant=tenant, status="active").first()
        if program is None:
            self.stderr.write("Run seed_program first.")
            return

        for client_id, clicks, landing, redirect, lead in DEMO_REFERRERS:
            self._seed_journey(tenant, program, client_id, clicks, landing, redirect, lead)

        self._seed_partner_direct(tenant, program)
        recomputed = recompute_dirty()
        self.stdout.write(self.style.SUCCESS(
            f"Demo seeded: {len(DEMO_REFERRERS)} referrers + partner-direct; {recomputed} rollup period(s). "
            f"No conversions (account_opened stays 0 — Zoho only)."
        ))

    def _seed_journey(self, tenant, program, client_id, clicks, landing, redirect, lead):
        identity, _ = ReferralIdentity.objects.get_or_create(
            tenant=tenant, partner=program.partner, client_id=client_id, id_source="native",
            defaults={"program": program, "status": "active"},
        )
        referral, _ = Referral.objects.get_or_create(
            tenant=tenant, referral_identity=identity, source="referral_link",
            defaults={"program": program, "status": "opened"},
        )
        vid = f"demo-{client_id.lower()}"
        for _ in range(clicks):
            self._ev(tenant, referral, vocab.CLICK, vocab.SRC_CLICK, vid, confirmed=True)
        if landing:
            self._ev(tenant, referral, vocab.LANDING_VIEWED, vocab.SRC_CLICK, vid)
            self._ev(tenant, referral, vocab.HUMAN_CONFIRMED, vocab.SRC_BEACON, vid, confirmed=True)
        if lead:
            prospect, _ = Prospect.objects.get_or_create(
                tenant=tenant, mobile=f"9198765{client_id[-4:]}",
                defaults={"name": f"Demo {client_id}", "lead_source": "landing"},
            )
            Lead.objects.get_or_create(
                tenant=tenant, referral=referral, prospect=prospect,
                defaults={"status": "new", "consent": True},
            )
            self._ev(tenant, referral, vocab.LEAD_CAPTURED, vocab.SRC_FORM, vid)
        if redirect:
            self._ev(tenant, referral, vocab.REDIRECT_COMPLETED, vocab.SRC_REDIRECT, vid)

    def _seed_partner_direct(self, tenant, program):
        referral, _ = Referral.objects.get_or_create(
            tenant=tenant, referral_identity=None, source="partner_direct",
            defaults={"program": program, "status": "opened"},
        )
        self._ev(tenant, referral, vocab.CLICK, vocab.SRC_CLICK, "demo-open", confirmed=True)

    def _ev(self, tenant, referral, event_type, source, vid, confirmed=False):
        Event.objects.create(
            tenant=tenant, event_type=event_type, source=source, referral=referral,
            user_type="anonymous", visitor_id=vid, is_bot=False, is_confirmed_human=confirmed,
            metadata={},
        )
