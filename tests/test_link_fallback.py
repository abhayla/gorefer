"""A broken public link never shows an error page (owner decision 2026-11-10).

It redirects to the default account-opening link, which records the click and sends the
visitor to the partner. Signed-in pages, the API and file-like paths keep their 404.
"""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.config import preferences as prefkeys
from apps.config.cascade import set_tenant
from apps.events.models import Event
from apps.referrals.models import ReferralProgram
from apps.tenants.models import Tenant

HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.7"}


@pytest.fixture
def seeded(db):
    call_command("seed_program")


def _get(path):
    return Client().get(path, **HUMAN)


@pytest.mark.parametrize("path", [
    "/zeroda/open",            # mistyped program word
    "/groww/r/wa/RJ4521",      # a program this site does not serve
    "/zerodha/opn",            # mistyped link
    "/zerodha/open/yt/hi/extra",
    "/anything/at/all",
    "/share/li/RJ4521",        # a share channel that is not served
])
def test_broken_link_goes_to_the_default_open_link(seeded, path):
    resp = _get(path)
    assert (resp.status_code, resp.headers["Location"]) == (302, "/zerodha/open")
    assert Event.objects.count() == 0  # the fallback itself records nothing


@pytest.mark.django_db(transaction=True)
def test_following_the_fallback_reaches_the_partner_and_counts_one_click(seeded):
    client = Client()
    resp = client.get("/zeroda/open", follow=False, **HUMAN)
    final = client.get(resp.headers["Location"], **HUMAN)
    assert final.status_code == 302
    assert final.headers["Location"] == _get("/zerodha/open").headers["Location"]
    assert Event.objects.filter(event_type="click", referral__source="partner_direct").count() == 2


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("path", ["/Zerodha/Open/YT/HI", "/zerodha/open/yt/hi/", "/ZERODHA/OPEN/YT/HI/"])
def test_wrong_case_or_trailing_slash_keeps_the_tags(seeded, path):
    client = Client()
    resp = client.get(path, **HUMAN)
    assert (resp.status_code, resp.headers["Location"]) == (302, "/zerodha/open/yt/hi")
    client.get(resp.headers["Location"], **HUMAN)
    assert Event.objects.get(event_type="click").metadata == {"channel": "YouTube", "language": "Hindi"}


def test_no_program_prefix_falls_back_to_the_bare_link(seeded):
    ReferralProgram.objects.update(url_prefix="")
    resp = _get("/zerodha/open")
    assert (resp.status_code, resp.headers["Location"]) == (302, "/open")


@pytest.mark.parametrize("path", [
    "/api/nope", "/admin-panel/nope", "/my/nope", "/login/nope", "/d/no-such-page",
    "/wp-login.php", "/.env", "/favicon.ico", "/static/missing.css",
])
def test_private_and_file_paths_keep_their_404(seeded, path):
    assert _get(path).status_code in (404, 302)
    resp = _get(path)
    assert resp.headers.get("Location", "") not in ("/zerodha/open", "/open")


def test_non_get_is_not_redirected(seeded):
    assert Client().post("/anything/at/all").status_code == 404


def test_switch_off_restores_plain_404(seeded):
    """Rail E-6: the behaviour is a cascade key, changeable without a deploy."""
    set_tenant(prefkeys.LINK_FALLBACK_ENABLED, False, tenant_id=Tenant.objects.get().id)
    assert _get("/zeroda/open").status_code == 404
