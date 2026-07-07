"""M7 admin dashboard / explorer / journey tests."""
import importlib

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from django.urls import clear_url_caches

import gorefer.urls


@pytest.fixture
def demo(db):
    call_command("seed_program")
    call_command("seed_demo")


@pytest.fixture
def admin_client(demo):
    User = get_user_model()
    User.objects.create_user(
        username="admin@pifs.in", email="admin@pifs.in", password="pw12345!", is_staff=True
    )
    c = Client()
    c.login(username="admin@pifs.in", password="pw12345!")
    return c


# --- auth gate -------------------------------------------------------------

def test_dashboard_requires_login(demo):
    resp = Client().get("/admin-panel/")
    assert resp.status_code == 302
    assert "/admin-panel/login/" in resp.headers["Location"]


def test_non_staff_cannot_access(demo):
    User = get_user_model()
    User.objects.create_user(username="joe", password="pw12345!", is_staff=False)
    c = Client()
    c.login(username="joe", password="pw12345!")
    resp = c.get("/admin-panel/")
    assert resp.status_code == 302  # bounced to login (staff test fails)


# --- dashboard -------------------------------------------------------------

def test_dashboard_renders_kpis_and_funnel(admin_client):
    resp = admin_client.get("/admin-panel/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Referral funnel" in html
    assert "Top referrers" in html
    assert "APPROX" in html          # unique visitors labelled approximate
    assert "FROM ZOHO" in html       # accounts opened Zoho-sourced
    assert "Account opened" in html  # funnel stage


def test_dashboard_accounts_opened_is_zoho_count(admin_client):
    from apps.dashboard.queries import kpis
    from apps.integrations.models import Conversion
    from apps.tenants.resolve import get_bootstrap_tenant

    assert admin_client.get("/admin-panel/").status_code == 200
    # The dashboard's accounts_opened reflects Zoho-sourced conversions (2 in demo).
    k = kpis(get_bootstrap_tenant())
    assert k["accounts_opened"] == Conversion.objects.filter(is_reversed=False).count()
    assert k["accounts_from_zoho"] is True


# --- explorer --------------------------------------------------------------

def test_explorer_renders_and_filters_by_source(admin_client):
    resp = admin_client.get("/admin-panel/explorer/")
    assert resp.status_code == 200
    # partner-direct filter shows the NONE row
    resp2 = admin_client.get("/admin-panel/explorer/?source=partner_direct")
    html = resp2.content.decode()
    assert "— NONE —" in html
    assert "Partner-direct" in html


def test_explorer_shows_off_platform_population(admin_client):
    resp = admin_client.get("/admin-panel/explorer/?source=zoho_import")
    html = resp.content.decode()
    assert "Off-platform" in html


def test_explorer_referrer_column_no_name_marker(admin_client):
    """Referrer column shows 'name not on file' when unknown — never a duplicate of
    the client id (DA polish #3). Demo referrers have no Customer record."""
    html = admin_client.get("/admin-panel/explorer/?source=referral_link").content.decode()
    assert "— name not on file —" in html


@pytest.mark.django_db
def test_explorer_referrer_column_shows_name_when_known():
    from apps.referrals.models import Customer, ReferralProgram
    call_command("seed_program")
    call_command("seed_demo")
    program = ReferralProgram.objects.get()
    Customer.objects.create(
        tenant=program.tenant, program=program, partner=program.partner,
        client_id="RJ4521", first_name="Ramesh", last_name="Kumar", mobile="9998887777",
    )
    User = get_user_model()
    User.objects.create_user(username="a@b.in", password="pw12345!", is_staff=True)
    c = Client()
    c.login(username="a@b.in", password="pw12345!")
    html = c.get("/admin-panel/explorer/?source=referral_link").content.decode()
    assert "Ramesh Kumar" in html  # name shown for the known referrer


# --- journey detail --------------------------------------------------------

def test_journey_detail_shows_timeline_and_conversion(admin_client):
    from apps.referrals.models import Referral
    # RJ4521 has a Zoho conversion in demo.
    ref = Referral.objects.get(referral_identity__client_id="RJ4521", source="referral_link")
    resp = admin_client.get(f"/admin-panel/journey/{ref.id}/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Journey timeline" in html
    assert "Credited referrer" in html
    assert "RJ4521" in html
    assert "Account opened" in html   # true open date row
    assert "zoho" in html             # source shown


# --- PII masking + guardrail #3 -------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_recent_leads_mask_mobile():
    call_command("seed_program")
    User = get_user_model()
    User.objects.create_user(username="a@b.in", password="pw12345!", is_staff=True)
    c = Client()
    # capture a lead so it appears in recent leads
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    c.post("/api/leads/", data={"client_id": "RJ4521", "name": "Rahul", "mobile": "9876543210",
           "consent": True}, content_type="application/json")
    c.login(username="a@b.in", password="pw12345!")
    html = c.get("/admin-panel/").content.decode()
    assert "9876543210" not in html      # full mobile never shown
    assert "•" in html                   # masked form present


def test_dashboard_no_partner_code_or_zerodha_url(admin_client):
    for path in ("/admin-panel/", "/admin-panel/explorer/"):
        html = admin_client.get(path).content.decode()
        assert "ZMPHZC" not in html
        assert "signup.zerodha.com" not in html


# --- no dead UI when flag off ---------------------------------------------

def test_dashboard_routes_absent_when_flag_off(db, settings):
    # When ENABLE_ADMIN_DASHBOARD is off, the routes are not mounted (no dead UI).
    settings.FEATURE_FLAGS = {**settings.FEATURE_FLAGS, "ENABLE_ADMIN_DASHBOARD": False}
    importlib.reload(gorefer.urls)
    clear_url_caches()
    try:
        resp = Client().get("/admin-panel/")
        assert resp.status_code == 404
    finally:
        # restore for other tests
        settings.FEATURE_FLAGS = {**settings.FEATURE_FLAGS, "ENABLE_ADMIN_DASHBOARD": True}
        importlib.reload(gorefer.urls)
        clear_url_caches()
