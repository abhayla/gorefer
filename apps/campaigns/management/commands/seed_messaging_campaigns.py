"""Seed the first messaging campaign row (idempotent) — T-124 W1.

Owner-approved seed values (plan `~/.claude/plans/i-moved-you-to-silly-sonnet.md`,
decision ⑦ context): slug `referrer-recurring`, DISABLED by default, 3 steps at a
3-day gap each, budgets max_msgs_per_24h=1 / max_msgs_per_72h=1 / max_msgs_per_7d=2,
template `gr_platform_gorefer_refrecord_en_2026_08_07` for language `en`.

This command creates CONFIGURATION only — no sending/scheduling engine reads these
rows yet (W2). Running it twice is a no-op: `get_or_create` on slug means an existing
campaign's fields (including `enabled`, which the /admin-panel/campaigns CRUD page
lets an operator flip) are left exactly as the operator set them — re-running the
seed can never silently re-disable a campaign someone already armed. Steps are
seeded the same way, per (campaign, order).

    python manage.py seed_messaging_campaigns
    python manage.py seed_messaging_campaigns --tenant pifs
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.campaigns.models import (
    DEFAULT_SEND_DAYS_MASK,
    MessagingCampaign,
    MessagingCampaignStep,
)
from apps.tenants.models import Tenant

REFERRER_RECURRING_SLUG = "referrer-recurring"
REFERRER_RECURRING_NAME = "Referrer recurring nudge"
REFERRER_RECURRING_TEMPLATE_EN = "gr_platform_gorefer_refrecord_en_2026_08_07"
REFERRER_RECURRING_STEP_COUNT = 3
REFERRER_RECURRING_GAP_DAYS = 3  # ~72h-equivalent gap per step, expressed as whole days


class Command(BaseCommand):
    help = "Idempotently seed the 'referrer-recurring' messaging campaign (disabled by default)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="pifs", help="Tenant slug (default: pifs).")

    def handle(self, *args, **opts):
        tenant = Tenant.objects.filter(slug=opts["tenant"]).first()
        if tenant is None:
            raise CommandError(f"No tenant with slug '{opts['tenant']}'. Run seed_program first.")

        campaign, created = MessagingCampaign.objects.get_or_create(
            tenant=tenant,
            slug=REFERRER_RECURRING_SLUG,
            defaults=dict(
                name=REFERRER_RECURRING_NAME,
                enabled=False,  # DISABLED by default — an operator opts in explicitly
                min_records=0,
                activity_window_days=None,
                exclude_converted=True,
                manual_include_mobiles=[],
                manual_exclude_mobiles=[],
                max_msgs_per_24h=1,
                max_msgs_per_72h=1,
                max_msgs_per_7d=2,
                send_days_mask=DEFAULT_SEND_DAYS_MASK,
                send_hour_ist=9,
                anchor_event_key="record_created",
                language_template_map={"en": REFERRER_RECURRING_TEMPLATE_EN},
            ),
        )

        step_created = step_skipped = 0
        for order in range(1, REFERRER_RECURRING_STEP_COUNT + 1):
            _, was_created = MessagingCampaignStep.objects.get_or_create(
                tenant=tenant,
                campaign=campaign,
                order=order,
                defaults=dict(
                    gap_days_from_previous=REFERRER_RECURRING_GAP_DAYS,
                    language="en",
                    template_role="referrer_recurring_nudge",
                    template_name="",  # falls back to the campaign's language_template_map
                    enabled=True,
                ),
            )
            step_created += was_created
            step_skipped += not was_created

        status = "created" if created else "already existed — left untouched"
        self.stdout.write(self.style.SUCCESS(
            f"Campaign '{campaign.slug}' for '{tenant.slug}': {status} "
            f"({REFERRER_RECURRING_STEP_COUNT} steps: {step_created} created, "
            f"{step_skipped} already existed)."
        ))
        self.stdout.write(
            "This did NOT enable sending — no engine reads these rows yet (W2). "
            "The campaign is DISABLED; flip it on from /admin-panel/campaigns when the "
            "sending engine ships."
        )
