"""One-tap WhatsApp share link: PR #197 rules that still hold (owner 2026-11-04).

The message text itself is now the two-step text; see test_onetap_whatsapp_two_step.py for
the byte-exact A-D tests. This file keeps the surrounding behaviour pinned.

Only `/{prefix}/share/wa/{client_id}` (and bare `/share/wa/{client_id}`) changed. Its
message now has its own English text, the program's plain no-referrer link
`/{prefix}/open` (PIFS credited, the referrer not) and a bold two-line disclosure.
Owner decisions: D1 "Share without my ID" sends the same message; D2 the referrer's own
opening line still replaces the text; D3 Hindi keeps the shared Hindi wording with the
new link and disclosure.

Everything else stays as it was and is pinned here too: My Referrals, the share hub,
Telegram and X keep the shared message with the referrer's own link. The row-by-row map
the owner approved is the "GoRefer Link Matrix" artifact (rows J1.1, J1.5, J2.1-J2.6,
J3.1-J3.7, J11.4, J11.7).
"""
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.management import call_command
from django.test import Client

from apps.config import preferences as prefkeys
from apps.config.cascade import resolve, set_tenant
from apps.events.models import Event
from apps.referrals.models import ReferralIdentity, ReferralProgram
from apps.tenants.resolve import get_bootstrap_tenant

CID = "RJ4521"
HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.9"}
BOT = {"HTTP_USER_AGENT": "WhatsApp/2.23.20 A"}
SHARE_URLS = pytest.mark.urls("tests.urls_share_intent")

OPEN_LINK = "https://gorefer.in/zerodha/open"
DISCLOSURE = "*Disclosures:*\nhttps://gorefer.in/d/pifs"
_TAIL = "\n\n" + DISCLOSURE


def _expected(register_link: str) -> str:
    """The approved English two-step text for a given step-1 link."""
    return (
        prefkeys.SHARE_ONETAP_WA_MESSAGE_DEFAULT.format(
            register_link=register_link, open_link=OPEN_LINK, program_brand="Zerodha", link=OPEN_LINK
        )
        + _TAIL
    )


EXPECTED_EN = _expected(f"https://gorefer.in/zerodha/r/wa/{CID}")
EXPECTED_NOID = _expected("https://gorefer.in/r/wa")


@pytest.fixture
def tenant(db, settings):
    settings.PUBLIC_BASE_URL = "https://gorefer.in"
    call_command("seed_program")
    return get_bootstrap_tenant()


def _text(resp) -> str:
    return parse_qs(urlparse(resp.headers["Location"]).query)["text"][0]


def _get(path, capture, **headers):
    with capture(execute=True):
        return Client().get(path, **(headers or HUMAN))


def _identity(tenant, client_id=CID):
    program = ReferralProgram.objects.get(tenant=tenant)
    return ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner, client_id=client_id
    )


# --- the changed rows -------------------------------------------------------------


@SHARE_URLS
@pytest.mark.parametrize("path", [f"/share/wa/{CID}", f"/zerodha/share/wa/{CID}"])
def test_one_tap_whatsapp_message_is_the_approved_text(tenant, django_capture_on_commit_callbacks, path):
    """Rows J1.1 / J3.3: the approved two-step message with the referrer's own register link."""
    resp = _get(path, django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("https://wa.me/?text=")
    text = _text(resp)
    assert text == EXPECTED_EN
    assert "ZMPHZC" not in text


@SHARE_URLS
def test_the_share_is_still_recorded_under_the_referrer(tenant, django_capture_on_commit_callbacks):
    """Row J1.1: the referrer's share count is kept even though the friend's link no
    longer carries their id."""
    _get(f"/share/wa/{CID}", django_capture_on_commit_callbacks)
    event = Event.objects.get(event_type="share_intent")
    assert event.referral.referral_identity.client_id == CID
    assert event.metadata == {"channel": "WhatsApp"}


@SHARE_URLS
def test_the_open_link_in_the_message_credits_no_referrer(tenant, django_capture_on_commit_callbacks):
    """Rows J2.3 / J2.6: the friend's tap goes to the plain sign-up page, partner code only."""
    resp = _get("/zerodha/open", django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://signup.zerodha.com/?c=ZMPHZC"
    click = Event.objects.get(event_type="click")
    assert click.referral.referral_identity is None
    assert click.referral.source == "partner_direct"


@SHARE_URLS
def test_referrer_opener_keeps_its_place_with_the_new_link(tenant, django_capture_on_commit_callbacks):
    """Row J3.1 / decision D2."""
    from apps.accounts import opener as opener_service

    opener_service.set_opener(_identity(tenant), "My own words.")
    text = _text(_get(f"/share/wa/{CID}", django_capture_on_commit_callbacks))
    assert text == f"My own words.\n{OPEN_LINK}\n\n{DISCLOSURE}"


@SHARE_URLS
def test_hindi_uses_its_own_two_step_text(tenant, django_capture_on_commit_callbacks):
    """Row J3.2: Hindi has its own two-step text (replaces D3 for the one-tap message)."""
    text = _text(_get(f"/share/wa/{CID}?lang=hi", django_capture_on_commit_callbacks))
    assert text.startswith("*Zerodha खाता खोलने के लिए ये स्टेप्स फ़ॉलो करें*\n\n*स्टेप 1 - अपनी जानकारी रजिस्टर करें*\n")
    assert text.endswith(_TAIL)


@SHARE_URLS
@pytest.mark.parametrize("path", ["/share/wa/KITEID?skip=1", "/zerodha/share/wa/?skip=1"])
def test_share_without_my_id_uses_no_id_register_link(tenant, django_capture_on_commit_callbacks, path):
    """Row J3.7 / decision D1: same message; step 1 is /r/wa; nobody credited; no referrer created."""
    text = _text(_get(path, django_capture_on_commit_callbacks))
    assert text == EXPECTED_NOID
    event = Event.objects.get(event_type="share_intent")
    assert event.referral.referral_identity is None
    assert event.metadata == {"channel": "WhatsApp", "without_id": True}
    assert not ReferralIdentity.objects.exists()


@SHARE_URLS
def test_kite_id_typed_in_the_pop_up_leads_to_the_new_message(tenant, django_capture_on_commit_callbacks):
    """Row J3.6."""
    resp = _get("/share/wa/KITEID?kite_id=AB1234", django_capture_on_commit_callbacks)
    assert resp.headers["Location"] == "/zerodha/share/wa/AB1234"
    assert _text(_get("/zerodha/share/wa/AB1234", django_capture_on_commit_callbacks)) == _expected(
        "https://gorefer.in/zerodha/r/wa/AB1234"
    )


@SHARE_URLS
def test_a_preview_bot_gets_the_target_and_nothing_is_recorded(tenant, django_capture_on_commit_callbacks):
    """Row J3.9."""
    resp = _get(f"/share/wa/{CID}", django_capture_on_commit_callbacks, **BOT)
    assert _text(resp) == EXPECTED_EN
    assert not Event.objects.exists()
    assert not ReferralIdentity.objects.exists()


# --- config (rail E-6): every behaviour above is a cascade key ----------------------


@SHARE_URLS
def test_switch_back_to_the_referrer_link_without_a_deploy(tenant, django_capture_on_commit_callbacks):
    """Rollback path: with the old single-{link} text pasted back, the link choice still works."""
    set_tenant(prefkeys.SHARE_ONETAP_WA_MESSAGE, "Join: {link}", tenant_id=tenant.id)
    set_tenant(prefkeys.SHARE_ONETAP_WA_LINK, "referrer", tenant_id=tenant.id)
    text = _text(_get(f"/share/wa/{CID}", django_capture_on_commit_callbacks))
    assert text == f"Join: https://gorefer.in/zerodha/r/wa/{CID}\n\n{DISCLOSURE}"


@SHARE_URLS
def test_one_tap_text_and_disclosure_are_config(tenant, django_capture_on_commit_callbacks):
    """rail E-6 spot test: the one-tap message and its disclosure line are cascade keys."""
    set_tenant(prefkeys.SHARE_ONETAP_WA_MESSAGE, "Join {program_brand}: {link}", tenant_id=tenant.id)
    set_tenant(prefkeys.SHARE_ONETAP_WA_DISCLOSURE, "Read: {url}", tenant_id=tenant.id)
    text = _text(_get(f"/share/wa/{CID}", django_capture_on_commit_callbacks))
    assert text == f"Join Zerodha: {OPEN_LINK}\n\nRead: https://gorefer.in/d/pifs"


@SHARE_URLS
def test_disclosure_without_its_link_falls_back(tenant, django_capture_on_commit_callbacks):
    set_tenant(prefkeys.SHARE_ONETAP_WA_DISCLOSURE, "No link here", tenant_id=tenant.id)
    text = _text(_get(f"/share/wa/{CID}", django_capture_on_commit_callbacks))
    assert text.endswith("\n\nDisclosures: https://gorefer.in/d/pifs")


def test_seeded_defaults_are_the_approved_values(tenant):
    assert resolve(prefkeys.SHARE_ONETAP_WA_LINK, tenant_id=tenant.id) == "open"
    assert resolve(prefkeys.SHARE_ONETAP_WA_DISCLOSURE, tenant_id=tenant.id) == "*Disclosures:*\n{url}"
    assert "{register_link}" in resolve(prefkeys.SHARE_ONETAP_WA_MESSAGE, tenant_id=tenant.id)


def test_preferences_screen_saves_and_refuses_like_the_shared_message(tenant):
    from apps.dashboard.preferences_service import save_preferences

    notices = save_preferences(tenant, {
        prefkeys.SHARE_ONETAP_WA_LINK: "referrer",
        prefkeys.SHARE_ONETAP_WA_MESSAGE: "No link in this one",
        prefkeys.SHARE_ONETAP_WA_DISCLOSURE: "Missing the url",
    })
    assert resolve(prefkeys.SHARE_ONETAP_WA_LINK, tenant_id=tenant.id) == "referrer"
    assert any("One-tap WhatsApp message" in n and "{register_link}" in n for n in notices)
    assert any("One-tap WhatsApp disclosure line" in n and "{url}" in n for n in notices)
    assert "{register_link}" in resolve(prefkeys.SHARE_ONETAP_WA_MESSAGE, tenant_id=tenant.id)
    assert "{url}" in resolve(prefkeys.SHARE_ONETAP_WA_DISCLOSURE, tenant_id=tenant.id)

    save_preferences(tenant, {prefkeys.SHARE_ONETAP_WA_LINK: "open",
                              prefkeys.SHARE_ONETAP_WA_MESSAGE: "Hi {link}"})
    assert resolve(prefkeys.SHARE_ONETAP_WA_LINK, tenant_id=tenant.id) == "open"
    assert resolve(prefkeys.SHARE_ONETAP_WA_MESSAGE, tenant_id=tenant.id) == "Hi {link}"


def test_preferences_screen_shows_the_one_tap_section(tenant, admin_client):
    body = admin_client.get("/admin-panel/preferences").content.decode()
    for name in ("share_onetap_wa_link", "share_onetap_wa_message", "share_onetap_wa_disclosure"):
        assert f'name="{name}"' in body


# --- the rows that must stay the same -----------------------------------------------


@SHARE_URLS
@pytest.mark.parametrize("ch", ["tg", "x"])
def test_telegram_and_x_keep_the_referrer_link(tenant, django_capture_on_commit_callbacks, ch):
    """Rows J6.1 / J7.1."""
    text = _text(_get(f"/share/{ch}/{CID}", django_capture_on_commit_callbacks))
    assert f"https://gorefer.in/zerodha/r/{ch}/{CID}" in text
    assert OPEN_LINK not in text
    assert text.endswith("\n\nDisclosures: https://gorefer.in/d/pifs")


@SHARE_URLS
def test_telegram_share_without_id_is_unchanged(tenant, django_capture_on_commit_callbacks):
    text = _text(_get("/share/tg/KITEID?skip=1", django_capture_on_commit_callbacks))
    assert "https://gorefer.in/zerodha/r/open" in text
    assert OPEN_LINK + "\n" not in text


def test_my_referrals_keeps_the_shared_message(tenant):
    """Row J4.2."""
    from apps.accounts.selfview import my_referrals_ctx

    text = my_referrals_ctx(tenant, CID)["share_text"]
    assert f"https://gorefer.in/zerodha/r/wa/{CID}" in text
    assert OPEN_LINK not in text
    assert text.endswith("\n\nDisclosures: https://gorefer.in/d/pifs")


@pytest.mark.urls("tests.urls_share_hub")
def test_share_hub_keeps_the_shared_message(tenant):
    """Rows J5.1-J5.7."""
    from apps.accounts.hub import hub_ctx
    from apps.accounts.records_link import mint_records_token

    identity = _identity(tenant)
    ctx = hub_ctx(identity, mint_records_token(identity))
    assert f"https://gorefer.in/zerodha/r/wa/{CID}" in ctx["share_message"]
    assert OPEN_LINK not in ctx["share_message"]
    assert ctx["my_link"] == f"https://gorefer.in/zerodha/r/wa/{CID}"
