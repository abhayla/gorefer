"""/r/<unknown value> shows the Kite ID pop-up since 2026-11-02; /r/open keeps its direct link.

History: T-574 (owner 2026-10-22) passed a value that fails the strict Zerodha-id pattern
through to the partner as r=<raw value>, and sent /r/open to the partner's referral page.
Owner decision 2026-11-02 replaced both with the Kite ID pop-up; its Skip is exactly the
old /r/open path (empty referral box, partner code server-side, no referrer). What T-574
guaranteed and still holds: junk NEVER becomes a referrer identity, and the raw value is
never sent anywhere.
"""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.config.models import ConfigCentral
from apps.events.models import Event
from apps.referrals.models import Referral, ReferralIdentity

HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.9"}
BOT = {"HTTP_USER_AGENT": "WhatsApp/2.23.20 A"}
REFERRAL_PAGE = "https://signup.zerodha.com/api/lead/?c=ZMPHZC"
PROMPT_TITLE = "Who referred you?"


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


def _get(client, path, capture, **kw):
    with capture(execute=True):
        return client.get(path, **(kw or HUMAN))


def _assert_prompt_no_writes(resp):
    assert resp.status_code == 200
    assert PROMPT_TITLE in resp.content.decode()
    assert ReferralIdentity.objects.count() == 0
    assert Referral.objects.count() == 0
    assert not Event.objects.filter(event_type="click").exists()


@pytest.mark.parametrize("path", [
    "/r/ZERODHAID",
    "/r/XYZ",
    "/r/zerodhaid",
    "/r/AB%20CD",
    "/r/A%26B%23C%3FD",
    "/r/A%0D%0AB",
    "/r/wa/ZERODHAID",
    "/r/ZERODHAID/continue",
    "/r/wa/ZERODHAID/continue",
    "/r/KITEID",        # well-shaped placeholder: used to become a referrer
    "/r/" + "A" * 32,
    "/r/" + "A" * 33,   # used to be the branded 400
])
def test_unknown_value_shows_the_prompt(seeded, client, django_capture_on_commit_callbacks, path):
    _assert_prompt_no_writes(_get(client, path, django_capture_on_commit_callbacks))


def test_prompt_in_direct_landing_mode_is_same(seeded, client, django_capture_on_commit_callbacks):
    ConfigCentral.objects.update_or_create(key="landing_mode", defaults={"value": "direct"})
    _assert_prompt_no_writes(_get(client, "/r/ZERODHAID", django_capture_on_commit_callbacks))


def test_bot_on_unknown_id_gets_preview_no_writes(seeded, client, django_capture_on_commit_callbacks):
    resp = _get(client, "/r/ZERODHAID", django_capture_on_commit_callbacks, **BOT)
    assert resp.status_code == 200
    assert PROMPT_TITLE not in resp.content.decode()
    assert Event.objects.count() == 0
    assert Referral.objects.count() == 0
    assert ReferralIdentity.objects.count() == 0


@pytest.mark.parametrize("path", ["/r/open", "/r/OPEN", "/r/Open", "/r/wa/open", "/r/wa/OPEN"])
def test_reserved_open_goes_straight_to_empty_referral_box(
    seeded, client, django_capture_on_commit_callbacks, path
):
    """Owner 2026-11-02: no pop-up on /r/open — it is the deliberate no-referrer link (the live
    prospect-invite template uses it), so it keeps its direct 302, exactly as before."""
    resp = _get(client, path, django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    assert resp.headers["Location"] == REFERRAL_PAGE
    assert ReferralIdentity.objects.count() == 0
    assert Referral.objects.filter(source="partner_direct").count() == 1
    assert Event.objects.filter(event_type="click").count() == 1


@pytest.mark.parametrize("path", ["/r/open", "/r/wa/open", "/r/ZERODHAID", "/r/wa/KITEID/continue"])
def test_skip_goes_to_empty_referral_box(seeded, client, django_capture_on_commit_callbacks, path):
    resp = _get(client, path + "?skip=1", django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    assert resp.headers["Location"] == REFERRAL_PAGE  # placeholder dropped, partner code kept
    assert ReferralIdentity.objects.count() == 0
    assert Referral.objects.filter(source="partner_direct").count() == 1
    assert Event.objects.filter(event_type="click").count() == 1


def test_reserved_open_bot_gets_preview(seeded, client, django_capture_on_commit_callbacks):
    resp = _get(client, "/r/open", django_capture_on_commit_callbacks, **BOT)
    assert resp.status_code == 200
    assert Event.objects.count() == 0 and Referral.objects.count() == 0


def test_slash_open_is_unchanged(seeded, client, django_capture_on_commit_callbacks):
    resp = _get(client, "/open", django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://signup.zerodha.com/?c=ZMPHZC"


def test_partner_referral_page_key_is_a_cascade_key(seeded, client, django_capture_on_commit_callbacks):
    """rail E-6 spot test: the Skip destination (old /r/open) is config, not a literal."""
    ConfigCentral.objects.update_or_create(
        key="partner_referral_page_url_template",
        defaults={"value": "https://example.test/refer?c={partner_code}"},
    )
    resp = _get(client, "/r/open?skip=1", django_capture_on_commit_callbacks)
    assert resp.headers["Location"] == "https://example.test/refer?c=ZMPHZC"


def test_malformed_referral_page_override_falls_back(seeded, client, django_capture_on_commit_callbacks):
    """A stray `{}` in the operator override must not 500 the Skip."""
    ConfigCentral.objects.update_or_create(
        key="partner_referral_page_url_template",
        defaults={"value": "https://example.test/refer?c={}"},
    )
    resp = _get(client, "/r/open?skip=1", django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://signup.zerodha.com/api/lead/?c=ZMPHZC"


def test_valid_id_is_unchanged(seeded, client):
    resp = client.get("/r/RJ4521", **HUMAN)
    assert resp.status_code == 200
    assert ReferralIdentity.objects.count() == 1
    assert ReferralIdentity.objects.get().client_id == "RJ4521"


@pytest.mark.parametrize("path", ["/r/" + "A" * 33, "/r/KITEID", "/r/open", "/r/wa/"])
def test_no_zerodha_url_in_any_body(seeded, client, django_capture_on_commit_callbacks, path):
    html = _get(client, path, django_capture_on_commit_callbacks).content.decode()
    assert "signup.zerodha.com" not in html and "ZMPHZC" not in html
