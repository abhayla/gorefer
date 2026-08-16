"""T-148 — public, no-login privacy policy page at /privacy.

Live defect this closes: the landing form's consent checkbox linked to
https://gorefer.in/privacy, which 404'd in production (no route existed). This
is a live DPDP exposure for an SEBI Authorised Person — consent must reference a
readable policy.

Guardrails asserted:
  - GET /privacy -> 200, no login required, AP disclosure + market-risk warning
    present (page extends landing_base.html like every other customer page).
  - All DPDP sections required by the T-148 contract are present: who collects,
    what is collected, purpose limitation, sharing (Zoho + Wati/Meta), retention
    (12 months / ADR-020), erasure (WATI number or email), consent.
  - The landing page's Privacy Policy link href equals the cascade-resolved
    `privacy_policy_url` config value, not a hardcoded literal.
  - `privacy_policy_url` is a config key (not a Python constant) with a seeded
    default of "/privacy" so a fresh seed points at the route this test hits.
"""
import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import Client

from apps.config.cascade import resolve
from apps.config.models import ConfigCentral


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


# --- route + compliance block ------------------------------------------------

def test_privacy_page_returns_200_no_login(seeded, client):
    resp = client.get("/privacy")
    assert resp.status_code == 200


def test_privacy_page_carries_compliance_block(seeded, client):
    html = client.get("/privacy").content.decode()
    assert settings.AP_DISCLOSURE_BLOCK in html
    assert settings.MARKET_RISK_WARNING in html


# --- required DPDP sections ---------------------------------------------------

def test_privacy_page_names_who_collects(seeded, client):
    html = client.get("/privacy").content.decode()
    assert "Passive Income Financial Solutions" in html
    assert "Zerodha Authorised Person" in html
    assert settings.NSE_AP_NO in html


def test_privacy_page_lists_what_is_collected(seeded, client):
    html = client.get("/privacy").content.decode()
    for term in ("name", "mobile", "email", "IP address", "city", "visitor_id"):
        assert term in html, f"missing data-collected item: {term!r}"


def test_privacy_page_states_purpose_limitation(seeded, client):
    html = client.get("/privacy").content.decode()
    assert "referral" in html.lower()
    assert "Zerodha demat" in html or "Zerodha account" in html


def test_privacy_page_names_sharing_partners(seeded, client):
    html = client.get("/privacy").content.decode()
    assert "Zoho" in html
    assert "Wati" in html
    assert "Meta" in html


def test_privacy_page_states_12_month_retention(seeded, client):
    html = client.get("/privacy").content.decode()
    assert "12 months" in html


def test_privacy_page_gives_erasure_channel(seeded, client):
    html = client.get("/privacy").content.decode()
    assert "wa.me/917080642020" in html
    assert "mailto:" not in html


def test_privacy_page_mentions_consent(seeded, client):
    html = client.get("/privacy").content.decode()
    assert "consent" in html.lower()


# --- landing form link resolves to the live route, config-driven -------------

def test_landing_privacy_link_matches_configured_url(seeded, client):
    landing_html = client.get(
        "/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7"
    ).content.decode()
    configured = resolve("privacy_policy_url", default="/privacy")
    assert f'href="{configured}"' in landing_html


def test_privacy_policy_url_is_seeded_config_not_hardcoded(seeded):
    row = ConfigCentral.objects.get(key="privacy_policy_url")
    assert row.value == "/privacy"


def test_privacy_link_from_landing_page_actually_loads(seeded, client):
    configured = resolve("privacy_policy_url", default="/privacy")
    assert configured.startswith("/"), "expected a same-origin relative path"
    resp = client.get(configured)
    assert resp.status_code == 200
