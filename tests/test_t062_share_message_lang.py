"""T-062 — share-message self-serve editing + language stickiness.

What this locks down:
  - the Preferences screen exposes two editable share-message fields (EN + HI),
    keyed exactly to `share_kit_message_template` / `share_kit_message_template_hi`
    — the SAME cascade keys `kit_message()` already reads — so a saved edit changes
    the live /share/wa prefill and hub share message with NO deploy;
  - GET /share/{channel}/{client_id} and GET /hub/{token} resolve their message
    language from the referrer's STORED language (the `referrer_language` cascade
    key, the exact source `apps.referrals.recipient_identity`/followups already use)
    when no `?lang=` is given; an explicit `?lang=` always overrides; invalid/unset
    stored language -> EN;
  - zero behavior change for EN/unset referrers (pinned against the pre-T-062 output
    shape: the default EN template format resolved directly from flags).
"""
from __future__ import annotations

import urllib.parse

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.config import preferences as prefkeys
from apps.config.cascade import set_tenant
from apps.config.i18n import resolve_lang_or_stored, resolve_stored_referrer_language
from apps.referrals.models import ReferralIdentity, ReferralProgram
from apps.referrals.share_intent_service import SHARE_KIT_MESSAGE_KEY
from apps.tenants.models import Tenant
from gorefer.flags import flags

CID = "RJ4521"
PREFS_URL = "/admin-panel/preferences"
HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.7"}

pytestmark = pytest.mark.django_db

SHARE_URLS = pytest.mark.urls("tests.urls_share_intent")
HUB_URLS = pytest.mark.urls("tests.urls_share_hub")


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


@pytest.fixture
def admin_client(seeded):
    User = get_user_model()
    User.objects.create_user(
        username="admin@pifs.in", email="admin@pifs.in", password="pw12345!", is_staff=True
    )
    c = Client()
    c.login(username="admin@pifs.in", password="pw12345!")
    return c


def _identity(tenant, client_id: str = CID) -> ReferralIdentity:
    program = ReferralProgram.objects.get(tenant=tenant)
    return ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner, client_id=client_id
    )


# ------------------------------------------------------------- key-name pinning


def test_share_kit_message_key_matches_the_prefs_constant():
    """The DoD requires the SAME cascade key — pin the two literals equal so a rename
    on either side fails loudly instead of silently splitting into two keys."""
    assert prefkeys.SHARE_KIT_MESSAGE_TEMPLATE == SHARE_KIT_MESSAGE_KEY


# --------------------------------------------------------- Preferences screen (EN/HI)


def test_preferences_screen_renders_both_share_message_fields(admin_client):
    resp = admin_client.get(PREFS_URL)
    body = resp.content.decode()
    assert 'name="share_kit_message_template"' in body
    assert 'name="share_kit_message_template_hi"' in body
    # Help text documents the actual placeholders kit_message() supports.
    assert "{link}" in body
    assert "{program_brand}" in body


@SHARE_URLS
def test_saving_new_en_message_changes_the_live_share_prefill(admin_client, seeded, client):
    resp = admin_client.post(
        PREFS_URL,
        {
            "landing_mode": "page",
            "referrer_reward_claim": "10% brokerage share + 300 reward points",
            "support_helpline_phone": "+91 73888 82020",
            "wati_business_number": "917080642020",
            "share_channels": ["wa", "copy"],
            "share_show_reward": "on",
            "share_kit_message_template": "Brand new EN copy — {link}",
            "share_kit_message_template_hi": "",
        },
    )
    assert resp.status_code == 200

    _identity(seeded)
    resp2 = client.get(f"/share/wa/{CID}", **HUMAN)
    text = urllib.parse.parse_qs(urllib.parse.urlparse(resp2["Location"]).query).get("text", [""])[0]
    assert text.startswith("Brand new EN copy — ")


def test_saving_new_hi_message_changes_the_live_hub_prefill(admin_client, seeded):
    resp = admin_client.post(
        PREFS_URL,
        {
            "landing_mode": "page",
            "referrer_reward_claim": "10% brokerage share + 300 reward points",
            "support_helpline_phone": "+91 73888 82020",
            "wati_business_number": "917080642020",
            "share_channels": ["wa", "copy"],
            "share_show_reward": "on",
            "share_kit_message_template": "",
            "share_kit_message_template_hi": "नया हिंदी संदेश: {link}",
        },
    )
    assert resp.status_code == 200

    from apps.accounts.hub import hub_ctx
    from apps.accounts.records_link import mint_records_token

    identity = _identity(seeded)
    ctx = hub_ctx(identity, mint_records_token(identity), lang="hi")
    assert "नया हिंदी संदेश:" in ctx["share_message"]


def test_blank_submission_resets_to_default(admin_client, seeded):
    set_tenant(prefkeys.SHARE_KIT_MESSAGE_TEMPLATE, "custom override", tenant_id=seeded.id)
    admin_client.post(
        PREFS_URL,
        {
            "landing_mode": "page",
            "referrer_reward_claim": "10% brokerage share + 300 reward points",
            "support_helpline_phone": "+91 73888 82020",
            "wati_business_number": "917080642020",
            "share_channels": ["wa", "copy"],
            "share_show_reward": "on",
            "share_kit_message_template": "",
            "share_kit_message_template_hi": "",
        },
    )
    value = prefkeys.get_preferences(seeded.id)[prefkeys.SHARE_KIT_MESSAGE_TEMPLATE]
    assert value == flags.SHARE_KIT_MESSAGE_TEMPLATE


# --------------------------------------------------------------- stored-language source


def test_resolve_stored_referrer_language_reads_the_existing_cascade_key(seeded):
    assert resolve_stored_referrer_language(seeded.id) == "en"
    set_tenant(prefkeys.REFERRER_LANGUAGE, "hi", tenant_id=seeded.id)
    assert resolve_stored_referrer_language(seeded.id) == "hi"


def test_resolve_stored_referrer_language_unknown_value_is_en(seeded):
    set_tenant(prefkeys.REFERRER_LANGUAGE, "fr", tenant_id=seeded.id)
    assert resolve_stored_referrer_language(seeded.id) == "en"


class _Req:
    def __init__(self, get: dict):
        self.GET = get


def test_resolve_lang_or_stored_explicit_param_always_wins(seeded):
    set_tenant(prefkeys.REFERRER_LANGUAGE, "hi", tenant_id=seeded.id)
    assert resolve_lang_or_stored(_Req({"lang": "en"}), seeded.id) == "en"
    assert resolve_lang_or_stored(_Req({}), seeded.id) == "hi"
    assert resolve_lang_or_stored(_Req({"lang": "garbage"}), seeded.id) == "hi"


def test_followups_recipient_identity_reads_the_same_source(seeded):
    """Reuse, never a second source — recipient_identity's resolver must move in
    lockstep with the new public i18n entrypoint."""
    from apps.referrals.recipient_identity import _resolve_lang

    set_tenant(prefkeys.REFERRER_LANGUAGE, "hi", tenant_id=seeded.id)
    assert _resolve_lang(seeded.id) == resolve_stored_referrer_language(seeded.id) == "hi"


# --------------------------------------------------------------------- /share/ endpoint


@SHARE_URLS
def test_share_endpoint_defaults_to_stored_language(seeded, client):
    set_tenant(prefkeys.REFERRER_LANGUAGE, "hi", tenant_id=seeded.id)
    set_tenant(
        prefkeys.SHARE_KIT_MESSAGE_TEMPLATE_HI, "हिंदी प्रीफ़िल: {link}", tenant_id=seeded.id
    )
    resp = client.get(f"/share/wa/{CID}", **HUMAN)
    text = urllib.parse.parse_qs(urllib.parse.urlparse(resp["Location"]).query).get("text", [""])[0]
    assert text.startswith("हिंदी प्रीफ़िल:")


@SHARE_URLS
def test_share_endpoint_explicit_lang_param_overrides_stored(seeded, client):
    set_tenant(prefkeys.REFERRER_LANGUAGE, "hi", tenant_id=seeded.id)
    resp = client.get(f"/share/wa/{CID}?lang=en", **HUMAN)
    text = urllib.parse.parse_qs(urllib.parse.urlparse(resp["Location"]).query).get("text", [""])[0]
    assert text.startswith("Open a free Zerodha account")


@SHARE_URLS
def test_share_endpoint_unset_stored_language_is_en(seeded, client):
    resp = client.get(f"/share/wa/{CID}", **HUMAN)
    text = urllib.parse.parse_qs(urllib.parse.urlparse(resp["Location"]).query).get("text", [""])[0]
    assert text.startswith("Open a free Zerodha account")


# ------------------------------------------------------------------------ /hub/ default


@HUB_URLS
def test_hub_defaults_to_stored_language_when_no_lang_param(seeded, client):
    from apps.accounts.records_link import mint_records_token

    set_tenant(prefkeys.REFERRER_LANGUAGE, "hi", tenant_id=seeded.id)
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()
    assert '<html lang="hi">' in body


@HUB_URLS
def test_hub_explicit_lang_param_overrides_stored_both_ways(seeded, client):
    from apps.accounts.records_link import mint_records_token

    set_tenant(prefkeys.REFERRER_LANGUAGE, "hi", tenant_id=seeded.id)
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}?lang=en").content.decode()
    assert '<html lang="en">' in body

    set_tenant(prefkeys.REFERRER_LANGUAGE, "en", tenant_id=seeded.id)
    body_hi = client.get(f"/hub/{token}?lang=hi").content.decode()
    assert '<html lang="hi">' in body_hi


@HUB_URLS
def test_hub_unset_stored_language_defaults_en(seeded, client):
    from apps.accounts.records_link import mint_records_token

    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()
    assert '<html lang="en">' in body


@HUB_URLS
def test_hub_invalid_stored_language_falls_back_to_en(seeded, client):
    from apps.accounts.records_link import mint_records_token

    set_tenant(prefkeys.REFERRER_LANGUAGE, "fr", tenant_id=seeded.id)
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()
    assert '<html lang="en">' in body


# --------------------------------------------------------- zero-behavior-change (pin)


@SHARE_URLS
def test_zero_behavior_change_default_share_prefill_is_byte_identical(seeded, client):
    """Pinned against the EXACT pre-T-062 output shape: flags.SHARE_KIT_MESSAGE_TEMPLATE
    formatted with the tracked link + program brand, followed by the disclosure anchor —
    with no cascade override and no stored language set."""
    resp = client.get(f"/share/wa/{CID}", **HUMAN)
    text = urllib.parse.parse_qs(urllib.parse.urlparse(resp["Location"]).query).get("text", [""])[0]
    expected = flags.SHARE_KIT_MESSAGE_TEMPLATE.format(
        link=f"https://gorefer.in/r/wa/{CID}", program_brand="Zerodha"
    )
    assert text == expected + "\n\nDisclosures: https://gorefer.in/d/pifs"


@HUB_URLS
def test_zero_behavior_change_hub_html_lang_is_en_by_default(seeded, client):
    from apps.accounts.records_link import mint_records_token

    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()
    assert '<html lang="en">' in body


# --------------------------------------------------------- T-053/055/056/061 invariants


@HUB_URLS
def test_token_never_in_share_href_with_stored_hi_language(seeded, client):
    from apps.accounts.hub import SHARE_BUTTONS
    from apps.accounts.records_link import mint_records_token

    set_tenant(prefkeys.REFERRER_LANGUAGE, "hi", tenant_id=seeded.id)
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()
    import re

    hrefs = re.findall(r"""<a\s+href=["']([^"']+)["'][^>]*data-share-channel=""", body, re.I)
    assert len(hrefs) == len(SHARE_BUTTONS)
    for href in hrefs:
        assert token not in href


@SHARE_URLS
def test_guardrail3_clean_with_stored_hi_language(seeded, client):
    set_tenant(prefkeys.REFERRER_LANGUAGE, "hi", tenant_id=seeded.id)
    resp = client.get(f"/share/wa/{CID}", **HUMAN)
    location = urllib.parse.unquote(resp.headers["Location"])
    assert "ZMPHZC" not in location
    assert "signup.zerodha.com" not in location
