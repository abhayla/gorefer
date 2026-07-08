"""M9 — Zoho-READ enrichment + User Referral Screen ("Referral Profile") tests.

Admin-only screen; Zoho WRITE stays OFF; Zoho READ enrichment is fixture-backed in
demo (flag off) and flagged live otherwise. Guardrail #2 preserved: the READ adapter
never writes/sets conversion status. Config-over-code: columns/strings come from
PROFILE_CONFIG, not inline literals.
"""
import json
import re

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client


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


def _embedded_clicks(html: str):
    m = re.search(r'id="gr-clicks"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else []


# --- auth gate -------------------------------------------------------------

def test_profile_requires_login(demo):
    resp = Client().get("/admin-panel/referrer/RJ4521/")
    assert resp.status_code == 302
    assert "/admin-panel/login/" in resp.headers["Location"]


def test_search_requires_login(demo):
    resp = Client().get("/admin-panel/referrers/")
    assert resp.status_code == 302


# --- profile renders -------------------------------------------------------

def test_profile_renders_top_band_and_zoho_enrichment(admin_client):
    html = admin_client.get("/admin-panel/referrer/RJ4521/").content.decode()
    assert "Rajesh Joshi" in html          # Zoho-read name (fixture)
    assert "Active Investor" in html       # is_active_investor chip
    assert "Pune, MH" in html              # Mailing_City/State enrichment
    assert "gorefer.in/r/RJ4521" in html   # per-link card link
    assert "Referral Profile" in html


def test_profile_loads_rings_js_so_kpi_rings_paint(admin_client):
    """DEF-M9-1: the top-band KPI rings are drawn by rings.js — it MUST be loaded on
    the profile (data-ring divs are inert without it)."""
    html = admin_client.get("/admin-panel/referrer/RJ4521/").content.decode()
    assert "data-ring" in html                 # ring placeholders present
    assert "js/rings.js" in html               # and the script that paints them


def test_profile_missing_zoho_value_shows_not_on_file(admin_client):
    """DA1707 has no Reward/Referral_Bonus in the fixture → '— not on file —'."""
    html = admin_client.get("/admin-panel/referrer/DA1707/").content.decode()
    assert "— not on file —" in html


def test_profile_unknown_client_id_404(admin_client):
    # A well-formed id with no GoRefer footprint has no profile.
    assert admin_client.get("/admin-panel/referrer/ZZ9999/").status_code == 404


def test_profile_invalid_client_id_404(admin_client):
    # Sub-min-length / illegal → 404 (validator).
    assert admin_client.get("/admin-panel/referrer/AB/").status_code == 404


# --- clicks tab: enriched rows, bot excluded from totals -------------------

def test_profile_clicks_tab_has_enriched_rows(admin_client):
    html = admin_client.get("/admin-panel/referrer/RJ4521/").content.decode()
    rows = _embedded_clicks(html)
    assert len(rows) == 5                       # 4 human + 1 bot (seed)
    humans = [r for r in rows if not r["bot"]]
    bots = [r for r in rows if r["bot"]]
    assert len(humans) == 4 and len(bots) == 1
    # geo/device/channel enrichment present on human rows.
    cities = {r["city"] for r in humans}
    assert "Pune" in cities and "Mumbai" in cities
    assert any(r["channel"] == "WhatsApp" for r in humans)
    assert any(r["device"] == "Mobile" for r in humans)
    assert bots[0]["outcome"] == "Bot — excluded"


def test_profile_headline_clicks_exclude_bots(admin_client):
    from apps.dashboard import profile
    from apps.tenants.resolve import get_bootstrap_tenant

    band = profile.top_band(get_bootstrap_tenant(), "RJ4521")
    # 4 human clicks counted; the 1 bot click is excluded from the headline.
    assert band["aggregates"]["clicks"] == 4


def test_profile_ip_from_visitor_pii(admin_client):
    """IP comes from the erasable VisitorPII (admin sees full IP), never the Event."""
    html = admin_client.get("/admin-panel/referrer/RJ4521/").content.decode()
    rows = _embedded_clicks(html)
    assert any(r["ip"] == "49.36.142.18" for r in rows)


# --- referred people tab (Zoho READ) ---------------------------------------

def test_profile_referred_people_from_zoho(admin_client):
    html = admin_client.get("/admin-panel/referrer/RJ4521/").content.decode()
    assert "Referred People" in html
    assert "Sunil Kamble" in html   # fixture referred person
    # A person with no Zoho name renders the italic "name not on file" marker.
    assert "— name not on file —" in html


# --- per-link cards: real enabled partners only ----------------------------

def test_profile_only_real_enabled_partner_cards(admin_client):
    """The illustrative 'Loan' card from the mockup is NOT shipped — only real,
    enabled programs (today: Zerodha)."""
    from apps.dashboard import profile
    from apps.tenants.resolve import get_bootstrap_tenant

    cards = profile.per_link_cards(get_bootstrap_tenant(), "RJ4521")
    assert len(cards) == 1
    assert cards[0]["partner_name"] == "Zerodha"
    assert cards[0]["partner_code"] == "ZMPHZC"


# --- config-over-code ------------------------------------------------------

def test_profile_columns_are_config_driven(admin_client):
    """Column sets come from PROFILE_CONFIG, not inline literals — the Referred
    People header labels render from config."""
    from apps.dashboard.profile import PROFILE_CONFIG

    html = admin_client.get("/admin-panel/referrer/RJ4521/").content.decode()
    for _key, label in PROFILE_CONFIG["people_columns"]:
        assert label in html
    # Click columns are handed to the JS as config JSON (json_script).
    assert 'id="gr-ccols"' in html


# --- search entry point ----------------------------------------------------

def test_referrer_search_exact_client_id_redirects(admin_client):
    resp = admin_client.get("/admin-panel/referrers/?q=RJ4521")
    assert resp.status_code == 302
    assert "/admin-panel/referrer/RJ4521/" in resp.headers["Location"]


def test_referrer_search_by_name_lists_matches(admin_client):
    from apps.referrals.models import Customer, ReferralProgram

    program = ReferralProgram.objects.get()
    Customer.objects.get_or_create(
        tenant=program.tenant, program=program, partner=program.partner,
        client_id="RJ4521", defaults={"first_name": "Rajesh", "last_name": "Joshi"},
    )
    html = admin_client.get("/admin-panel/referrers/?q=Rajesh").content.decode()
    assert "RJ4521" in html


def test_referrer_search_empty_is_friendly(admin_client):
    html = admin_client.get("/admin-panel/referrers/?q=NOPE99").content.decode()
    assert "No referrer found" in html


# --- Zoho READ adapter (fixtures) ------------------------------------------

def test_zoho_read_adapter_returns_fixture_contact(db):
    from apps.integrations.zoho.read import get_zoho_read_adapter

    adapter = get_zoho_read_adapter()
    contact = adapter.fetch_contact_by_client_id(client_id="RJ4521")
    assert contact.matched is True
    assert contact.full_name == "Rajesh Joshi"
    assert contact.mailing_city == "Pune"
    assert contact.is_active_investor is True


def test_zoho_read_adapter_unknown_client_is_unmatched(db):
    from apps.integrations.zoho.read import get_zoho_read_adapter

    contact = get_zoho_read_adapter().fetch_contact_by_client_id(client_id="ZZ0000")
    assert contact.matched is False
    assert contact.full_name is None  # → renders "— not on file —"


def test_zoho_read_adapter_referred_people_fixture(db):
    from apps.integrations.zoho.read import get_zoho_read_adapter

    people = get_zoho_read_adapter().fetch_referred_people(referrer_client_id="RJ4521")
    assert len(people.people) == 3
    assert people.people[0].name == "Sunil Kamble"


def test_zoho_read_field_name_normalization(db):
    """doc-08 B4: ClientId (Contacts) vs Client_Id (Referrers) both map; blank → None."""
    from apps.integrations.zoho.read import _norm_contact

    c = _norm_contact("X1", {"Full_Name": "A B", "Mailing_City": "", "Profession": "Doc"})
    assert c.full_name == "A B"
    assert c.mailing_city is None   # blank treated as missing
    assert c.profession == "Doc"


# --- flagged live-read (integration; refuses without creds) ----------------

def test_zoho_read_live_adapter_selected_when_flag_on(db, monkeypatch):
    """With ENABLE_ZOHO_READ on but no creds, the LIVE adapter is selected and
    refuses to run (never silently falls back to fixtures)."""
    monkeypatch.setenv("ENABLE_ZOHO_READ", "true")
    monkeypatch.delenv("ZOHO_CLIENT_ID", raising=False)
    monkeypatch.delenv("ZOHO_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("ZOHO_REFRESH_TOKEN", raising=False)
    from apps.integrations.zoho.read import get_zoho_read_adapter

    with pytest.raises(RuntimeError):
        get_zoho_read_adapter()


# --- guardrail #2: READ enrichment never writes conversion status ----------

def test_zoho_read_never_writes_conversion(admin_client):
    """Viewing the profile (which calls the READ adapter) creates no Conversion and
    sets no account status — status still comes only from the webhook ingest path."""
    from apps.integrations.models import Conversion

    before = Conversion.objects.count()
    admin_client.get("/admin-panel/referrer/RJ4521/")
    admin_client.get("/admin-panel/referrer/DA1707/")
    assert Conversion.objects.count() == before


# --- PII masking config (built now, admin view stays full) -----------------

def test_pii_mask_config_exists_and_admin_view_is_full(admin_client, settings):
    """PII_MASK_FOR_CUSTOMER_VIEW exists (built now); the ADMIN view still shows the
    full IP (masking only activates in a future customer view)."""
    assert hasattr(settings, "PII_MASK_FOR_CUSTOMER_VIEW")
    html = admin_client.get("/admin-panel/referrer/RJ4521/").content.decode()
    rows = _embedded_clicks(html)
    assert any(r["ip"] == "49.36.142.18" for r in rows)  # full IP, unmasked (admin)
