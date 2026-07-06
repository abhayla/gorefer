"""Seed the single ReferralProgram (Zerodha row #1) — NOT a schema migration (§8).

Idempotent. Creates, if absent:
  1. the bootstrap tenant (PIFS) + its domain,
  2. the central config baseline (incl. the compliance-locked incentive claim),
  3. the Partner (code from settings.PARTNER_CODE, default ZMPHZC),
  4. the ReferralProgram row (provider-agnostic; Zerodha = row #1),
  5. its ProgramRedirectRule with the server-side destination-URL template.

Provider-agnostic: nothing here is a Zerodha-named table/route. Zerodha is data.
"""
from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.config.models import ConfigCentral
from apps.referrals.models import Partner, ProgramRedirectRule, ReferralProgram
from gorefer.flags import flags

BOOTSTRAP_TENANT_SLUG = "pifs"
DESTINATION_TEMPLATE = "https://signup.zerodha.com/api/lead/?c={partner_code}&r={client_id}"


class Command(BaseCommand):
    help = "Seed the bootstrap tenant, central config, partner, and the single ReferralProgram (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        tenant = self._seed_tenant()
        self._seed_central_config()
        partner = self._seed_partner(tenant)
        program = self._seed_program(tenant, partner)
        self._seed_redirect_rule(tenant, program)
        self.stdout.write(
            self.style.SUCCESS("Seed complete: tenant + config + partner + program + redirect rule.")
        )

    def _seed_tenant(self):
        from apps.tenants.models import Domain, Tenant

        tenant, created = Tenant.objects.get_or_create(
            slug=BOOTSTRAP_TENANT_SLUG,
            defaults={"name": "Passive Income Financial Solutions"},
        )
        # Domain row is only meaningful under django-tenants (Postgres); harmless otherwise.
        Domain.objects.get_or_create(
            domain="gorefer.in", tenant=tenant, defaults={"is_primary": True}
        )
        self.stdout.write(f"  tenant: {'created' if created else 'exists'} ({tenant.slug})")
        return tenant

    def _seed_central_config(self):
        baseline = {
            "referral_incentive_claim": flags.REFERRAL_INCENTIVE_CLAIM,
            "nse_ap_no": getattr(settings, "NSE_AP_NO", ""),
            "sebi_reg_no": "INZ000031633",
            "attribution_window_days": 60,
            # WhatsApp share target = WATI BUSINESS number (NOT Ashok's personal),
            # config-driven via the cascade (ADR-022). Digits only for wa.me.
            "wati_business_number": settings.WATI_BUSINESS_NUMBER,
            "privacy_policy_url": "https://gorefer.in/privacy",
        }
        for key, value in baseline.items():
            ConfigCentral.objects.get_or_create(key=key, defaults={"value": value})
        self.stdout.write("  central config: baseline ensured")

    def _seed_partner(self, tenant):
        partner, created = Partner.objects.get_or_create(
            code=settings.PARTNER_CODE,
            defaults={
                "tenant": tenant,
                "name": "Passive Income Financial Solutions Pvt Ltd",
                "credentials": {"nse_ap_no": getattr(settings, "NSE_AP_NO", "")},
                "website": "https://gorefer.in",
                "status": "active",
            },
        )
        self.stdout.write(f"  partner: {'created' if created else 'exists'} ({partner.code})")
        return partner

    def _seed_program(self, tenant, partner):
        program, created = ReferralProgram.objects.get_or_create(
            tenant=tenant,
            partner=partner,
            name="Zerodha",
            defaults={
                "display_name": "Zerodha",
                "status": "active",
                "reward_description": flags.REFERRAL_INCENTIVE_CLAIM,
                "brand_color": "#387ED1",
                "terms_url": "https://zerodha.com/open-account",
            },
        )
        self.stdout.write(f"  program: {'created' if created else 'exists'} ({program.name})")
        return program

    def _seed_redirect_rule(self, tenant, program):
        rule, created = ProgramRedirectRule.objects.get_or_create(
            program=program,
            priority=100,
            defaults={
                "tenant": tenant,
                "destination_url_template": DESTINATION_TEMPLATE,
                "is_active": True,
            },
        )
        self.stdout.write(f"  redirect rule: {'created' if created else 'exists'}")
        return rule
