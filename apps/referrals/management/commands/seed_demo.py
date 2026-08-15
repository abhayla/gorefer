"""Seed demo data (§10) so the funnel/journey/dashboard render without external calls.

Creates a handful of referrers with journeys across the funnel (clicks → landing →
redirect → lead), a partner-direct journey, and recomputes rollups. Deliberately
creates NO account_opened / conversion rows — those originate only in Zoho (M6);
the funnel shows them as 0 / "pending Zoho". Idempotent-ish: safe to re-run (uses
distinct demo client_ids; events are append-only so counts grow on re-run).

Requires `seed_program` first (tenant + program). Demo-only — never for production.

T-130 note: `DEMO_REFERRERS`/`DEMO_CUSTOMERS` ids (RJ4521, DA1707, ...) are
deliberately real-Zerodha-shaped (`validators.ZERODHA_CLIENT_ID_PATTERN`, 6 chars)
and are shared BY DESIGN with the LogOnly read-adapter fixtures inside the Zoho
integration boundary (~15 tests assert the Customer row seeded here and the
fixture Contact returned for the same id agree). Renaming them to a
non-colliding shape would ripple through that test surface for no isolation
benefit, since the real hazard is this command ever running against a database
that also serves live traffic — already forbidden above. Detection instead lives
in the integration boundary's `sweep_customer_name_drift` task, which flags any
of these ids it finds carrying a name that disagrees with Zoho (`demo_seed_shadow`).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.events import vocab
from apps.events.models import Event, VisitorPII
from apps.events.rollups import recompute_dirty
from apps.referrals.models import (
    Customer,
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

# Known-customer names (the Zoho/Customer name source) so the Explorer / leaderboard /
# Referral Profile show a NAME even with Zoho READ off. (first_name, last_name)
DEMO_CUSTOMERS = {
    "RJ4521": ("Rajesh", "Joshi"),
    "DA1707": ("Amit", "Deshpande"),
}

# Per-click enrichment for the featured referrer's Referral Profile Clicks tab —
# distinct city/IP/device/channel per row + one bot row (dimmed, excluded from totals).
# Each dict → one click Event (+ VisitorPII for city/IP). Geo on the Event (country/
# state); city + raw IP on the erasable VisitorPII (never on the immutable Event).
FEATURED_CLICKS = [
    {"vid": "demo-rj-1", "ua": "Mozilla/5.0 (Linux; Android 14) Chrome/126",
     "channel": "WhatsApp", "city": "Pune", "state": "MH", "ip": "49.36.142.18", "bot": False},
    {"vid": "demo-rj-2", "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17) Safari/605",
     "channel": "WhatsApp", "city": "Mumbai", "state": "MH", "ip": "103.21.58.9", "bot": False},
    {"vid": "demo-rj-3", "ua": "Mozilla/5.0 (Windows NT 10.0) Chrome/126",
     "channel": "Direct", "city": "Pune", "state": "MH", "ip": "49.36.142.18", "bot": False},
    {"vid": "demo-rj-4", "ua": "Mozilla/5.0 (Linux; Android 13) Chrome/125",
     "channel": "QR", "city": "Nashik", "state": "MH", "ip": "157.48.203.7", "bot": False},
    {"vid": "demo-rj-bot", "ua": "Googlebot/2.1 (+http://www.google.com/bot.html)",
     "channel": "WhatsApp", "city": "", "state": "", "ip": "66.249.66.1", "bot": True},
]


class Command(BaseCommand):
    help = "Seed demo journeys + events + rollups (no conversions — Zoho-only). Demo only."

    @transaction.atomic
    def handle(self, *args, **options):
        tenant = get_bootstrap_tenant()
        program = ReferralProgram.objects.for_tenant(tenant).filter(status="active").first()
        if program is None:
            self.stderr.write("Run seed_program first.")
            return

        self._seed_customers(tenant, program)
        for client_id, clicks, landing, redirect, lead in DEMO_REFERRERS:
            self._seed_journey(tenant, program, client_id, clicks, landing, redirect, lead)

        self._seed_partner_direct(tenant, program)
        conversions = self._seed_conversions(tenant)
        recomputed = recompute_dirty()
        self.stdout.write(self.style.SUCCESS(
            f"Demo seeded: {len(DEMO_REFERRERS)} referrers + partner-direct; "
            f"{conversions} Zoho-sourced conversion(s); {recomputed} rollup period(s)."
        ))

    def _seed_conversions(self, tenant):
        """Seed demo conversions THROUGH the Zoho ingest path (never an internal
        fabrication) — proving account_opened only ever comes from the Zoho path.
        One on-platform (RJ4521 converts) + one off-platform zero-click (new id)."""
        from apps.integrations import services

        fixtures = [
            {"event_id": "demo-conv-1", "opener_zerodha_account_id": "ZA9001",
             "referrer_client_id": "RJ4521", "opener_name": "Demo Opener 1",
             "status": "Account Opened", "account_opened_at": "2026-06-15T10:00:00"},
            {"event_id": "demo-conv-2", "opener_zerodha_account_id": "ZA9002",
             "referrer_client_id": "GW5500", "opener_name": "Demo Offplatform",
             "status": "Account Opened", "account_opened_at": "2026-05-02T10:00:00"},
        ]
        n = 0
        for fx in fixtures:
            if services.ingest_conversion(tenant=tenant, payload=fx) is not None:
                n += 1
        return n

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
        if client_id == "RJ4521":
            # Featured referrer: distinct, enriched clicks (UA/channel/geo + VisitorPII
            # IP/city) so the Referral Profile Clicks tab renders varied rows + one bot.
            for detail in FEATURED_CLICKS:
                self._ev(
                    tenant, referral, vocab.CLICK, vocab.SRC_CLICK, detail["vid"],
                    confirmed=not detail["bot"], is_bot=detail["bot"], ua=detail["ua"],
                    channel=detail["channel"], state=detail["state"], country="India",
                )
                self._pii(tenant, detail["vid"], detail["ip"], detail["city"])
            # Landing/lead/redirect below stitch to the first human click's visitor id.
            vid = FEATURED_CLICKS[0]["vid"]
        else:
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

    def _seed_customers(self, tenant, program):
        """Seed the known-customer name source (the Zoho/Customer name lookup)."""
        for client_id, (first, last) in DEMO_CUSTOMERS.items():
            Customer.objects.get_or_create(
                tenant=tenant, program=program, client_id=client_id,
                defaults={"partner": program.partner, "first_name": first, "last_name": last},
            )

    def _pii(self, tenant, vid, ip, city):
        """The SEPARATE erasable PII record (raw IP + derived city), keyed by visitor
        id — never on the immutable Event (#16/#17). Powers the profile Clicks tab."""
        VisitorPII.objects.get_or_create(
            tenant=tenant, visitor_id=vid,
            defaults={"raw_ip": ip or None, "city": city or ""},
        )

    def _ev(self, tenant, referral, event_type, source, vid, confirmed=False, *,
            is_bot=False, ua="", channel="", state="", country=""):
        metadata = {"channel": channel} if channel else {}
        Event.objects.create(
            tenant=tenant, event_type=event_type, source=source, referral=referral,
            user_type="anonymous", visitor_id=vid, is_bot=is_bot,
            is_confirmed_human=confirmed, user_agent=ua, state=state, country=country,
            metadata=metadata,
        )
