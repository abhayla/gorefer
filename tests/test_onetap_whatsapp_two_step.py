"""One-tap WhatsApp share = two steps: register link, then open link (owner 2026-11-04).

The four texts below are the owner-approved messages, byte for byte (A EN with an ID,
B EN "Share without my ID", C HI with an ID, D HI without an ID). Every test decodes the
wa.me `text` and compares for equality; nothing is retyped from memory.
"""
# ruff: noqa: E501
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.management import call_command
from django.test import Client

from apps.config import preferences as prefkeys
from apps.config.cascade import resolve, set_tenant
from apps.config.models import ConfigCentral
from apps.events.models import Event
from apps.referrals.models import ReferralIdentity
from apps.tenants.resolve import get_bootstrap_tenant

CID = "DA1707"
HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.9"}
SHARE_URLS = pytest.mark.urls("tests.urls_share_intent")

# --- APPROVED TEXTS (generated from the owner-approved file) ---
A = "*Follow these steps to Open Zerodha Account*\n\n*Step 1 - Register your details*\nhttps://gorefer.in/zerodha/r/wa/DA1707\n\n*Step 2 - Open a free Zerodha account online:*\nhttps://gorefer.in/zerodha/open\n\n*Keep ready:*\nPAN, Aadhaar-linked mobile number, bank details, Cancelled Cheque or Passbook, Picture of your Signature\n\n*How-to-Open Zerodha Account video:*\nhttps://youtu.be/JFx9tzhBrjE\n\nInvestments in securities market are subject to market risks, read all the related documents carefully before investing.\n\n*Disclosures:*\nhttps://gorefer.in/d/pifs"
B = "*Follow these steps to Open Zerodha Account*\n\n*Step 1 - Register your details*\nhttps://gorefer.in/r/wa\n\n*Step 2 - Open a free Zerodha account online:*\nhttps://gorefer.in/zerodha/open\n\n*Keep ready:*\nPAN, Aadhaar-linked mobile number, bank details, Cancelled Cheque or Passbook, Picture of your Signature\n\n*How-to-Open Zerodha Account video:*\nhttps://youtu.be/JFx9tzhBrjE\n\nInvestments in securities market are subject to market risks, read all the related documents carefully before investing.\n\n*Disclosures:*\nhttps://gorefer.in/d/pifs"
C = "*Zerodha खाता खोलने के लिए ये स्टेप्स फ़ॉलो करें*\n\n*स्टेप 1 - अपनी जानकारी रजिस्टर करें*\nhttps://gorefer.in/zerodha/r/wa/DA1707\n\n*स्टेप 2 - ऑनलाइन मुफ़्त Zerodha खाता खोलें:*\nhttps://gorefer.in/zerodha/open\n\n*तैयार रखें:*\nPAN, आधार से जुड़ा मोबाइल नंबर, बैंक डिटेल्स, कैंसल्ड चेक या पासबुक, आपके सिग्नेचर की फ़ोटो\n\n*Zerodha खाता कैसे खोलें - वीडियो:*\nhttps://youtu.be/JTZ-ebu2vyA\n\nInvestments in securities market are subject to market risks, read all the related documents carefully before investing.\n\n*Disclosures:*\nhttps://gorefer.in/d/pifs"
D = "*Zerodha खाता खोलने के लिए ये स्टेप्स फ़ॉलो करें*\n\n*स्टेप 1 - अपनी जानकारी रजिस्टर करें*\nhttps://gorefer.in/r/wa\n\n*स्टेप 2 - ऑनलाइन मुफ़्त Zerodha खाता खोलें:*\nhttps://gorefer.in/zerodha/open\n\n*तैयार रखें:*\nPAN, आधार से जुड़ा मोबाइल नंबर, बैंक डिटेल्स, कैंसल्ड चेक या पासबुक, आपके सिग्नेचर की फ़ोटो\n\n*Zerodha खाता कैसे खोलें - वीडियो:*\nhttps://youtu.be/JTZ-ebu2vyA\n\nInvestments in securities market are subject to market risks, read all the related documents carefully before investing.\n\n*Disclosures:*\nhttps://gorefer.in/d/pifs"

PR197_DEFAULT = (
    "*Open a free {program_brand} account online:*\n{link}\n\n"
    "*Keep ready:*\nPAN, Aadhaar-linked mobile number, bank details, Cancelled Cheque or "
    "Passbook, Picture of your Signature\n\n"
    "*How-to-Open {program_brand} Account video:*\n"
    "https://www.youtube.com/watch?v=JTZ-ebu2vyA\n\n"
    "Investments in securities market are subject to market risks, read all the related "
    "documents carefully before investing."
)


@pytest.fixture
def tenant(db, settings):
    settings.PUBLIC_BASE_URL = "https://gorefer.in"
    call_command("seed_program")
    return get_bootstrap_tenant()


def _text(resp) -> str:
    return parse_qs(urlparse(resp.headers["Location"]).query)["text"][0]


def _get(path, capture):
    with capture(execute=True):
        return Client().get(path, **HUMAN)


def _set_central(key, value):
    ConfigCentral.objects.update_or_create(key=key, defaults={"value": value})


def _central(key):
    return ConfigCentral.objects.get(key=key).value


# --- the four byte-exact tests ---------------------------------------------------


@SHARE_URLS
@pytest.mark.parametrize("path", [f"/zerodha/share/wa/{CID}", f"/share/wa/{CID}"])
def test_A_english_with_id(tenant, django_capture_on_commit_callbacks, path):
    assert _text(_get(path, django_capture_on_commit_callbacks)) == A


@SHARE_URLS
@pytest.mark.parametrize("path", ["/zerodha/share/wa/KITEID?skip=1", "/share/wa/KITEID?skip=1"])
def test_B_english_share_without_my_id(tenant, django_capture_on_commit_callbacks, path):
    assert _text(_get(path, django_capture_on_commit_callbacks)) == B
    assert not ReferralIdentity.objects.exists()


@SHARE_URLS
@pytest.mark.parametrize("path", [f"/zerodha/share/wa/{CID}?lang=hi", f"/share/wa/{CID}?lang=hi"])
def test_C_hindi_with_id(tenant, django_capture_on_commit_callbacks, path):
    assert _text(_get(path, django_capture_on_commit_callbacks)) == C


@SHARE_URLS
def test_D_hindi_share_without_my_id(tenant, django_capture_on_commit_callbacks):
    path = "/zerodha/share/wa/KITEID?skip=1&lang=hi"
    assert _text(_get(path, django_capture_on_commit_callbacks)) == D


@SHARE_URLS
def test_typed_id_popup_path_gives_A(tenant, django_capture_on_commit_callbacks):
    resp = _get(f"/share/wa/KITEID?kite_id={CID}", django_capture_on_commit_callbacks)
    assert resp.headers["Location"] == f"/zerodha/share/wa/{CID}"
    assert _text(_get(resp.headers["Location"], django_capture_on_commit_callbacks)) == A


# --- behaviour kept -------------------------------------------------------------


@SHARE_URLS
def test_referrer_opener_still_replaces_the_text(tenant, django_capture_on_commit_callbacks):
    from apps.accounts import opener as opener_service
    from apps.referrals.models import ReferralProgram

    program = ReferralProgram.objects.get(tenant=tenant)
    identity = ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner, client_id=CID)
    opener_service.set_opener(identity, "My own words.")
    text = _text(_get(f"/share/wa/{CID}", django_capture_on_commit_callbacks))
    assert text == ("My own words.\nhttps://gorefer.in/zerodha/open\n\n"
                    "*Disclosures:*\nhttps://gorefer.in/d/pifs")


@SHARE_URLS
def test_share_event_recorded_under_the_referrer(tenant, django_capture_on_commit_callbacks):
    _get(f"/share/wa/{CID}", django_capture_on_commit_callbacks)
    event = Event.objects.get(event_type="share_intent")
    assert event.referral.referral_identity.client_id == CID


@SHARE_URLS
@pytest.mark.parametrize("ch", ["tg", "x"])
def test_telegram_and_x_unchanged(tenant, django_capture_on_commit_callbacks, ch):
    text = _text(_get(f"/share/{ch}/{CID}", django_capture_on_commit_callbacks))
    assert f"https://gorefer.in/zerodha/r/{ch}/{CID}" in text
    assert "Step 1" not in text
    assert text.endswith("\n\nDisclosures: https://gorefer.in/d/pifs")


@SHARE_URLS
def test_old_link_placeholder_still_works_for_rollback(tenant, django_capture_on_commit_callbacks):
    """An operator pastes the PR #197 text back: {link} = the open link, as before."""
    set_tenant(prefkeys.SHARE_ONETAP_WA_MESSAGE, PR197_DEFAULT, tenant_id=tenant.id)
    text = _text(_get(f"/share/wa/{CID}", django_capture_on_commit_callbacks))
    assert text.startswith("*Open a free Zerodha account online:*\nhttps://gorefer.in/zerodha/open\n\n")
    assert text.endswith("*Disclosures:*\nhttps://gorefer.in/d/pifs")


# --- config (E-6 spot tests, one per new key) ------------------------------------


@SHARE_URLS
def test_hindi_message_is_a_cascade_key(tenant, django_capture_on_commit_callbacks):
    set_tenant(prefkeys.SHARE_ONETAP_WA_MESSAGE_HI, "हिंदी {register_link} {open_link}",
               tenant_id=tenant.id)
    text = _text(_get(f"/share/wa/{CID}?lang=hi", django_capture_on_commit_callbacks))
    assert text == ("हिंदी https://gorefer.in/zerodha/r/wa/DA1707 https://gorefer.in/zerodha/open"
                    "\n\n*Disclosures:*\nhttps://gorefer.in/d/pifs")


@SHARE_URLS
def test_blank_hindi_value_in_config_falls_back_to_english_template(tenant, django_capture_on_commit_callbacks):
    set_tenant(prefkeys.SHARE_ONETAP_WA_MESSAGE_HI, "", tenant_id=tenant.id)
    assert _text(_get(f"/share/wa/{CID}?lang=hi", django_capture_on_commit_callbacks)) == A


@SHARE_URLS
@pytest.mark.parametrize("bad", ["*Hi {nope}*\n{register_link}","{register_link} {", "{0} {register_link}"])
def test_unrenderable_configured_text_falls_back_to_default(tenant, django_capture_on_commit_callbacks, bad):
    _set_central(prefkeys.SHARE_ONETAP_WA_MESSAGE, bad)
    resp = _get(f"/share/wa/{CID}", django_capture_on_commit_callbacks)
    assert resp.status_code == 302 and resp.headers["Location"].startswith("https://wa.me/")
    assert _text(resp) == A


@SHARE_URLS
def test_unrenderable_hindi_text_falls_back_to_hindi_default(tenant, django_capture_on_commit_callbacks):
    _set_central(prefkeys.SHARE_ONETAP_WA_MESSAGE_HI, "{nope}")
    assert _text(_get(f"/share/wa/{CID}?lang=hi", django_capture_on_commit_callbacks)) == C


def test_blank_hindi_save_stores_default_and_help_text_says_so(tenant, admin_client):
    from apps.dashboard.preferences_service import save_preferences

    save_preferences(tenant, {prefkeys.SHARE_ONETAP_WA_MESSAGE_HI: ""})
    assert resolve(prefkeys.SHARE_ONETAP_WA_MESSAGE_HI, tenant_id=tenant.id) == prefkeys.SHARE_ONETAP_WA_MESSAGE_HI_DEFAULT
    body = admin_client.get("/admin-panel/preferences").content.decode()
    assert "Leave blank to use the default Hindi message." in body


@SHARE_URLS
def test_no_id_register_path_is_a_cascade_key(tenant, django_capture_on_commit_callbacks):
    set_tenant(prefkeys.SHARE_ONETAP_WA_REGISTER_PATH, "/r/open", tenant_id=tenant.id)
    text = _text(_get("/share/wa/KITEID?skip=1", django_capture_on_commit_callbacks))
    assert text == B.replace("https://gorefer.in/r/wa", "https://gorefer.in/r/open")


def test_new_keys_have_the_approved_defaults(tenant):
    assert resolve(prefkeys.SHARE_ONETAP_WA_REGISTER_PATH, tenant_id=tenant.id) == "/r/wa"
    assert "{register_link}" in resolve(prefkeys.SHARE_ONETAP_WA_MESSAGE, tenant_id=tenant.id)
    assert "{register_link}" in resolve(prefkeys.SHARE_ONETAP_WA_MESSAGE_HI, tenant_id=tenant.id)


def test_validator_accepts_new_placeholders_and_requires_a_link(tenant):
    from apps.dashboard.preferences_service import save_preferences as _save

    def save_preferences(t, d):
        return [n for n in _save(t, d) if "One-tap" in n]

    ok = "Go {register_link} then {open_link} for {program_brand}"
    assert save_preferences(tenant, {prefkeys.SHARE_ONETAP_WA_MESSAGE: ok}) == []
    assert resolve(prefkeys.SHARE_ONETAP_WA_MESSAGE, tenant_id=tenant.id) == ok
    assert save_preferences(tenant, {prefkeys.SHARE_ONETAP_WA_MESSAGE: "Old {link}"}) == []
    notices = save_preferences(tenant, {prefkeys.SHARE_ONETAP_WA_MESSAGE: "no link at all"})
    assert any("{register_link}" in n for n in notices)
    assert save_preferences(tenant, {prefkeys.SHARE_ONETAP_WA_MESSAGE: "{register_link} {bogus}"})
    assert resolve(prefkeys.SHARE_ONETAP_WA_MESSAGE, tenant_id=tenant.id) == "Old {link}"
    # Hindi message and the no-ID path save through the same screen.
    assert save_preferences(tenant, {prefkeys.SHARE_ONETAP_WA_MESSAGE_HI: "हि {register_link}",
                                     prefkeys.SHARE_ONETAP_WA_REGISTER_PATH: "/r/open"}) == []
    assert resolve(prefkeys.SHARE_ONETAP_WA_MESSAGE_HI, tenant_id=tenant.id) == "हि {register_link}"
    assert resolve(prefkeys.SHARE_ONETAP_WA_REGISTER_PATH, tenant_id=tenant.id) == "/r/open"
    assert save_preferences(tenant, {prefkeys.SHARE_ONETAP_WA_MESSAGE_HI: "no link"})


def test_preferences_screen_shows_new_fields(tenant, admin_client):
    body = admin_client.get("/admin-panel/preferences").content.decode()
    for name in ("share_onetap_wa_message_hi", "share_onetap_wa_register_path"):
        assert f'name="{name}"' in body


# --- seed: move the PR #197 default only when it is byte-equal --------------------


def test_seed_moves_the_old_default_to_the_new_one(tenant):
    _set_central(prefkeys.SHARE_ONETAP_WA_MESSAGE, PR197_DEFAULT)
    call_command("seed_program")
    assert _central(prefkeys.SHARE_ONETAP_WA_MESSAGE) == prefkeys.SHARE_ONETAP_WA_MESSAGE_DEFAULT


def test_seed_never_touches_an_operator_edit_or_tenant_override(tenant):
    _set_central(prefkeys.SHARE_ONETAP_WA_MESSAGE, "Custom {link}")
    set_tenant(prefkeys.SHARE_ONETAP_WA_MESSAGE, PR197_DEFAULT, tenant_id=tenant.id)
    call_command("seed_program")
    assert _central(prefkeys.SHARE_ONETAP_WA_MESSAGE) == "Custom {link}"
    assert resolve(prefkeys.SHARE_ONETAP_WA_MESSAGE, tenant_id=tenant.id) == PR197_DEFAULT


def test_seed_is_idempotent_and_creates_missing_keys(tenant):
    ConfigCentral.objects.filter(key=prefkeys.SHARE_ONETAP_WA_MESSAGE_HI).delete()
    _set_central(prefkeys.SHARE_ONETAP_WA_MESSAGE, PR197_DEFAULT)
    call_command("seed_program")
    keys = (prefkeys.SHARE_ONETAP_WA_MESSAGE, prefkeys.SHARE_ONETAP_WA_MESSAGE_HI,
            prefkeys.SHARE_ONETAP_WA_REGISTER_PATH)
    first = {k: _central(k) for k in keys}
    call_command("seed_program")
    assert first == {k: _central(k) for k in keys}
    assert first[prefkeys.SHARE_ONETAP_WA_MESSAGE_HI] == prefkeys.SHARE_ONETAP_WA_MESSAGE_HI_DEFAULT


def test_seed_moves_pr199_english_default_to_the_first_line_default(tenant):
    _set_central(prefkeys.SHARE_ONETAP_WA_MESSAGE, prefkeys.SHARE_ONETAP_WA_MESSAGE_PR199_DEFAULT)
    call_command("seed_program")
    assert _central(prefkeys.SHARE_ONETAP_WA_MESSAGE) == prefkeys.SHARE_ONETAP_WA_MESSAGE_DEFAULT
    assert prefkeys.SHARE_ONETAP_WA_MESSAGE_DEFAULT.startswith(
        "*Follow these steps to Open {program_brand} Account*\n\n*Step 1")


def test_seed_moves_pr199_hindi_default_to_the_first_line_default(tenant):
    _set_central(prefkeys.SHARE_ONETAP_WA_MESSAGE_HI, prefkeys.SHARE_ONETAP_WA_MESSAGE_HI_PR199_DEFAULT)
    call_command("seed_program")
    assert _central(prefkeys.SHARE_ONETAP_WA_MESSAGE_HI) == prefkeys.SHARE_ONETAP_WA_MESSAGE_HI_DEFAULT
    assert prefkeys.SHARE_ONETAP_WA_MESSAGE_HI_DEFAULT.startswith(
        "*{program_brand} खाता खोलने के लिए ये स्टेप्स फ़ॉलो करें*\n\n*स्टेप 1")


def test_seed_leaves_edited_pr199_text_and_is_idempotent(tenant):
    edited_en = prefkeys.SHARE_ONETAP_WA_MESSAGE_PR199_DEFAULT + " "
    edited_hi = prefkeys.SHARE_ONETAP_WA_MESSAGE_HI_PR199_DEFAULT + " "
    _set_central(prefkeys.SHARE_ONETAP_WA_MESSAGE, edited_en)
    _set_central(prefkeys.SHARE_ONETAP_WA_MESSAGE_HI, edited_hi)
    call_command("seed_program")
    call_command("seed_program")
    assert _central(prefkeys.SHARE_ONETAP_WA_MESSAGE) == edited_en
    assert _central(prefkeys.SHARE_ONETAP_WA_MESSAGE_HI) == edited_hi
    _set_central(prefkeys.SHARE_ONETAP_WA_MESSAGE, prefkeys.SHARE_ONETAP_WA_MESSAGE_PR199_DEFAULT)
    call_command("seed_program")
    call_command("seed_program")
    assert _central(prefkeys.SHARE_ONETAP_WA_MESSAGE) == prefkeys.SHARE_ONETAP_WA_MESSAGE_DEFAULT
