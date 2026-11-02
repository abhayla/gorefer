"""Kite ID pop-up (owner decision 2026-11-02).

Every referral or share link whose id is missing, malformed or an obvious placeholder
(/r/wa/KITEID, /r/wa/, /r/, /r/open, /share/wa/YOUR_KITE_ID, /share/wa/ and every
/{program}/ twin) shows ONE pop-up asking for the Kite ID:
  - a valid id   -> 302 to the canonical link (which then records the click as before);
  - Skip         -> referral links: the partner referral page with an empty box, partner
                    code server-side, no referrer; share links: WhatsApp with the share
                    message carrying the no-referrer link;
  - placeholders are never saved as referrers, from any link.
Real ids, /open and /zerodha/open are unchanged; crawlers still get the preview card.
"""
from urllib.parse import unquote

import pytest
from django.core.management import call_command
from django.test import Client

from apps.config import preferences as prefkeys
from apps.config.cascade import resolve, set_tenant
from apps.events.models import Event
from apps.referrals import links
from apps.referrals.models import Referral, ReferralIdentity
from apps.referrals.validators import InvalidClientId, validate_client_id_for
from apps.tenants.resolve import get_bootstrap_tenant
from gorefer.flags import SHARE_CHANNEL_LABELS

HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.9"}
BOT = {"HTTP_USER_AGENT": "WhatsApp/2.23.20 A"}
REF_TITLE = prefkeys.KITE_PROMPT_REF_TITLE_DEFAULT
SHARE_TITLE = prefkeys.KITE_PROMPT_SHARE_TITLE_DEFAULT
REFERRAL_PAGE = "https://signup.zerodha.com/api/lead/?c=ZMPHZC"


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def tenant(seeded):
    return get_bootstrap_tenant()


def _get(path, capture, **kw):
    with capture(execute=True):
        return Client().get(path, **(kw or HUMAN))


def _no_referrer_saved():
    return ReferralIdentity.objects.count() == 0


# --- which links show it ----------------------------------------------------------

REFERRAL_PROMPT_PATHS = [
    "/r/", "/r", "/r/wa/", "/r/wa", "/r/KITEID", "/r/wa/KITEID", "/r/YOUR_KITE_ID",
    "/r/wa/YOUR_KITE_ID", "/r/ZERODHAID", "/r/KITEID/continue", "/r/wa/KITEID/continue",
    "/r/" + "A" * 40,
]


@pytest.mark.parametrize("path", REFERRAL_PROMPT_PATHS + ["/zerodha" + p for p in REFERRAL_PROMPT_PATHS])
def test_referral_links_without_a_usable_id_show_the_referrer_prompt(
    seeded, django_capture_on_commit_callbacks, path
):
    resp = _get(path, django_capture_on_commit_callbacks)
    body = resp.content.decode()
    assert resp.status_code == 200
    assert REF_TITLE in body
    assert 'name="kite_id"' in body
    assert "?skip=1" in body
    assert _no_referrer_saved()
    assert not Event.objects.filter(event_type="click").exists()


SHARE_PROMPT_PATHS = ["/share/wa/", "/share/wa", "/share/wa/KITEID", "/share/wa/YOUR_KITE_ID",
                      "/share/wa/open", "/share/wa/AB"]


@pytest.mark.urls("tests.urls_share_intent")
@pytest.mark.parametrize("path", SHARE_PROMPT_PATHS + ["/zerodha" + p for p in SHARE_PROMPT_PATHS])
def test_share_links_without_a_usable_id_show_the_sharer_prompt(
    seeded, django_capture_on_commit_callbacks, path
):
    resp = _get(path, django_capture_on_commit_callbacks)
    assert resp.status_code == 200
    assert SHARE_TITLE in resp.content.decode()
    assert _no_referrer_saved()
    assert not Event.objects.filter(event_type="share_intent").exists()


@pytest.mark.parametrize("path", ["/r/open", "/zerodha/r/open", "/r/wa/open", "/zerodha/r/fb/OPEN"])
def test_open_is_not_prompted(seeded, django_capture_on_commit_callbacks, path):
    """/r/open is the deliberate no-referrer link (owner 2026-11-02): no pop-up, the same
    direct 302 to the partner referral page as before."""
    resp = _get(path, django_capture_on_commit_callbacks)
    assert (resp.status_code, resp.headers["Location"]) == (302, REFERRAL_PAGE)
    assert _no_referrer_saved()


@pytest.mark.parametrize("path,location", [
    ("/r/RJ4521/continue", REFERRAL_PAGE + "&r=RJ4521"),
    ("/open", "https://signup.zerodha.com/?c=ZMPHZC"),
    ("/zerodha/open", "https://signup.zerodha.com/?c=ZMPHZC"),
])
def test_links_with_a_real_id_and_open_are_unchanged(
    seeded, django_capture_on_commit_callbacks, path, location
):
    resp = _get(path, django_capture_on_commit_callbacks)
    assert (resp.status_code, resp.headers["Location"]) == (302, location)


def test_real_id_landing_is_unchanged(seeded, django_capture_on_commit_callbacks):
    resp = _get("/r/wa/RJ4521", django_capture_on_commit_callbacks)
    assert resp.status_code == 200
    assert REF_TITLE not in resp.content.decode()
    assert ReferralIdentity.objects.filter(client_id="RJ4521").exists()


@pytest.mark.urls("tests.urls_share_intent")
def test_share_with_a_real_id_is_unchanged(seeded, django_capture_on_commit_callbacks):
    resp = _get("/share/wa/RJ4521", django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    assert "gorefer.in%2Fzerodha%2Fr%2Fwa%2FRJ4521" in resp.headers["Location"]


@pytest.mark.parametrize("path", ["/r/wa/KITEID", "/r/", "/r/open", "/r/wa/"])
def test_crawlers_get_the_preview_card_not_the_prompt(seeded, django_capture_on_commit_callbacks, path):
    resp = _get(path, django_capture_on_commit_callbacks, **BOT)
    assert resp.status_code == 200
    assert 'name="kite_id"' not in resp.content.decode()
    assert Event.objects.count() == 0 and Referral.objects.count() == 0


@pytest.mark.urls("tests.urls_share_intent")
def test_unsupported_share_channel_is_unchanged(seeded, django_capture_on_commit_callbacks):
    assert _get("/share/xx/KITEID", django_capture_on_commit_callbacks).status_code == 404
    body = _get("/share/xx/", django_capture_on_commit_callbacks).content.decode()
    assert SHARE_TITLE not in body and "wa.me/" in body  # the T-122 help page


def test_unknown_program_word_still_404s(seeded, django_capture_on_commit_callbacks):
    for path in ("/groww/r/wa/KITEID", "/groww/r/", "/groww/r/open"):
        assert _get(path, django_capture_on_commit_callbacks).status_code == 404


# --- entering an id -----------------------------------------------------------------

@pytest.mark.parametrize("path,entered,target", [
    ("/r/wa/KITEID", "AB1234", "/zerodha/r/wa/AB1234"),
    ("/r/wa/KITEID", " ab 1234 ", "/zerodha/r/wa/AB1234"),   # spaces + lowercase forgiven
    ("/r/", "AB1234", "/zerodha/r/AB1234"),
    ("/r/wa/", "AB1234", "/zerodha/r/wa/AB1234"),
    ("/zerodha/r/yt/KITEID", "AB1234", "/zerodha/r/yt/AB1234"),
    ("/r/KITEID/continue", "AB1234", "/zerodha/r/AB1234"),
])
def test_a_valid_id_continues_to_the_canonical_referral_link(
    seeded, django_capture_on_commit_callbacks, path, entered, target
):
    resp = _get(f"{path}?kite_id={entered}", django_capture_on_commit_callbacks)
    assert (resp.status_code, resp.headers["Location"]) == (302, target)
    # The pop-up itself saves nothing; the canonical link it redirects to does the usual work.
    assert _no_referrer_saved()
    follow = _get(target, django_capture_on_commit_callbacks)
    assert follow.status_code == 200
    assert ReferralIdentity.objects.filter(client_id="AB1234").exists()


@pytest.mark.urls("tests.urls_share_intent")
@pytest.mark.parametrize("path", ["/share/wa/KITEID", "/share/wa/", "/zerodha/share/wa"])
def test_a_valid_id_continues_to_the_canonical_share_link(seeded, django_capture_on_commit_callbacks, path):
    resp = _get(f"{path}?kite_id=ab1234", django_capture_on_commit_callbacks)
    assert (resp.status_code, resp.headers["Location"]) == (302, "/zerodha/share/wa/AB1234")


@pytest.mark.parametrize("entered,error_default", [
    ("", prefkeys.KITE_PROMPT_ERROR_EMPTY_DEFAULT),
    ("KITEID", prefkeys.KITE_PROMPT_ERROR_PLACEHOLDER_DEFAULT),
    ("kiteid", prefkeys.KITE_PROMPT_ERROR_PLACEHOLDER_DEFAULT),
    ("XXXXXX", prefkeys.KITE_PROMPT_ERROR_PLACEHOLDER_DEFAULT),
    ("YOUR_KITE_ID", prefkeys.KITE_PROMPT_ERROR_SHAPE_DEFAULT),
    ("12345", prefkeys.KITE_PROMPT_ERROR_SHAPE_DEFAULT),
])
def test_a_bad_entry_keeps_the_prompt_open_with_the_right_error(
    seeded, django_capture_on_commit_callbacks, entered, error_default
):
    from django.utils.html import escape

    resp = _get(f"/r/wa/KITEID?kite_id={entered}", django_capture_on_commit_callbacks)
    body = resp.content.decode()
    assert resp.status_code == 200
    assert escape(error_default) in body
    assert 'role="alert"' in body
    assert _no_referrer_saved()


def test_the_view_event_is_recorded_once_not_on_each_retry(seeded, django_capture_on_commit_callbacks):
    _get("/r/wa/KITEID", django_capture_on_commit_callbacks)
    _get("/r/wa/KITEID?kite_id=KITEID", django_capture_on_commit_callbacks)
    events = Event.objects.filter(event_type="share_recovery_viewed")
    assert events.count() == 1
    assert events.get().metadata == {"channel": "WhatsApp", "prompt": "referral"}


# --- skipping -----------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/r/wa/KITEID", "/r/", "/zerodha/r/open", "/r/wa/YOUR_KITE_ID"])
def test_referral_skip_lands_on_the_empty_box_with_partner_code(
    seeded, django_capture_on_commit_callbacks, path
):
    resp = _get(path + "?skip=1", django_capture_on_commit_callbacks)
    assert (resp.status_code, resp.headers["Location"]) == (302, REFERRAL_PAGE)
    assert _no_referrer_saved()
    assert Referral.objects.filter(source="partner_direct", referral_identity__isnull=True).count() == 1


@pytest.mark.urls("tests.urls_share_intent")
@pytest.mark.parametrize("path", ["/share/wa/KITEID", "/share/wa/", "/zerodha/share/wa/YOUR_KITE_ID"])
def test_share_skip_shares_the_no_referrer_link(seeded, django_capture_on_commit_callbacks, settings, path):
    settings.PUBLIC_BASE_URL = "https://gorefer.in"
    resp = _get(path + "?skip=1", django_capture_on_commit_callbacks)
    assert resp.status_code == 302
    text = unquote(resp.headers["Location"])
    assert resp.headers["Location"].startswith("https://wa.me/?text=")
    assert "https://gorefer.in/zerodha/r/open" in text
    assert "Disclosures: https://gorefer.in/d/pifs" in text  # compliance tail still appended
    assert "KITEID" not in text and "ZMPHZC" not in text
    assert _no_referrer_saved()
    event = Event.objects.get(event_type="share_intent")
    assert event.metadata == {"channel": "WhatsApp", "without_id": True}
    assert event.referral.referral_identity is None


@pytest.mark.urls("tests.urls_share_intent")
def test_share_skip_from_a_crawler_records_nothing(seeded, django_capture_on_commit_callbacks):
    _get("/share/wa/?skip=1", django_capture_on_commit_callbacks, **BOT)
    assert Event.objects.count() == 0 and Referral.objects.count() == 0


# --- placeholders never become referrers ------------------------------------------

def test_placeholder_words_are_refused_by_the_strict_validator(tenant):
    for word in ("KITEID", "kiteid", "CLIENT", "XXXXXX"):
        with pytest.raises(InvalidClientId):
            validate_client_id_for(tenant, word)
    assert validate_client_id_for(tenant, "rj4521") == "RJ4521"  # real ids untouched


def test_placeholder_words_are_config(tenant, django_capture_on_commit_callbacks):
    """rail E-6 spot test: the placeholder list is a cascade key, editable without a deploy."""
    assert _get("/r/SAMPLE", django_capture_on_commit_callbacks).status_code == 200
    assert ReferralIdentity.objects.filter(client_id="SAMPLE").exists()  # a real-shaped id passes
    set_tenant(prefkeys.CLIENT_ID_PLACEHOLDER_WORDS, ["SAMPLE"], tenant_id=tenant.id)
    resp = _get("/r/AMPLE1", django_capture_on_commit_callbacks)
    assert resp.status_code == 200 and ReferralIdentity.objects.filter(client_id="AMPLE1").exists()
    with pytest.raises(InvalidClientId):
        validate_client_id_for(tenant, "sample")


# --- wording is configuration -------------------------------------------------------

def test_prompt_wording_comes_from_the_cascade(tenant, django_capture_on_commit_callbacks):
    """rail E-6 spot test: every word on the pop-up resolves from config."""
    set_tenant(prefkeys.KITE_PROMPT_REF_TITLE, "Kaun ne bheja?", tenant_id=tenant.id)
    set_tenant(prefkeys.KITE_PROMPT_REF_BUTTON, "Go to {program_brand}", tenant_id=tenant.id)
    body = _get("/r/wa/", django_capture_on_commit_callbacks).content.decode()
    assert "Kaun ne bheja?" in body
    assert "Go to Zerodha" in body  # {program_brand} filled from the program


def test_prompt_page_carries_compliance_and_no_partner_code(
    seeded, django_capture_on_commit_callbacks, settings
):
    body = _get("/r/wa/KITEID", django_capture_on_commit_callbacks).content.decode()
    assert "AP2516003693" in body
    assert settings.MARKET_RISK_WARNING in body
    assert "ZMPHZC" not in body and "signup.zerodha.com" not in body


def test_preferences_save_the_wording_and_placeholder_list(tenant):
    from apps.dashboard.preferences_service import current_view, save_preferences

    notices = save_preferences(tenant, {
        prefkeys.KITE_PROMPT_SHARE_TITLE: "Apna Kite ID likhein",
        prefkeys.KITE_PROMPT_REF_SKIP: "",  # blank restores the default
        prefkeys.CLIENT_ID_PLACEHOLDER_WORDS: "kite-id, Your ID,KITEID",
    })
    assert not any("Placeholder words" in n for n in notices)  # (a partial form trips other sections)
    assert resolve(prefkeys.KITE_PROMPT_SHARE_TITLE, tenant_id=tenant.id) == "Apna Kite ID likhein"
    skip = resolve(prefkeys.KITE_PROMPT_REF_SKIP, tenant_id=tenant.id)
    assert skip == prefkeys.KITE_PROMPT_REF_SKIP_DEFAULT
    assert resolve(prefkeys.CLIENT_ID_PLACEHOLDER_WORDS, tenant_id=tenant.id) == ["KITEID", "YOURID"]
    rows = {r["form_key"]: r["value"] for r in current_view(tenant)["kite_prompt_fields"]}
    assert rows[prefkeys.CLIENT_ID_PLACEHOLDER_WORDS] == "KITEID, YOURID"


def test_preferences_refuse_an_empty_placeholder_list(tenant):
    from apps.dashboard.preferences_service import save_preferences

    notices = save_preferences(tenant, {prefkeys.CLIENT_ID_PLACEHOLDER_WORDS: " , "})
    assert any("keep at least one word" in n for n in notices)
    assert "KITEID" in resolve(prefkeys.CLIENT_ID_PLACEHOLDER_WORDS, tenant_id=tenant.id)


def test_share_path_builder(tenant):
    assert links.share_path("wa", "AB1234", tenant=tenant) == "/zerodha/share/wa/AB1234"


# --- every share channel, not just WhatsApp -------------------------------------------

ALL_CHANNELS = sorted(SHARE_CHANNEL_LABELS.items())


@pytest.mark.parametrize("code,label", ALL_CHANNELS)
def test_every_channel_gets_the_prompt_and_keeps_its_channel(
    seeded, django_capture_on_commit_callbacks, code, label
):
    """/r/{ch}/KITEID, /r/{ch}/, /r/{ch} and the /zerodha/ twin show the pop-up for EVERY
    configured channel (fb, x, li, tg, ig, yt, email, copy, wa); a valid entry keeps the
    channel in the link, and Skip records it on the click."""
    for path in (f"/r/{code}/KITEID", f"/r/{code}/", f"/r/{code}", f"/zerodha/r/{code}/YOUR_KITE_ID"):
        resp = _get(path, django_capture_on_commit_callbacks)
        assert resp.status_code == 200 and REF_TITLE in resp.content.decode(), path
    resp = _get(f"/r/{code}/KITEID?kite_id=AB1234", django_capture_on_commit_callbacks)
    assert resp.headers["Location"] == f"/zerodha/r/{code}/AB1234"
    resp = _get(f"/r/{code}/KITEID?skip=1", django_capture_on_commit_callbacks)
    assert resp.headers["Location"] == REFERRAL_PAGE
    assert Event.objects.get(event_type="click").metadata == {"channel": label}
    assert _no_referrer_saved()
    real = _get(f"/r/{code}/AB1234", django_capture_on_commit_callbacks)
    assert real.status_code == 200 and REF_TITLE not in real.content.decode()  # real id: landing
