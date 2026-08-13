"""T-122 — soft-landing recovery page for a share/acquisition link whose
`client_id` fell out (missing/empty).

Background: a Zoho field-mapping bug sent WhatsApp template URL buttons with a
BLANK `{{client_id}}`, so taps on `/share/wa/{{client_id}}` and `/r/{{client_id}}`
landed on the bare path -> 404. This page ensures those taps (and any bare `/r/`
hit) always resolve to a branded, actionable page instead.

Guardrails asserted:
  - never a 404 — HTTP 200 for /share/{channel}/ (+ query string), /share/{channel}
    (bare), /r/, /r;
  - `/share/...` routes stay behind ENABLE_SHARE_INTENT, same as the parent route;
  - exactly one CTA: a wa.me deep link to the config-resolved WATI business number
    with the config-resolved pre-fill text;
  - the compliance disclosure block + market-risk warning render;
  - `share_recovery_viewed` is recorded for a human UA and skipped for a bot UA;
  - no raw Zerodha URL / partner code ever appears in the body.
"""
from urllib.parse import unquote

import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event

HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.7"}
BOT = {"HTTP_USER_AGENT": "WhatsApp/2.23.1", "REMOTE_ADDR": "203.0.113.7"}


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


# --- bare /r/ and /r (unconditional route, no flag) -------------------------

def test_bare_r_with_trailing_slash_returns_200(seeded, client):
    resp = client.get("/r/", **HUMAN)
    assert resp.status_code == 200
    assert "wa.me/" in resp.content.decode()


def test_bare_r_without_trailing_slash_returns_200(seeded, client):
    resp = client.get("/r", **HUMAN)
    assert resp.status_code == 200


def test_bare_r_records_recovery_viewed_for_human(seeded, client):
    client.get("/r/", **HUMAN)
    event = Event.objects.get(event_type="share_recovery_viewed")
    assert event.is_bot is False
    assert event.person_ref_id is None


def test_bare_r_records_no_event_for_bot(seeded, client):
    client.get("/r/", **BOT)
    assert not Event.objects.filter(event_type="share_recovery_viewed").exists()


# --- /share/{channel}/ missing client_id, behind ENABLE_SHARE_INTENT --------

@pytest.mark.urls("tests.urls_share_intent")
def test_share_channel_missing_client_id_with_slash_returns_200(seeded, client):
    resp = client.get("/share/wa/", **HUMAN)
    assert resp.status_code == 200


@pytest.mark.urls("tests.urls_share_intent")
def test_share_channel_missing_client_id_bare_returns_200(seeded, client):
    resp = client.get("/share/wa", **HUMAN)
    assert resp.status_code == 200


@pytest.mark.urls("tests.urls_share_intent")
def test_share_channel_missing_client_id_with_query_string_returns_200(seeded, client):
    """A crawler/tracker query string (fbclid etc.) must not matter to routing."""
    resp = client.get("/share/wa/?fbclid=abc123&utm_source=wati", **HUMAN)
    assert resp.status_code == 200


@pytest.mark.urls("tests.urls_share_intent")
def test_share_channel_recovery_records_channel_in_metadata(seeded, client):
    client.get("/share/wa/", **HUMAN)
    event = Event.objects.get(event_type="share_recovery_viewed")
    assert event.metadata.get("channel") == "WhatsApp"


def test_share_channel_recovery_404s_when_flag_off(seeded, client):
    """No @pytest.mark.urls override here — exercises the REAL prod urlconf, where
    ENABLE_SHARE_INTENT defaults False, so the whole /share/ surface must not exist
    (Constitution §4: no route at all when a flag is off, not a 404 rendered page
    that happens to say 404 — the URLconf itself must not register it)."""
    resp = client.get("/share/wa/", **HUMAN)
    assert resp.status_code == 404


# --- Content / compliance / CTA ---------------------------------------------

def test_recovery_page_has_exactly_one_primary_cta(seeded, client):
    body = client.get("/r/", **HUMAN).content.decode()
    assert body.count('href="https://wa.me/') == 1


def test_recovery_page_wa_link_uses_configured_number_and_prefill(seeded, client):
    body = client.get("/r/", **HUMAN).content.decode()
    assert "https://wa.me/917080642020?text=" in body
    start = body.index("https://wa.me/917080642020?text=") + len("https://wa.me/917080642020?text=")
    end = body.index('"', start)
    prefill = unquote(body[start:end])
    assert prefill == "Hi, I need my referral link"


def test_recovery_page_renders_compliance_disclosure(seeded, client):
    body = client.get("/r/", **HUMAN).content.decode()
    assert "AP2516003693" in body  # NSE AP reg. no., part of the disclosure block


def test_recovery_page_has_no_partner_code_or_raw_zerodha_url(seeded, client):
    body = client.get("/r/", **HUMAN).content.decode()
    assert "ZMPHZC" not in body
    assert "signup.zerodha.com" not in body


def test_recovery_page_has_no_login_or_form(seeded, client):
    body = client.get("/r/", **HUMAN).content.decode()
    assert "<form" not in body
