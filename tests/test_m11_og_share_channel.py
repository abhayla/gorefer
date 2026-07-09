"""M11 — OG preview card + ?s= share-channel capture/strip (ADR-028, S2-01 §5.3/§7).

Guardrails asserted here:
  - ?s= captured as the click's Channel (metadata["channel"]) using config-driven
    labels (wa->WhatsApp, unknown->other, absent->none).
  - ?s is STRIPPED before the 302 — the Zerodha Location never carries `s=`.
  - The OG/Twitter-Card meta renders on the landing, carries NO partner code and NO
    raw Zerodha URL, and does not clone Zerodha.
  - A preview crawler UA gets the OG card but creates NO journey/click and never 302s.
"""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event
from apps.referrals.models import Referral, ReferralIdentity
from gorefer.flags import normalize_share_channel


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


def _get_landing(client, path="/r/RJ4521"):
    """Fetch a landing page as a human mobile browser (helper keeps lines short)."""
    return client.get(path, HTTP_USER_AGENT="Mozilla/5.0 (Android)", REMOTE_ADDR="203.0.113.7")


# --- channel normalization (config-driven codes -> labels) -----------------

def test_normalize_share_channel_maps_codes():
    assert normalize_share_channel("wa") == "WhatsApp"
    assert normalize_share_channel("WA") == "WhatsApp"  # case-insensitive
    assert normalize_share_channel("fb") == "Facebook"
    assert normalize_share_channel("x") == "X"
    assert normalize_share_channel("li") == "LinkedIn"
    assert normalize_share_channel("tg") == "Telegram"
    assert normalize_share_channel("ig") == "Instagram"
    assert normalize_share_channel("email") == "Email"
    assert normalize_share_channel("copy") == "Copy"


def test_normalize_share_channel_unknown_is_other():
    assert normalize_share_channel("zzz") == "other"


def test_normalize_share_channel_absent_is_none():
    assert normalize_share_channel(None) is None
    assert normalize_share_channel("") is None
    assert normalize_share_channel("   ") is None


# --- ?s=wa recorded as the click channel -----------------------------------

def test_s_wa_recorded_as_click_channel(seeded, client):
    resp = client.get("/r/RJ4521?s=wa", HTTP_USER_AGENT="Mozilla/5.0 (Android)", REMOTE_ADDR="203.0.113.7")
    assert resp.status_code == 200
    click = Event.objects.get(event_type="click")
    assert click.metadata.get("channel") == "WhatsApp"


def test_s_unknown_recorded_as_other(seeded, client):
    client.get("/r/RJ4521?s=zzz", HTTP_USER_AGENT="Mozilla/5.0 (Android)", REMOTE_ADDR="203.0.113.7")
    assert Event.objects.get(event_type="click").metadata.get("channel") == "other"


def test_no_s_param_means_no_channel_key(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0 (Android)", REMOTE_ADDR="203.0.113.7")
    click = Event.objects.get(event_type="click")
    assert "channel" not in (click.metadata or {})  # renders as "Direct" in the profile


def test_config_driven_param_name(seeded, client, monkeypatch):
    # The param NAME is config (SHARE_CHANNEL_PARAM). Point it at ?src= and verify the
    # view reads the configured name. flags is a module-level singleton; patch its attr.
    from gorefer import flags as flagmod

    monkeypatch.setattr(flagmod, "SHARE_CHANNEL_PARAM", "src")
    client.get("/r/RJ4521?src=fb", HTTP_USER_AGENT="Mozilla/5.0 (Android)", REMOTE_ADDR="203.0.113.7")
    assert Event.objects.get(event_type="click").metadata.get("channel") == "Facebook"


# --- ?s stripped before the 302 (never leaks into the Zerodha Location) -----

def test_s_stripped_from_continue_302(seeded, client):
    client.get("/r/RJ4521?s=wa", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    resp = client.get("/r/RJ4521/continue?s=wa", HTTP_USER_AGENT="Mozilla/5.0")
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    # Exactly the server-assembled destination — no s= anywhere.
    assert loc == "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=RJ4521"
    assert "s=wa" not in loc
    assert "&s=" not in loc and "?s=" not in loc


def test_s_stripped_from_open_302(seeded, client):
    resp = client.get("/open?s=wa", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    assert loc == "https://signup.zerodha.com/api/lead/?c=ZMPHZC"
    assert "s=" not in loc.split("?", 1)[1]


# --- OG / Twitter-Card meta present + guardrail #3 (no partner code / Zerodha URL) --

def test_landing_has_og_and_twitter_card_meta(seeded, client):
    html = _get_landing(client).content.decode()
    assert 'property="og:title"' in html
    assert 'property="og:description"' in html
    assert 'property="og:image"' in html
    assert 'property="og:url"' in html
    assert 'name="twitter:card"' in html and "summary_large_image" in html
    # og:url points at our own /r/{id}, absolute.
    assert "/r/RJ4521" in html


def test_og_card_and_landing_have_no_partner_code_or_zerodha_url(seeded, client):
    html = _get_landing(client).content.decode()
    assert "ZMPHZC" not in html
    assert "signup.zerodha.com" not in html


# --- crawler-not-a-click: preview UA gets the card, no journey/click/redirect ---

@pytest.mark.parametrize(
    "ua",
    [
        "facebookexternalhit/1.1",
        "Twitterbot/1.0",
        "LinkedInBot/1.0",
        "WhatsApp/2.23.20",
        "TelegramBot (like TwitterBot)",
        "Slackbot-LinkExpanding 1.0",
    ],
)
def test_crawler_gets_card_but_no_journey(seeded, client, ua):
    resp = client.get("/r/RJ4521?s=wa", HTTP_USER_AGENT=ua)
    assert resp.status_code == 200
    html = resp.content.decode()
    # The crawler still gets a compliant OG card...
    assert 'property="og:title"' in html
    # ...but NO journey / identity / click event is created, and no channel recorded.
    assert ReferralIdentity.objects.count() == 0
    assert Referral.objects.count() == 0
    assert Event.objects.count() == 0
