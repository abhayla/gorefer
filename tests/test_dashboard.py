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


def test_topbar_avatar_dropdown_holds_user_items(admin_client):
    """The avatar dropdown holds the USER items (Preferences, Sign out); the main nav
    keeps only app/data sections (Dashboard, Explorer, Referral Profile)."""
    html = admin_client.get("/admin-panel/").content.decode()
    # accessible dropdown scaffolding
    assert 'id="avatar-menu-btn"' in html
    assert 'aria-haspopup="menu"' in html
    assert 'role="menu"' in html
    assert 'aria-controls="avatar-menu"' in html
    # user items are menuitems inside the dropdown
    assert 'role="menuitem"' in html
    assert "Sign out" in html
    assert "Preferences" in html
    # each user item is rendered as a role=menuitem link (not a bare nav pill)
    import re
    menuitems = re.findall(r'role="menuitem"[^>]*>\s*(?:<span[^>]*>[^<]*</span>\s*)?([A-Za-z ]+)', html)
    joined = " ".join(menuitems)
    assert "Preferences" in joined and "Sign out" in joined
    # main-nav app sections still present
    assert "Dashboard" in html and "Explorer" in html and "Referral Profile" in html
    # no leaked template comment text (the multi-line {# #} gotcha)
    assert "Scrolls horizontally" not in html


def test_topbar_status_is_flag_driven(admin_client):
    """The Zoho/WATI topbar indicators are FLAG-DRIVEN (green On / red Off), two states
    only — NOT activity-based; green does not wait for a real sync/send."""
    from apps.config.cascade import set_tenant
    from apps.config.integration_flags import ENABLE_WATI_SEND, ENABLE_ZOHO_WRITE
    from apps.tenants.resolve import get_current_tenant

    t = get_current_tenant()
    # flags OFF → both show Off (red), never the old "no sync yet" wording
    set_tenant(ENABLE_ZOHO_WRITE, False, tenant_id=t.id)
    set_tenant(ENABLE_WATI_SEND, False, tenant_id=t.id)
    body = admin_client.get("/admin-panel/").content.decode()
    assert "Zoho: <span" in body and "Off" in body
    assert "no sync yet" not in body and "no sends yet" not in body
    assert "bg-danger" in body  # red dot present when off

    # flip a flag ON → that indicator goes green (On), immediately, no activity needed
    set_tenant(ENABLE_ZOHO_WRITE, True, tenant_id=t.id)
    set_tenant(ENABLE_WATI_SEND, True, tenant_id=t.id)
    body = admin_client.get("/admin-panel/").content.decode()
    assert "On" in body
    assert "bg-positive" in body  # green dot present when on


def test_topbar_shows_worker_liveness_indicator(admin_client):
    """The topbar carries a background-worker (qcluster) liveness light so a dead
    worker is visible. In test/sync mode it renders the 'unknown' (—) state, never a
    false red."""
    html = admin_client.get("/admin-panel/").content.decode()
    assert "Worker:" in html
    # Sync/inline mode in tests → unknown state, grey dash (not a false 'Down').
    assert "bg-ink-300" in html
    # Never falsely alarm when there's no worker to be down: the red 'Down' LABEL span
    # must be absent (substring 'Down' also appears in unrelated JS 'ArrowDown').
    assert ">Down<" not in html


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
    # seed_demo already seeds a Customer for RJ4521 (the name source), so its name
    # lights up in the explorer; update it to a distinctive value to assert on.
    from apps.referrals.models import Customer, ReferralProgram
    call_command("seed_program")
    call_command("seed_demo")
    program = ReferralProgram.objects.get()
    Customer.objects.update_or_create(
        tenant=program.tenant, program=program, client_id="RJ4521",
        defaults={"partner": program.partner, "first_name": "Ramesh",
                  "last_name": "Kumar", "mobile": "9998887777"},
    )
    User = get_user_model()
    User.objects.create_user(username="a@b.in", password="pw12345!", is_staff=True)
    c = Client()
    c.login(username="a@b.in", password="pw12345!")
    html = c.get("/admin-panel/explorer/?source=referral_link").content.decode()
    assert "Ramesh Kumar" in html  # name shown for the known referrer


# --- explorer sorting --------------------------------------------------------

def test_explorer_default_sorts_by_last_activity_desc(admin_client):
    """Default order = last activity, newest first; rows with no activity trail."""
    from apps.dashboard import queries
    from apps.tenants.resolve import get_bootstrap_tenant
    rows = queries.explorer_rows(get_bootstrap_tenant())
    stamps = [r["last_activity"] for r in rows if r["last_activity"] is not None]
    assert stamps == sorted(stamps, reverse=True)
    # every no-activity row (if any) comes after every dated row
    tail = rows[len(stamps):]
    assert all(r["last_activity"] is None for r in tail)


def test_explorer_sorts_by_any_whitelisted_column_both_directions(admin_client):
    from apps.dashboard import queries
    from apps.tenants.resolve import get_bootstrap_tenant
    tenant = get_bootstrap_tenant()
    for key in queries.EXPLORER_SORT_KEYS:
        for direction, rev in (("asc", False), ("desc", True)):
            rows = queries.explorer_rows(tenant, sort=key, direction=direction)
            key_fn = queries.EXPLORER_SORT_KEYS[key]
            vals = [key_fn(r) for r in rows if key_fn(r) is not None]
            assert vals == sorted(vals, reverse=rev), f"{key} {direction} out of order"


def test_explorer_invalid_sort_params_fall_back(admin_client):
    resp = admin_client.get("/admin-panel/explorer/?sort=evil'-- &dir=sideways")
    assert resp.status_code == 200


def test_explorer_headers_link_and_preserve_filters(admin_client):
    html = admin_client.get(
        "/admin-panel/explorer/?source=referral_link&sort=clicks&dir=desc"
    ).content.decode()
    # header links carry the sort params and keep the active source filter
    assert "sort=clicks" in html and "sort=last_activity" in html
    assert "source=referral_link" in html
    # active column shows a direction indicator (▼ desc)
    assert "&#9660;" in html or "▼" in html


# --- explorer funnel columns (owner design A, 2026-07-22) --------------------

def _make_journey(events=(), client_id="ZZ9999"):
    """Referral on the seeded program with the given (event_type, is_bot) events."""
    from apps.events.models import Event
    from apps.referrals.models import Referral, ReferralIdentity, ReferralProgram
    program = ReferralProgram.objects.get()
    identity = ReferralIdentity.objects.create(
        tenant=program.tenant, program=program, partner=program.partner,
        client_id=client_id, status="active",
    )
    ref = Referral.objects.create(
        tenant=program.tenant, program=program, referral_identity=identity,
        source="referral_link", status="opened",
    )
    for event_type, is_bot in events:
        Event.objects.create(
            tenant=program.tenant, referral=ref, event_type=event_type, is_bot=is_bot
        )
    return ref


def _row_for(ref, **kwargs):
    from apps.dashboard import queries
    rows = queries.explorer_rows(ref.tenant, **kwargs)
    return next(r for r in rows if r["id"] == ref.id)


def test_explorer_row_carries_full_funnel_counts(demo):
    """One row = one link's funnel: clicks / landing opens / REAL leads / accounts."""
    from apps.referrals.lead_service import capture_lead
    ref = _make_journey([
        ("click", False), ("click", False), ("landing_viewed", False),
    ])
    capture_lead(
        tenant=ref.tenant, referral=ref, name="Test Prospect",
        mobile="9876500001", email="", city="", consent=True,
    )
    row = _row_for(ref)
    assert (row["clicks"], row["landing_views"], row["leads"], row["accounts"]) == (2, 1, 1, 0)


def test_explorer_leads_count_real_lead_rows_not_events(demo):
    """A stray lead_captured event with NO Lead row must not count (never overstate)."""
    ref = _make_journey([("click", False), ("lead_captured", False)])
    assert _row_for(ref)["leads"] == 0


def test_explorer_stage_filter(demo):
    from apps.dashboard import queries
    ref = _make_journey([("click", False), ("landing_viewed", False)], client_id="ZZ9998")
    rows = queries.explorer_rows(ref.tenant, stage="landing")
    assert all(r["landing_views"] > 0 for r in rows)
    assert any(r["id"] == ref.id for r in rows)
    rows = queries.explorer_rows(ref.tenant, stage="account")
    assert all(r["accounts"] > 0 for r in rows)
    assert not any(r["id"] == ref.id for r in rows)


def test_explorer_bot_events_never_counted_or_timestamped(demo):
    ref = _make_journey([("click", True), ("landing_viewed", True)])
    row = _row_for(ref)
    assert (row["clicks"], row["last_activity"]) == (0, None)
    # and the no-activity row trails the dated rows under the default sort
    from apps.dashboard import queries
    rows = queries.explorer_rows(ref.tenant)
    assert rows[-1]["last_activity"] is None


def test_explorer_synthetic_traffic_never_counted(demo):
    """GoLiveSmoke/curl traffic is excluded from counts (owner decision 2026-07-22)."""
    from apps.events.models import Event
    ref = _make_journey(client_id="ZZ5555")
    for ua in ("GoReferGoLiveSmoke/1.0 (+ops)", "curl/8.15.0"):
        Event.objects.create(
            tenant=ref.tenant, referral=ref, event_type="click", user_agent=ua
        )
    row = _row_for(ref)
    assert (row["clicks"], row["last_activity"]) == (0, None)


def test_synthetic_ua_classifier():
    from apps.events.bots import is_synthetic_user_agent
    assert is_synthetic_user_agent("GoReferGoLiveSmoke/1.0 (+ops)")
    assert is_synthetic_user_agent("curl/8.15.0")
    assert not is_synthetic_user_agent("Mozilla/5.0 (Linux; Android 14)")
    assert not is_synthetic_user_agent(None)


def test_explorer_renders_funnel_columns_and_stage_dropdown(admin_client):
    """Owner design A: count columns replace the collapsed Status word entirely."""
    html = admin_client.get("/admin-panel/explorer/").content.decode()
    for label in ("Leads", "Accounts", "Landing opens", "Any stage reached"):
        assert label in html
    assert "sort=leads" in html and "sort=accounts" in html
    # the collapsed status column is gone from the explorer table
    assert "sort=status" not in html


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
