"""T-124 W1 — seed_messaging_campaigns idempotency."""
from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.campaigns.management.commands.seed_messaging_campaigns import (
    REFERRER_RECURRING_GAP_DAYS,
    REFERRER_RECURRING_SLUG,
    REFERRER_RECURRING_STEP_COUNT,
    REFERRER_RECURRING_TEMPLATE_EN,
)
from apps.campaigns.models import MessagingCampaign, MessagingCampaignStep
from apps.tenants.resolve import get_bootstrap_tenant


@pytest.fixture
def tenant(db):
    call_command("seed_program")
    return get_bootstrap_tenant()


def test_seed_creates_disabled_campaign_with_three_steps(tenant):
    call_command("seed_messaging_campaigns")

    campaign = MessagingCampaign.objects.for_tenant(tenant).get(slug=REFERRER_RECURRING_SLUG)
    assert campaign.enabled is False
    assert campaign.max_msgs_per_24h == 1
    assert campaign.max_msgs_per_72h == 1
    assert campaign.max_msgs_per_7d == 2
    assert campaign.language_template_map == {"en": REFERRER_RECURRING_TEMPLATE_EN}

    steps = list(campaign.steps.order_by("order"))
    assert len(steps) == REFERRER_RECURRING_STEP_COUNT
    assert [s.order for s in steps] == [1, 2, 3]
    assert all(s.gap_days_from_previous == REFERRER_RECURRING_GAP_DAYS for s in steps)


def test_seed_is_idempotent(tenant):
    call_command("seed_messaging_campaigns")
    call_command("seed_messaging_campaigns")

    assert MessagingCampaign.objects.for_tenant(tenant).filter(slug=REFERRER_RECURRING_SLUG).count() == 1
    campaign = MessagingCampaign.objects.for_tenant(tenant).get(slug=REFERRER_RECURRING_SLUG)
    assert MessagingCampaignStep.objects.filter(campaign=campaign).count() == REFERRER_RECURRING_STEP_COUNT


def test_seed_does_not_flip_enabled_once_an_operator_turns_it_on(tenant):
    """Re-running the seed must not silently re-disable a campaign an operator armed."""
    call_command("seed_messaging_campaigns")
    campaign = MessagingCampaign.objects.for_tenant(tenant).get(slug=REFERRER_RECURRING_SLUG)
    campaign.enabled = True
    campaign.save(update_fields=["enabled"])

    call_command("seed_messaging_campaigns")
    campaign.refresh_from_db()
    assert campaign.enabled is True, "re-running the seed must leave an already-armed campaign alone"
