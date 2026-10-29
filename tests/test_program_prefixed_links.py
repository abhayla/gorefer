"""Program-prefixed public links (owner decision 2026-10-29).

`gorefer.in/{url_prefix}/open`, `/{url_prefix}/r/open`, `/{url_prefix}/r/{client_id}` and
`/{url_prefix}/r/{channel}/{client_id}` (Zerodha's word: `zerodha`) are TWINS of the bare
links — same view, same response, same journey writes. The bare links are unchanged.
The word is data on ReferralProgram, never a route literal (CLAUDE.md §4). Every link
GoRefer GENERATES now carries the word; with a blank word it falls back to the bare form.
"""
import re

import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event
from apps.referrals import links
from apps.referrals import recipient_identity as ri
from apps.referrals.models import Referral, ReferralIdentity, ReferralProgram
from apps.referrals.share_intent_service import kit_message, tracked_link
from apps.tenants.models import Tenant

HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.9"}
BOT = {"HTTP_USER_AGENT": "WhatsApp/2.23.20 A"}
CID = "RJ4521"


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def tenant(seeded):
    return Tenant.objects.get(slug="pifs")


@pytest.fixture
def client():
    return Client()


def _get(client, path, capture, **kw):
    with capture(execute=True):
        return client.get(path, **(kw or HUMAN))


def _writes():
    return (
        ReferralIdentity.objects.count(),
        sorted(Referral.objects.values_list("source", flat=True)),
        sorted(Event.objects.values_list("event_type", flat=True)),
    )


def _clear_writes():
    Event.objects.all().delete()
    Referral.objects.all().delete()
    ReferralIdentity.objects.all().delete()


# --- the seeded data ----------------------------------------------------------------


def test_seeded_program_carries_the_zerodha_link_word(tenant):
    assert ReferralProgram.objects.get(tenant=tenant).url_prefix == "zerodha"


# --- new links behave exactly like their bare twins ---------------------------------

TWINS = [
    ("/open", "/zerodha/open"),
    ("/r/open", "/zerodha/r/open"),
    ("/r/OPEN", "/zerodha/r/OPEN"),
    (f"/r/{CID}", f"/zerodha/r/{CID}"),
    ("/r/ZERODHAID", "/zerodha/r/ZERODHAID"),          # placeholder passes through (T-574)
    (f"/r/wa/{CID}", f"/zerodha/r/wa/{CID}"),
    ("/r/wa/open", "/zerodha/r/wa/open"),
    (f"/r/{CID}/continue", f"/zerodha/r/{CID}/continue"),
    (f"/r/wa/{CID}/continue", f"/zerodha/r/wa/{CID}/continue"),
    ("/r/", "/zerodha/r/"),
    ("/r", "/zerodha/r"),
]


@pytest.mark.parametrize("bare,prefixed", TWINS)
def test_prefixed_link_matches_its_bare_twin(seeded, client, django_capture_on_commit_callbacks,
                                             bare, prefixed):
    old = _get(client, bare, django_capture_on_commit_callbacks)
    old_writes = _writes()
    _clear_writes()
    new = _get(Client(), prefixed, django_capture_on_commit_callbacks)
    assert new.status_code == old.status_code
    assert new.headers.get("Location") == old.headers.get("Location")
    assert _writes() == old_writes


@pytest.mark.parametrize("path,expected_location", [
    ("/zerodha/open", "https://signup.zerodha.com/?c=ZMPHZC"),
    ("/zerodha/r/open", "https://signup.zerodha.com/api/lead/?c=ZMPHZC"),
    ("/zerodha/r/ZERODHAID", "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=ZERODHAID"),
    (f"/zerodha/r/{CID}/continue", f"https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={CID}"),
])
def test_prefixed_redirect_destinations(seeded, client, django_capture_on_commit_callbacks,
                                        path, expected_location):
    resp = _get(client, path, django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    assert resp.headers["Location"] == expected_location


def test_prefixed_referral_link_renders_landing_and_creates_the_journey(
    seeded, client, django_capture_on_commit_callbacks
):
    resp = _get(client, f"/zerodha/r/{CID}", django_capture_on_commit_callbacks)
    assert resp.status_code == 200
    assert ReferralIdentity.objects.filter(client_id=CID).count() == 1
    assert Referral.objects.filter(source="referral_link").count() == 1


def test_prefix_is_case_insensitive(seeded, client, django_capture_on_commit_callbacks):
    for path in ("/Zerodha/open", "/ZERODHA/r/open", f"/ZeRoDhA/r/{CID}"):
        assert _get(Client(), path, django_capture_on_commit_callbacks).status_code in (200, 302)


def test_bot_on_prefixed_link_gets_preview_and_writes_nothing(
    seeded, client, django_capture_on_commit_callbacks
):
    for path in (f"/zerodha/r/{CID}", "/zerodha/open", "/zerodha/r/open"):
        resp = _get(client, path, django_capture_on_commit_callbacks, **BOT)
        assert resp.status_code == 200
    assert _writes() == (0, [], [])


# --- only the active program's word is a route -----------------------------------------


@pytest.mark.parametrize("path", [
    "/groww/open", f"/groww/r/{CID}", "/groww/r/open", f"/groww/r/wa/{CID}", "/groww/r/",
])
def test_unknown_prefix_is_404_and_writes_nothing(seeded, client, django_capture_on_commit_callbacks, path):
    assert _get(client, path, django_capture_on_commit_callbacks).status_code == 404
    assert _writes() == (0, [], [])


def test_blank_prefix_means_no_prefixed_links(tenant, client, django_capture_on_commit_callbacks):
    ReferralProgram.objects.filter(tenant=tenant).update(url_prefix="")
    assert _get(client, "/zerodha/open", django_capture_on_commit_callbacks).status_code == 404
    assert _get(client, f"/zerodha/r/{CID}", django_capture_on_commit_callbacks).status_code == 404
    # bare links are unaffected
    assert _get(client, "/open", django_capture_on_commit_callbacks).status_code == 302


def test_prefix_word_is_data_not_a_route_literal(tenant, client, django_capture_on_commit_callbacks):
    """Rename the word in data -> the new word works, the old one 404s. No code change."""
    ReferralProgram.objects.filter(tenant=tenant).update(url_prefix="zd")
    assert _get(client, "/zd/open", django_capture_on_commit_callbacks).status_code == 302
    assert _get(client, "/zerodha/open", django_capture_on_commit_callbacks).status_code == 404


def test_post_to_prefixed_link_is_405(seeded, client):
    assert client.post(f"/zerodha/r/{CID}").status_code == 405
    assert client.post("/zerodha/open").status_code == 405


# --- generated links use the prefixed form -------------------------------------------


def test_link_builder(tenant):
    assert links.referral_path(CID, tenant=tenant) == f"/zerodha/r/{CID}"
    assert links.referral_path(CID, channel="wa", tenant=tenant.id) == f"/zerodha/r/wa/{CID}"
    assert links.partner_direct_path(tenant=tenant) == "/zerodha/open"


def test_link_builder_falls_back_to_bare_form_without_a_prefix(tenant):
    ReferralProgram.objects.filter(tenant=tenant).update(url_prefix="")
    assert links.referral_path(CID, tenant=tenant) == f"/r/{CID}"
    assert links.referral_path(CID, channel="wa", tenant=tenant) == f"/r/wa/{CID}"
    assert links.partner_direct_path(tenant=tenant) == "/open"


def test_link_builder_with_no_program_falls_back_to_bare_form(db):
    assert links.referral_path(CID) == f"/r/{CID}"
    assert links.partner_direct_path() == "/open"


def test_share_kit_tracked_link_is_prefixed(tenant, settings):
    settings.PUBLIC_BASE_URL = "https://gorefer.in"
    assert tracked_link("wa", CID, tenant_id=tenant.id) == f"https://gorefer.in/zerodha/r/wa/{CID}"
    assert f"https://gorefer.in/zerodha/r/wa/{CID}" in kit_message("wa", CID, tenant.id)


def test_followup_nudge_links_are_prefixed(tenant, settings):
    settings.PUBLIC_BASE_URL = "https://gorefer.in"
    with_referrer = ri.RecipientIdentity(role=ri.ROLE_PROSPECT, referrer_client_id=CID)
    unknown = ri.RecipientIdentity()
    assert ri.nudge_link_for(with_referrer, tenant_id=tenant.id) == f"gorefer.in/zerodha/r/wa/{CID}"
    assert ri.nudge_link_for(unknown, tenant_id=tenant.id) == "gorefer.in/zerodha/open"


def test_landing_og_url_is_prefixed(seeded, client, settings, django_capture_on_commit_callbacks):
    settings.PUBLIC_BASE_URL = "https://gorefer.in"
    body = _get(client, f"/r/{CID}", django_capture_on_commit_callbacks).content.decode()
    og = re.search(r"""<meta property=["']og:url["'] content=["']([^"']*)["']""", body)
    assert og is not None and og.group(1) == f"https://gorefer.in/zerodha/r/{CID}"


def test_my_referrals_and_profile_links_are_prefixed(tenant, client, django_capture_on_commit_callbacks):
    from apps.accounts.selfview import my_referrals_ctx
    from apps.dashboard import profile

    _get(client, f"/r/{CID}", django_capture_on_commit_callbacks)  # create the identity
    ctx = my_referrals_ctx(tenant, CID)
    assert ctx["my_link"] == f"https://gorefer.in/zerodha/r/{CID}"
    assert f"https://gorefer.in/zerodha/r/wa/{CID} " in ctx["share_text"]
    cards = profile.per_link_cards(tenant, CID)
    assert cards and all(card["link"] == f"gorefer.in/zerodha/r/{CID}" for card in cards)


# --- share-intent twins (flag-on mount mirrored by tests.urls_share_intent) ----------

SHARE_TWINS = [
    (f"/share/wa/{CID}", f"/zerodha/share/wa/{CID}"),
    ("/share/wa/", "/zerodha/share/wa/"),
    ("/share/wa", "/zerodha/share/wa"),
]


@pytest.mark.urls("tests.urls_share_intent")
@pytest.mark.parametrize("bare,prefixed", SHARE_TWINS)
def test_prefixed_share_matches_its_bare_twin(seeded, django_capture_on_commit_callbacks, bare, prefixed):
    old = _get(Client(), bare, django_capture_on_commit_callbacks)
    old_writes = _writes()
    _clear_writes()
    new = _get(Client(), prefixed, django_capture_on_commit_callbacks)
    assert new.status_code == old.status_code
    assert new.headers.get("Location") == old.headers.get("Location")
    assert _writes() == old_writes


@pytest.mark.urls("tests.urls_share_intent")
def test_prefixed_share_is_a_real_wa_me_redirect(seeded, django_capture_on_commit_callbacks):
    resp = _get(Client(), f"/zerodha/share/wa/{CID}", django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("https://wa.me/")


@pytest.mark.urls("tests.urls_share_intent")
def test_prefixed_share_prefix_is_case_insensitive(seeded, django_capture_on_commit_callbacks):
    old = _get(Client(), f"/share/wa/{CID}", django_capture_on_commit_callbacks)
    _clear_writes()
    new = _get(Client(), f"/Zerodha/share/wa/{CID}", django_capture_on_commit_callbacks)
    assert (new.status_code, new.headers.get("Location")) == (old.status_code, old.headers.get("Location"))


@pytest.mark.urls("tests.urls_share_intent")
@pytest.mark.parametrize("path", [f"/groww/share/wa/{CID}", "/groww/share/wa/", "/groww/share/wa"])
def test_prefixed_share_unknown_prefix_is_404_and_writes_nothing(
    seeded, django_capture_on_commit_callbacks, path
):
    assert _get(Client(), path, django_capture_on_commit_callbacks).status_code == 404
    assert _writes() == (0, [], [])


@pytest.mark.urls("tests.urls_share_intent")
def test_prefixed_share_post_is_405(seeded):
    assert Client().post(f"/zerodha/share/wa/{CID}").status_code == 405


def test_prefixed_share_routes_absent_when_flag_off(seeded, client, django_capture_on_commit_callbacks):
    """Default urlconf = flag off (ENABLE_SHARE_INTENT defaults False): no bare, no prefixed share route."""
    assert _get(client, f"/share/wa/{CID}", django_capture_on_commit_callbacks).status_code == 404
    assert _get(client, f"/zerodha/share/wa/{CID}", django_capture_on_commit_callbacks).status_code == 404
