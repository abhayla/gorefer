"""T-124 W1 — MessagingCampaign / MessagingCampaignStep model tests.

Covers: unique slug per tenant, unique order per campaign, negative gap/budget
rejection, and tenant scoping via `.for_tenant()` (mirrors
tests/test_tenant_isolation.py's two-tenant probe style).
"""
from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction

from apps.campaigns.models import (
    DEFAULT_SEND_DAYS_MASK,
    MONDAY,
    SATURDAY,
    SUNDAY,
    MessagingCampaign,
    MessagingCampaignStep,
    days_from_mask,
    days_mask_from_codes,
)
from apps.tenants.models import Tenant
from apps.tenants.resolve import get_bootstrap_tenant


@pytest.fixture
def tenant(db):
    call_command("seed_program")
    return get_bootstrap_tenant()


@pytest.fixture
def other_tenant(tenant):
    return Tenant.objects.create(slug="rival", name="Rival AP", is_active=True)


def _campaign(tenant, **overrides):
    defaults = dict(
        tenant=tenant,
        slug="referrer-recurring",
        name="Referrer recurring nudge",
        enabled=False,
        max_msgs_per_24h=1,
        max_msgs_per_72h=1,
        max_msgs_per_7d=2,
        send_hour_ist=9,
        send_days_mask=DEFAULT_SEND_DAYS_MASK,
        language_template_map={"en": "gr_platform_gorefer_refrecord_en_2026_08_07"},
    )
    defaults.update(overrides)
    return MessagingCampaign.objects.create(**defaults)


# --- uniqueness --------------------------------------------------------------------


def test_slug_unique_per_tenant(tenant):
    _campaign(tenant)
    with pytest.raises(IntegrityError), transaction.atomic():
        _campaign(tenant)


def test_same_slug_allowed_across_tenants(tenant, other_tenant):
    _campaign(tenant)
    # Must not raise — the uniqueness is (tenant, slug), not slug alone.
    _campaign(other_tenant)
    assert MessagingCampaign.objects.filter(slug="referrer-recurring").count() == 2


def test_step_order_unique_per_campaign(tenant):
    campaign = _campaign(tenant)
    MessagingCampaignStep.objects.create(
        tenant=tenant, campaign=campaign, order=1, gap_days_from_previous=3
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        MessagingCampaignStep.objects.create(
            tenant=tenant, campaign=campaign, order=1, gap_days_from_previous=5
        )


def test_same_order_allowed_across_campaigns(tenant):
    c1 = _campaign(tenant, slug="c1")
    c2 = _campaign(tenant, slug="c2")
    MessagingCampaignStep.objects.create(tenant=tenant, campaign=c1, order=1, gap_days_from_previous=3)
    # Must not raise — uniqueness is (campaign, order), not order alone.
    MessagingCampaignStep.objects.create(tenant=tenant, campaign=c2, order=1, gap_days_from_previous=3)


# --- negative values rejected -------------------------------------------------------


def test_negative_gap_rejected_at_db_level(tenant):
    campaign = _campaign(tenant)
    step = MessagingCampaignStep(tenant=tenant, campaign=campaign, order=1, gap_days_from_previous=-1)
    with pytest.raises(ValidationError):
        step.full_clean()


def test_negative_budget_rejected_at_db_level(tenant):
    campaign = MessagingCampaign(
        tenant=tenant, slug="x", name="X", max_msgs_per_24h=-1, max_msgs_per_72h=1, max_msgs_per_7d=2,
        send_hour_ist=9, send_days_mask=DEFAULT_SEND_DAYS_MASK,
    )
    with pytest.raises(ValidationError):
        campaign.full_clean()


def test_send_hour_out_of_range_rejected(tenant):
    campaign = _campaign(tenant, send_hour_ist=99)
    with pytest.raises(ValidationError):
        campaign.clean()


# --- send_days_mask encoding ---------------------------------------------------------


def test_days_mask_round_trips_saturday_only():
    mask = days_mask_from_codes([6])  # Saturday (ISO weekday 6)
    assert mask == SATURDAY
    assert days_from_mask(mask) == [6]


def test_days_mask_supports_arbitrary_combination():
    mask = days_mask_from_codes([1, 7])  # Monday + Sunday
    assert mask == (MONDAY | SUNDAY)
    assert set(days_from_mask(mask)) == {1, 7}


# --- template resolution (decision 15: blank/missing -> English fallback) -----------


def test_template_for_falls_back_to_english(tenant):
    campaign = _campaign(tenant, language_template_map={"en": "tmpl_en"})
    assert campaign.template_for("hi") == "tmpl_en"
    assert campaign.template_for("en") == "tmpl_en"


def test_template_for_returns_empty_when_no_english_default(tenant):
    campaign = _campaign(tenant, language_template_map={})
    assert campaign.template_for("hi") == ""


def test_step_resolved_template_name_overrides_campaign_map(tenant):
    campaign = _campaign(tenant, language_template_map={"en": "tmpl_en"})
    step = MessagingCampaignStep.objects.create(
        tenant=tenant, campaign=campaign, order=1, gap_days_from_previous=3,
        language="en", template_name="tmpl_override",
    )
    assert step.resolved_template_name() == "tmpl_override"

    step2 = MessagingCampaignStep.objects.create(
        tenant=tenant, campaign=campaign, order=2, gap_days_from_previous=3, language="en",
    )
    assert step2.resolved_template_name() == "tmpl_en"


# --- tenant scoping (mirrors tests/test_tenant_isolation.py) ------------------------


def test_for_tenant_scopes_campaigns_across_tenants(tenant, other_tenant):
    mine = _campaign(tenant)
    theirs = _campaign(other_tenant)

    visible_to_a = list(MessagingCampaign.objects.for_tenant(tenant))
    visible_to_b = list(MessagingCampaign.objects.for_tenant(other_tenant))

    assert visible_to_a == [mine]
    assert visible_to_b == [theirs]
    assert mine not in visible_to_b
    assert theirs not in visible_to_a
