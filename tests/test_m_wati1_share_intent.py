"""M-WATI-1 — one-tap share endpoint (GET /share/{channel}/{client_id}).

Flag-gated (`ENABLE_SHARE_INTENT`, default False — Constitution §4, no dead route
when off): the route is registered at urlconf-import time from
settings.FEATURE_FLAGS, so every test here runs against `tests.urls_share_intent`
(the test urlconf mirroring the flag-on mount) rather than flipping the flag
per-test. Mirrors the fixtures/style of `tests/test_b1_channel_path.py`.

Guardrails asserted:
  - the 302 Location is exactly the WhatsApp share deep-link with the tracked
    `/r/wa/{client_id}` link prefilled — never a raw Zerodha URL/partner code;
  - the `share_intent` event is PII-free (no VisitorPII row, no person_ref_id)
    even though the request carries a REMOTE_ADDR;
  - lazy referrer/journey creation (ADR-008) reused, not duplicated;
  - an unsupported channel 404s (never a silent "other" fallback) and writes
    nothing; an invalid client_id 400s and writes nothing;
  - a bot/preview UA still gets the destination but creates no journey/event.
"""
from urllib.parse import unquote

import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event, VisitorPII
from apps.referrals.models import Referral, ReferralIdentity

pytestmark = pytest.mark.urls("tests.urls_share_intent")

HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.7"}


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


def test_share_intent_redirects_to_wa_me_with_tracked_link(seeded, client):
    resp = client.get("/share/wa/RJ4521", **HUMAN)
    assert resp.status_code == 302
    location = resp.headers["Location"]
    assert location.startswith("https://wa.me/?text=")
    decoded = unquote(location.split("?text=", 1)[1])
    assert "gorefer.in/r/wa/RJ4521" in decoded
    assert decoded.startswith("Open a free Zerodha account")


def test_share_intent_event_is_pii_free(seeded, client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        client.get("/share/wa/RJ4521", **HUMAN)
    event = Event.objects.get(event_type="share_intent")
    assert event.source == "wati"
    assert event.metadata.get("channel") == "WhatsApp"
    assert event.person_ref_id is None
    assert VisitorPII.objects.count() == 0


def test_share_intent_lazily_creates_the_journey(seeded, client, django_capture_on_commit_callbacks):
    assert not ReferralIdentity.objects.filter(client_id="RJ4521").exists()
    with django_capture_on_commit_callbacks(execute=True):
        client.get("/share/wa/RJ4521", **HUMAN)
    assert ReferralIdentity.objects.filter(client_id="RJ4521").exists()
    assert Referral.objects.filter(source="referral_link").exists()


def test_unsupported_channel_404s_with_no_event(seeded, client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.get("/share/tg/RJ4521", **HUMAN)
    assert resp.status_code == 404
    assert Event.objects.count() == 0


def test_invalid_client_id_400s_with_no_writes(seeded, client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.get("/share/wa/AB", **HUMAN)
    assert resp.status_code == 400
    assert Event.objects.count() == 0
    assert ReferralIdentity.objects.count() == 0


@pytest.mark.parametrize("ua", ["facebookexternalhit/1.1", "WhatsApp/2.23.20"])
def test_bot_ua_still_redirects_but_creates_nothing(seeded, client, django_capture_on_commit_callbacks, ua):
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.get("/share/wa/RJ4521", HTTP_USER_AGENT=ua)
    assert resp.status_code == 302
    assert Event.objects.count() == 0
    assert ReferralIdentity.objects.count() == 0


def test_guardrail_no_partner_code_or_zerodha_url_in_location(seeded, client):
    resp = client.get("/share/wa/RJ4521", **HUMAN)
    location = unquote(resp.headers["Location"])
    assert "ZMPHZC" not in location
    assert "signup.zerodha.com" not in location
