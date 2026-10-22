"""T-574 — /r/<unknown value> passes through to the partner; /r/open is the reserved partner link.

Owner decision 2026-10-22 (SPEC CHANGE to the 2026-07-27 strict-id behaviour): a value that
fails the strict Zerodha-id pattern is NOT blocked with a 400 — the visitor is 302'd to the
partner's lead URL with r=<raw value> (URL-encoded) and NO referrer identity is created.
"""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.config.models import ConfigCentral
from apps.events.models import Event
from apps.referrals.models import Referral, ReferralIdentity

HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.9"}
BOT = {"HTTP_USER_AGENT": "WhatsApp/2.23.20 A"}
LEAD = "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r="
REFERRAL_PAGE = "https://signup.zerodha.com/api/lead/?c=ZMPHZC"


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


def _get(client, path, capture, **kw):
    with capture(execute=True):
        return client.get(path, **(kw or HUMAN))


def _assert_passthrough(resp, expected_r):
    assert resp.status_code == 302
    assert resp.headers["Location"] == LEAD + expected_r
    assert ReferralIdentity.objects.count() == 0
    assert Referral.objects.filter(source="referral_link").count() == 0
    pd = Referral.objects.filter(source="partner_direct", referral_identity__isnull=True)
    assert pd.count() == 1
    assert Event.objects.count() == 1
    ev = Event.objects.get()
    assert ev.event_type == "click"
    assert ev.referral_id == pd.get().pk


@pytest.mark.parametrize("path,r", [
    ("/r/ZERODHAID", "ZERODHAID"),
    ("/r/XYZ", "XYZ"),
    ("/r/zerodhaid", "zerodhaid"),
    ("/r/AB%20CD", "AB%20CD"),
    ("/r/wa/ZERODHAID", "ZERODHAID"),
    ("/r/ZERODHAID/continue", "ZERODHAID"),
    ("/r/wa/ZERODHAID/continue", "ZERODHAID"),
])
def test_unknown_value_passes_through(seeded, client, django_capture_on_commit_callbacks, path, r):
    resp = _get(client, path, django_capture_on_commit_callbacks)
    _assert_passthrough(resp, r)


def test_passthrough_in_direct_landing_mode_is_same(seeded, client, django_capture_on_commit_callbacks):
    ConfigCentral.objects.update_or_create(key="landing_mode", defaults={"value": "direct"})
    resp = _get(client, "/r/ZERODHAID", django_capture_on_commit_callbacks)
    _assert_passthrough(resp, "ZERODHAID")


def test_33_chars_is_still_400(seeded, client, django_capture_on_commit_callbacks):
    resp = _get(client, "/r/" + "A" * 33, django_capture_on_commit_callbacks)
    assert resp.status_code == 400
    assert ReferralIdentity.objects.count() == 0
    assert Referral.objects.count() == 0
    assert Event.objects.count() == 0


def test_32_chars_passes(seeded, client, django_capture_on_commit_callbacks):
    resp = _get(client, "/r/" + "A" * 32, django_capture_on_commit_callbacks)
    _assert_passthrough(resp, "A" * 32)


def test_bot_on_unknown_id_gets_preview_no_writes(seeded, client, django_capture_on_commit_callbacks):
    resp = _get(client, "/r/ZERODHAID", django_capture_on_commit_callbacks, **BOT)
    assert resp.status_code == 200
    assert Event.objects.count() == 0
    assert Referral.objects.count() == 0
    assert ReferralIdentity.objects.count() == 0


@pytest.mark.parametrize("path", ["/r/open", "/r/OPEN", "/r/Open", "/r/wa/open", "/r/wa/OPEN"])
def test_reserved_open_goes_to_empty_referral_box(seeded, client, django_capture_on_commit_callbacks, path):
    resp = _get(client, path, django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    assert resp.headers["Location"] == REFERRAL_PAGE
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
    """rail E-6 spot test: the /r/open destination is config, not a literal."""
    ConfigCentral.objects.update_or_create(
        key="partner_referral_page_url_template",
        defaults={"value": "https://example.test/refer?c={partner_code}"},
    )
    resp = _get(client, "/r/open", django_capture_on_commit_callbacks)
    assert resp.headers["Location"] == "https://example.test/refer?c=ZMPHZC"


def test_valid_id_is_unchanged(seeded, client):
    resp = client.get("/r/RJ4521", **HUMAN)
    assert resp.status_code == 200
    assert ReferralIdentity.objects.count() == 1
    assert ReferralIdentity.objects.get().client_id == "RJ4521"


def test_no_zerodha_url_in_any_body(seeded, client, django_capture_on_commit_callbacks):
    resp = _get(client, "/r/" + "A" * 33, django_capture_on_commit_callbacks)
    html = resp.content.decode()
    assert "signup.zerodha.com" not in html and "ZMPHZC" not in html
