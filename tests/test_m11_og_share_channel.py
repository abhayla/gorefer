"""M11 — OG preview card + ?s= share-channel capture/strip (ADR-028, S2-01 §5.3/§7).

Guardrails asserted here:
  - ?s= captured as the click's Channel (metadata["channel"]) using config-driven
    labels (wa->WhatsApp, unknown->other, absent->none).
  - ?s is STRIPPED before the 302 — the Zerodha Location never carries `s=`.
  - The OG/Twitter-Card meta renders on the landing, carries NO partner code and NO
    raw Zerodha URL, and does not clone Zerodha.
  - A preview crawler UA gets the OG card but creates NO journey/click and never 302s.
"""
import re

import pytest
from django.conf import settings
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
    assert loc == "https://signup.zerodha.com/?c=ZMPHZC"
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


def _og_image_of(html: str) -> str:
    m = re.search(r'property="og:image"\s+content="([^"]*)"', html)
    assert m, "no og:image tag rendered"
    return m.group(1)


@pytest.mark.parametrize("ua", ["Mozilla/5.0 (Android)", "facebookexternalhit/1.1"])
def test_og_image_is_an_absolute_url_on_both_cards(seeded, client, ua):
    """og:image MUST be absolute — a crawler has no page context to resolve a relative one.

    Found live on prod 2026-07-26: the D2 crawler card emitted `og:image="img/og-card.png"`,
    so every forwarded referral link previewed with NO image — the exact surface D2 exists to
    fix. Two separate faults, both asserted here:
      1. the URL was relative;
      2. even resolved, `/img/og-card.png` is a 404 — the asset is served under STATIC_URL.

    The pre-existing check was `'property="og:image"' in html`, i.e. presence only, which is
    why a useless value passed. This asserts the property that actually matters. Parametrised
    over a human UA (M11 landing card) and a crawler UA (D2 preview card) because the bug was
    that those two rendered through DIFFERENT code paths.
    """
    resp = client.get("/r/RJ4521?s=wa", HTTP_USER_AGENT=ua)
    image = _og_image_of(resp.content.decode())
    assert image.startswith(("http://", "https://")), f"og:image not absolute: {image!r}"
    assert settings.STATIC_URL.rstrip("/") in image, (
        f"og:image must resolve under STATIC_URL ({settings.STATIC_URL}), got {image!r} — "
        "a bare /img/... path 404s in production"
    )


def test_absolute_image_url_passes_through_an_already_absolute_value(seeded):
    """An operator may point the cascade key at a CDN URL (CLAUDE.md §6d) — don't mangle it."""
    from apps.referrals.og import absolute_image_url

    cdn = "https://cdn.example.com/card.png"
    assert absolute_image_url(cdn) == cdn
    assert absolute_image_url("") == ""


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


# --- D2: crawlers get the PIFS card instead of a 302 (owner decision 2026-07-26) ---

CRAWLERS = [
    "facebookexternalhit/1.1",
    "WhatsApp/2.23.20.0",
    "Telegrambot (like TwitterBot)",
    "Slackbot-LinkExpanding 1.0",
    "Twitterbot/1.0",
    "LinkedInBot/1.0",
]


@pytest.mark.parametrize("ua", CRAWLERS)
def test_crawler_gets_a_pifs_card_not_a_redirect(seeded, client, ua):
    """M11 promised a PIFS preview card, but it only rendered in LANDING_MODE=page. PIFS runs
    `direct`, so crawlers were 302'd and WhatsApp built its preview from the PARTNER's page —
    every forwarded link showed the partner's branding, not PIFS's."""
    resp = client.get("/r/RJ4521", HTTP_USER_AGENT=ua)
    assert resp.status_code == 200, f"{ua} must NOT be redirected"
    body = resp.content.decode()
    assert 'property="og:title"' in body
    assert 'property="og:description"' in body


def test_crawler_card_leaks_no_partner_code_or_partner_url(seeded, client):
    """Guardrail 3 — this is a client-facing surface."""
    body = client.get("/r/RJ4521", HTTP_USER_AGENT="facebookexternalhit/1.1").content.decode()
    assert "ZMPHZC" not in body
    assert "signup.zerodha.com" not in body


def test_crawler_card_carries_the_compliance_block(seeded, client):
    """A preview card is a customer-facing asset, so the disclosure travels with it."""
    from django.conf import settings

    body = client.get("/r/RJ4521", HTTP_USER_AGENT="facebookexternalhit/1.1").content.decode()
    assert settings.MARKET_RISK_WARNING.split(".")[0] in body


def test_crawler_creates_no_journey_and_no_cookie(seeded, client):
    """The preview must stay as inert as the old 302 path was."""
    from apps.referrals.models import ReferralIdentity

    resp = client.get("/r/CRAWLBOT1", HTTP_USER_AGENT="facebookexternalhit/1.1")
    assert resp.status_code == 200
    assert not ReferralIdentity.objects.filter(client_id="CRAWLBOT1").exists()
    assert "gr_vid" not in resp.cookies


def test_a_human_is_still_redirected(seeded, client):
    """Humans must be unaffected — this only changes what a bot sees."""
    resp = client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0 (Linux; Android 13) Chrome/120")
    assert resp.status_code in (200, 302)
    if resp.status_code == 302:
        assert "signup.zerodha.com" in resp["Location"]
