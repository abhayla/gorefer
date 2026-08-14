"""T-124 W1 — Campaigns admin CRUD view tests (/admin-panel/campaigns).

Covers: staff-only auth gate, create/list/edit a campaign, add/remove/reorder
steps via the HTMX partial endpoints, and that an invalid submission (negative
gap/budget) is rejected with no partial save. Mirrors tests/test_dashboard.py's
admin_client fixture style.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.campaigns.models import DEFAULT_SEND_DAYS_MASK, MessagingCampaign, MessagingCampaignStep
from apps.tenants.resolve import get_bootstrap_tenant


@pytest.fixture
def tenant(db):
    call_command("seed_program")
    return get_bootstrap_tenant()


@pytest.fixture
def admin_client(tenant):
    User = get_user_model()
    User.objects.create_user(
        username="admin@pifs.in", email="admin@pifs.in", password="pw12345!", is_staff=True
    )
    c = Client()
    c.login(username="admin@pifs.in", password="pw12345!")
    return c


@pytest.fixture
def campaign(tenant):
    c = MessagingCampaign.objects.create(
        tenant=tenant, slug="referrer-recurring", name="Referrer recurring nudge", enabled=False,
        max_msgs_per_24h=1, max_msgs_per_72h=1, max_msgs_per_7d=2,
        send_hour_ist=9, send_days_mask=DEFAULT_SEND_DAYS_MASK,
        language_template_map={"en": "gr_platform_gorefer_refrecord_en_2026_08_07"},
    )
    MessagingCampaignStep.objects.create(tenant=tenant, campaign=c, order=1, gap_days_from_previous=3)
    return c


# --- auth gate -----------------------------------------------------------------------


def test_campaigns_list_requires_login(tenant):
    resp = Client().get("/admin-panel/campaigns/")
    assert resp.status_code == 302
    assert "/admin-panel/login/" in resp.headers["Location"]


def test_non_staff_cannot_access_campaigns(tenant):
    User = get_user_model()
    User.objects.create_user(username="joe", password="pw12345!", is_staff=False)
    c = Client()
    c.login(username="joe", password="pw12345!")
    resp = c.get("/admin-panel/campaigns/")
    assert resp.status_code == 302


def test_campaign_edit_requires_login(campaign):
    resp = Client().get(f"/admin-panel/campaigns/{campaign.id}/")
    assert resp.status_code == 302


# --- list + edit ---------------------------------------------------------------------


def test_campaigns_list_renders(admin_client, campaign):
    resp = admin_client.get("/admin-panel/campaigns/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "referrer-recurring" in html
    assert "Referrer recurring nudge" in html


def test_campaigns_list_shows_engine_live_copy(admin_client, campaign):
    resp = admin_client.get("/admin-panel/campaigns/")
    html = resp.content.decode()
    assert "messaging engine" in html.lower()
    assert "next release" not in html.lower()


def test_campaign_edit_renders(admin_client, campaign):
    resp = admin_client.get(f"/admin-panel/campaigns/{campaign.id}/")
    assert resp.status_code == 200
    assert b"Referrer recurring nudge" in resp.content


def test_campaign_edit_saves_valid_submission(admin_client, campaign):
    resp = admin_client.post(f"/admin-panel/campaigns/{campaign.id}/", {
        "name": "Renamed campaign",
        "enabled": "on",
        "min_records": "2",
        "activity_window_days": "",
        "exclude_converted": "on",
        "max_msgs_per_24h": "1",
        "max_msgs_per_72h": "1",
        "max_msgs_per_7d": "3",
        "send_hour_ist": "10",
        "send_days": ["1", "2", "3", "4", "5"],
        "anchor_event_key": "record_created",
        "manual_include_mobiles": "",
        "manual_exclude_mobiles": "",
        "lang_code": ["en"],
        "lang_template": ["gr_platform_gorefer_refrecord_en_2026_08_07"],
    })
    assert resp.status_code == 200
    assert b"Campaign saved" in resp.content
    campaign.refresh_from_db()
    assert campaign.name == "Renamed campaign"
    assert campaign.enabled is True
    assert campaign.min_records == 2
    assert campaign.max_msgs_per_7d == 3
    assert campaign.send_hour_ist == 10


def test_campaign_edit_rejects_negative_budget_with_no_partial_save(admin_client, campaign):
    original_name = campaign.name
    resp = admin_client.post(f"/admin-panel/campaigns/{campaign.id}/", {
        "name": "Should not be saved",
        "min_records": "0",
        "activity_window_days": "",
        "max_msgs_per_24h": "-1",  # invalid
        "max_msgs_per_72h": "1",
        "max_msgs_per_7d": "2",
        "send_hour_ist": "9",
        "send_days": ["1"],
        "anchor_event_key": "",
        "manual_include_mobiles": "",
        "manual_exclude_mobiles": "",
    })
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "must be a non-negative whole number" in html
    campaign.refresh_from_db()
    # No partial save: the name (a VALID field in the same submission) must also be
    # unchanged, proving the whole submission was rejected together.
    assert campaign.name == original_name


def test_campaign_edit_rejects_invalid_send_hour(admin_client, campaign):
    resp = admin_client.post(f"/admin-panel/campaigns/{campaign.id}/", {
        "name": campaign.name,
        "min_records": "0",
        "activity_window_days": "",
        "max_msgs_per_24h": "1",
        "max_msgs_per_72h": "1",
        "max_msgs_per_7d": "2",
        "send_hour_ist": "99",  # invalid
        "send_days": ["1"],
        "anchor_event_key": "",
        "manual_include_mobiles": "",
        "manual_exclude_mobiles": "",
    })
    assert resp.status_code == 200
    assert "0-23" in resp.content.decode()
    campaign.refresh_from_db()
    assert campaign.send_hour_ist == 9  # unchanged


# --- step ladder (HTMX partials) ------------------------------------------------------


def test_step_add(admin_client, campaign):
    resp = admin_client.post(f"/admin-panel/campaigns/{campaign.id}/steps/add")
    assert resp.status_code == 200
    assert campaign.steps.count() == 2
    assert list(campaign.steps.order_by("order").values_list("order", flat=True)) == [1, 2]


def test_step_remove_renumbers_remaining_steps(admin_client, tenant, campaign):
    step2 = MessagingCampaignStep.objects.create(
        tenant=tenant, campaign=campaign, order=2, gap_days_from_previous=3
    )
    MessagingCampaignStep.objects.create(tenant=tenant, campaign=campaign, order=3, gap_days_from_previous=3)

    resp = admin_client.post(f"/admin-panel/campaigns/{campaign.id}/steps/{step2.id}/remove")
    assert resp.status_code == 200
    assert campaign.steps.count() == 2
    assert list(campaign.steps.order_by("order").values_list("order", flat=True)) == [1, 2]


def test_step_move_up_swaps_order(admin_client, tenant, campaign):
    step2 = MessagingCampaignStep.objects.create(
        tenant=tenant, campaign=campaign, order=2, gap_days_from_previous=3
    )
    resp = admin_client.post(f"/admin-panel/campaigns/{campaign.id}/steps/{step2.id}/move/up")
    assert resp.status_code == 200
    step2.refresh_from_db()
    assert step2.order == 1


def test_step_update_valid(admin_client, campaign):
    step = campaign.steps.first()
    resp = admin_client.post(f"/admin-panel/campaigns/{campaign.id}/steps/{step.id}/update", {
        "gap_days_from_previous": "5",
        "language": "hi",
        "template_role": "role_x",
        "template_name": "tmpl_x",
        "enabled": "on",
    })
    assert resp.status_code == 200
    step.refresh_from_db()
    assert step.gap_days_from_previous == 5
    assert step.language == "hi"
    assert step.template_role == "role_x"
    assert step.template_name == "tmpl_x"


def test_step_update_rejects_negative_gap_with_no_save(admin_client, campaign):
    step = campaign.steps.first()
    original_gap = step.gap_days_from_previous
    resp = admin_client.post(f"/admin-panel/campaigns/{campaign.id}/steps/{step.id}/update", {
        "gap_days_from_previous": "-2",
        "language": "en",
        "template_role": "",
        "template_name": "",
    })
    assert resp.status_code == 200
    assert "not saved" in resp.content.decode()
    step.refresh_from_db()
    assert step.gap_days_from_previous == original_gap


# --- tenant isolation via CRUD (mirrors tests/test_tenant_isolation.py) ---------------


def test_admin_cannot_edit_another_tenants_campaign_via_url(admin_client, tenant, campaign):
    from apps.tenants.models import Tenant

    other = Tenant.objects.create(slug="rival", name="Rival AP", is_active=True)
    other_campaign = MessagingCampaign.objects.create(
        tenant=other, slug="referrer-recurring", name="Rival's campaign", enabled=False,
        max_msgs_per_24h=1, max_msgs_per_72h=1, max_msgs_per_7d=2, send_hour_ist=9,
        send_days_mask=DEFAULT_SEND_DAYS_MASK,
    )
    # The admin session resolves to the bootstrap tenant (single-tenant Sprint 1
    # request resolution — apps.tenants.resolve.get_current_tenant); a campaign row
    # belonging to a DIFFERENT tenant must 404, not leak.
    resp = admin_client.get(f"/admin-panel/campaigns/{other_campaign.id}/")
    assert resp.status_code == 404
