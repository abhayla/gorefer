"""One-tap share for X and Telegram (owner decision 2026-11-02), alongside WhatsApp.

/share/x/{client_id} opens a new X post, /share/tg/{client_id} Telegram's share screen.
The link inside is tagged with the platform (/zerodha/r/x/AB1234), so clicks credit the
referrer and count under X/Telegram. X uses its own shorter message (cascade key
share_kit_message_template__x) carrying the market-risk warning verbatim; every message
ends with the disclosure line. Facebook has a builder but is HELD (no disclosure text can
ride a Facebook share) — /share/fb/... stays a 404 until it is switched on.
"""
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.management import call_command
from django.test import Client

from apps.config import preferences as prefkeys
from apps.config.cascade import set_tenant
from apps.events.models import Event
from apps.referrals.models import ReferralIdentity
from apps.referrals.share_intent_service import build_facebook_target
from apps.tenants.resolve import get_bootstrap_tenant
from tests.link_fallback_helpers import fell_back

pytestmark = pytest.mark.urls("tests.urls_share_intent")

HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.9"}
RISK = (
    "Investments in securities market are subject to market risks, read all the related "
    "documents carefully before investing."
)
DISCLOSURES = "Disclosures: https://gorefer.in/d/pifs"


@pytest.fixture
def seeded(db, settings):
    settings.PUBLIC_BASE_URL = "https://gorefer.in"
    call_command("seed_program")


def _get(path, capture, **kw):
    with capture(execute=True):
        return Client().get(path, **(kw or HUMAN))


def _query(location):
    return {k: v[0] for k, v in parse_qs(urlparse(location).query).items()}


def test_x_opens_a_post_with_the_short_message(seeded, django_capture_on_commit_callbacks):
    resp = _get("/share/x/AB1234", django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("https://x.com/intent/post?text=")
    text = _query(resp.headers["Location"])["text"]
    assert text == (
        "Open a free Zerodha account with my referral link:\n"
        "https://gorefer.in/zerodha/r/x/AB1234\n\n" + RISK + "\n\n" + DISCLOSURES
    )
    # X counts every link as 23 characters; the post must fit 280.
    links = ("https://gorefer.in/zerodha/r/x/AB1234", "https://gorefer.in/d/pifs")
    assert len(text) - sum(len(u) for u in links) + 23 * len(links) <= 280
    assert "ZMPHZC" not in text
    event = Event.objects.get(event_type="share_intent")
    assert event.metadata == {"channel": "X"}
    assert ReferralIdentity.objects.filter(client_id="AB1234").exists()


def test_telegram_shares_the_link_and_the_usual_message(seeded, django_capture_on_commit_callbacks):
    resp = _get("/zerodha/share/tg/AB1234", django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("https://t.me/share/url?url=")
    q = _query(resp.headers["Location"])
    assert q["url"] == "https://gorefer.in/zerodha/r/tg/AB1234"
    assert "https://gorefer.in/zerodha/r/tg/AB1234" in q["text"]
    assert q["text"].endswith(DISCLOSURES)
    assert Event.objects.get(event_type="share_intent").metadata == {"channel": "Telegram"}


def test_whatsapp_keeps_its_own_one_tap_message(seeded, django_capture_on_commit_callbacks):
    resp = _get("/share/wa/AB1234", django_capture_on_commit_callbacks)
    text = _query(resp.headers["Location"])["text"]
    assert resp.headers["Location"].startswith("https://wa.me/?text=")
    assert "https://gorefer.in/zerodha/open" in text  # owner 2026-11-04
    assert not text.startswith("Open a free Zerodha account with my referral link:\nhttps://gorefer.in/zerodha/r/x/")


def test_the_x_message_is_config(seeded, django_capture_on_commit_callbacks):
    """rail E-6 spot test: X's message is a cascade key, editable without a deploy."""
    set_tenant(prefkeys.SHARE_KIT_MESSAGE_TEMPLATE_X, "Join {program_brand}: {link}",
               tenant_id=get_bootstrap_tenant().id)
    text = _query(_get("/share/x/AB1234", django_capture_on_commit_callbacks).headers["Location"])["text"]
    assert text == "Join Zerodha: https://gorefer.in/zerodha/r/x/AB1234\n\n" + DISCLOSURES


@pytest.mark.parametrize(
    "ch,title", [("x", "Share on X"), ("tg", "Share on Telegram"), ("wa", "Share on WhatsApp")]
)
def test_placeholder_share_shows_the_prompt_named_for_the_platform(
    seeded, django_capture_on_commit_callbacks, ch, title
):
    for path in (f"/share/{ch}/KITEID", f"/share/{ch}/", f"/zerodha/share/{ch}/YOUR_KITE_ID"):
        body = _get(path, django_capture_on_commit_callbacks).content.decode()
        assert prefkeys.KITE_PROMPT_SHARE_TITLE_DEFAULT in body and title in body, path
    assert ReferralIdentity.objects.count() == 0
    resp = _get(f"/share/{ch}/KITEID?kite_id=ab1234", django_capture_on_commit_callbacks)
    assert resp.headers["Location"] == f"/zerodha/share/{ch}/AB1234"


@pytest.mark.parametrize("ch,prefix", [("x", "https://x.com/intent/post?text="), ("tg", "https://t.me/share/url?url=")])
def test_share_without_id_uses_the_no_referrer_link(seeded, django_capture_on_commit_callbacks, ch, prefix):
    resp = _get(f"/share/{ch}/?skip=1", django_capture_on_commit_callbacks)
    assert resp.headers["Location"].startswith(prefix)
    assert "gorefer.in%2Fzerodha%2Fr%2Fopen" in resp.headers["Location"]
    assert ReferralIdentity.objects.count() == 0


def test_facebook_is_held(seeded, django_capture_on_commit_callbacks):
    assert fell_back(_get("/share/fb/AB1234", django_capture_on_commit_callbacks))
    assert fell_back(_get("/zerodha/share/fb/AB1234", django_capture_on_commit_callbacks))
    assert "wa.me/" in _get("/share/fb/", django_capture_on_commit_callbacks).content.decode()  # help page
    # The builder is ready for when it is switched on: link only, as Facebook requires.
    assert build_facebook_target("ignored", "https://gorefer.in/zerodha/r/fb/AB1234") == (
        "https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fgorefer.in%2Fzerodha%2Fr%2Ffb%2FAB1234"
    )
