"""Channel-only links (`/r/wa/`, `/r/wa`, `/zerodha/r/wa/`, ...) behave exactly like `/r/open`.

Owner decision 2026-10-29 (SPEC CHANGE to 06-API 4.1 step 1: a value equal to a configured
channel code is no longer passed through as r=<value>). Since 2026-11-02 these show the Kite
ID pop-up; its Skip is the old 302 to the partner referral page (where `/r/open` itself still
goes directly), with the channel recorded on the click. Real ids and `/open` are unchanged.
"""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event
from apps.referrals.models import Referral, ReferralIdentity
from tests.link_fallback_helpers import fell_back

HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.9"}
BOT = {"HTTP_USER_AGENT": "WhatsApp/2.23.20 A"}
REFERRAL_PAGE = "https://signup.zerodha.com/api/lead/?c=ZMPHZC"


@pytest.fixture
def seeded(db):
    call_command("seed_program")


def _get(path, capture, **kw):
    with capture(execute=True):
        return Client().get(path, **(kw or HUMAN))


def _state():
    ev = Event.objects.order_by("id").first()
    return (
        ReferralIdentity.objects.count(),
        Referral.objects.filter(source="partner_direct", referral_identity__isnull=True).count(),
        Event.objects.count(),
        (ev.event_type, ev.metadata) if ev else None,
    )


@pytest.mark.parametrize("path,channel_meta", [
    ("/r/wa/", "WhatsApp"),
    ("/r/wa", "WhatsApp"),
    ("/r/WA", "WhatsApp"),
    ("/r/yt/", "YouTube"),
    ("/r/yt", "YouTube"),
    ("/zerodha/r/wa/", "WhatsApp"),
    ("/zerodha/r/wa", "WhatsApp"),
    ("/zerodha/r/yt/", "YouTube"),
])
def test_channel_only_equals_open(seeded, django_capture_on_commit_callbacks, path, channel_meta):
    # Shown: the pop-up, and nothing but its view event recorded.
    resp = _get(path, django_capture_on_commit_callbacks)
    assert resp.status_code == 200
    assert "Who referred you?" in resp.content.decode()
    assert not Event.objects.filter(event_type="click").exists()
    Event.objects.all().delete()
    # Skip: the partner referral page with the channel recorded on the click.
    resp = _get(path + "?skip=1", django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    assert resp.headers["Location"] == REFERRAL_PAGE
    assert _state() == (0, 1, 1, ("click", {"channel": channel_meta}))


@pytest.mark.parametrize("path", ["/r/wa/", "/r/wa", "/zerodha/r/wa/", "/zerodha/r/wa"])
def test_bot_behaves_like_open_bot(seeded, django_capture_on_commit_callbacks, path):
    open_path = "/zerodha/r/open" if path.startswith("/zerodha") else "/r/open"
    ref = _get(open_path, django_capture_on_commit_callbacks, **BOT)
    n_ref = (Referral.objects.count(), Event.objects.count())
    resp = _get(path, django_capture_on_commit_callbacks, **BOT)
    assert (resp.status_code, resp.get("Location")) == (ref.status_code, ref.get("Location"))
    assert (Referral.objects.count(), Event.objects.count()) == n_ref == (0, 0)
    assert ReferralIdentity.objects.count() == 0


def test_wrong_prefix_falls_back_without_writes(seeded, django_capture_on_commit_callbacks):
    for p in ("/groww/r/wa/", "/groww/r/wa"):
        assert fell_back(_get(p, django_capture_on_commit_callbacks))
    assert (Referral.objects.count(), Event.objects.count()) == (0, 0)


@pytest.mark.parametrize("path", ["/r/", "/r", "/zerodha/r/", "/zerodha/r"])
def test_bare_r_shows_the_prompt(seeded, django_capture_on_commit_callbacks, path):
    resp = _get(path, django_capture_on_commit_callbacks)
    assert resp.status_code == 200
    assert "Who referred you?" in resp.content.decode()
    # only its own view event, never a click or a journey
    assert not Event.objects.filter(event_type="click").exists()
    assert Referral.objects.count() == 0


@pytest.mark.parametrize("path", ["/r/ZERODHAID", "/r/XYZ", "/r/wa/ZERODHAID"])
def test_other_unknown_values_show_the_prompt(seeded, django_capture_on_commit_callbacks, path):
    resp = _get(path, django_capture_on_commit_callbacks)
    assert resp.status_code == 200
    assert "Who referred you?" in resp.content.decode()


def test_channel_referral_with_real_id_unchanged(seeded, django_capture_on_commit_callbacks):
    resp = _get("/r/wa/RJ4521", django_capture_on_commit_callbacks)
    assert resp.status_code == 200  # branded landing for a real id
    assert ReferralIdentity.objects.filter(client_id="RJ4521").exists()


@pytest.mark.parametrize("path", ["/r/abc/", "/r/foo/", "/r/open/", "/zerodha/r/abc/", "/zerodha/r/open/"])
def test_unknown_channel_slash_falls_back_no_writes(seeded, django_capture_on_commit_callbacks, path):
    assert fell_back(_get(path, django_capture_on_commit_callbacks))
    assert (Referral.objects.count(), Event.objects.count(), ReferralIdentity.objects.count()) == (0, 0, 0)
