"""Tagged partner links: /open/{channel}/{language} (owner 2026-11-10).

A video link such as /zerodha/open/yt/hi is the plain partner link plus two tags. The
tags are recorded on the click (metadata channel + language) so each video language can
be counted separately, and they never reach the partner.
"""
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.config import preferences as prefkeys
from apps.config.cascade import set_tenant
from apps.dashboard import queries
from apps.events.models import Event
from apps.referrals.models import Referral
from apps.tenants.models import Tenant

HUMAN = "Mozilla/5.0 (Android)"
BOT = "facebookexternalhit/1.1"


@pytest.fixture
def seeded(db):
    call_command("seed_program")


def _open(path, ua=HUMAN):
    return Client().get(path, HTTP_USER_AGENT=ua, REMOTE_ADDR="203.0.113.7")


def _clicks():
    return list(Event.objects.filter(event_type="click").order_by("id"))


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("path", ["/open/yt/hi", "/zerodha/open/yt/hi"])
def test_tagged_link_records_channel_and_language(seeded, path):
    plain = _open("/open")
    resp = _open(path)
    assert resp.status_code == 302
    assert resp.headers["Location"] == plain.headers["Location"]  # same destination, no tags leaked
    click = _clicks()[-1]
    assert click.metadata == {"channel": "YouTube", "language": "Hindi"}
    assert click.referral.source == "partner_direct"
    assert click.referral.referral_identity is None  # never a synthetic referrer


@pytest.mark.django_db(transaction=True)
def test_channel_only_and_plain_links_carry_no_language(seeded):
    _open("/zerodha/open/yt")
    _open("/zerodha/open")
    yt, plain = _clicks()
    assert yt.metadata == {"channel": "YouTube"}
    assert plain.metadata == {}


@pytest.mark.django_db(transaction=True)
def test_unknown_language_still_redirects_and_is_recorded_as_other(seeded):
    resp = _open("/zerodha/open/yt/xx")
    assert resp.status_code == 302
    assert _clicks()[-1].metadata == {"channel": "YouTube", "language": prefkeys.LINK_LANGUAGE_OTHER}


@pytest.mark.django_db(transaction=True)
def test_language_labels_come_from_config(seeded):
    """Rail E-6: the code -> label map is a cascade key, so a language is added without a deploy."""
    tenant = Tenant.objects.get()
    set_tenant(prefkeys.LINK_LANGUAGE_LABELS, {"hi": "Hindi", "mai": "Maithili"}, tenant_id=tenant.id)
    _open("/zerodha/open/yt/mai")
    assert _clicks()[-1].metadata["language"] == "Maithili"


@pytest.mark.django_db(transaction=True)
def test_crawler_on_tagged_link_writes_nothing(seeded):
    resp = _open("/zerodha/open/yt/hi", ua=BOT)
    assert resp.status_code == 200  # preview card, not a redirect
    assert not _clicks()
    assert not Referral.objects.filter(source="partner_direct").exists()


def test_unknown_program_prefix_is_404(seeded):
    assert _open("/notaprogram/open/yt/hi").status_code == 404


@pytest.mark.django_db(transaction=True)
def test_dashboard_splits_partner_link_clicks_by_channel_and_language(seeded):
    for path in ["/zerodha/open/yt/hi", "/zerodha/open/yt/hi", "/zerodha/open/yt/mr", "/zerodha/open"]:
        _open(path)
    _open("/r/RJ4521")  # a referral click is a different population; not counted here
    found = queries.partner_link_clicks(Tenant.objects.get())
    rows = {(r["channel"], r["language"]): r["clicks"] for r in found}
    assert rows == {("YouTube", "Hindi"): 2, ("YouTube", "Marathi"): 1, ("Direct", ""): 1}

    get_user_model().objects.create_user(username="a@pifs.in", password="pw12345!", is_staff=True)
    c = Client()
    c.login(username="a@pifs.in", password="pw12345!")
    html = c.get("/admin-panel/").content.decode()
    assert "Partner link clicks by source" in html
    assert "Hindi" in html and "Marathi" in html
