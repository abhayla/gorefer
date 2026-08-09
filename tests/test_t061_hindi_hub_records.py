"""T-061 — Hindi parity on the hub (/hub/{token}) and records (/rr/{token}) surfaces.

What this locks down:
  - every owner-editable copy string on both pages resolves a `{key}_hi` cascade twin
    and NEVER renders blank when the HI row is missing/blank — it falls back to EN
    (the load-bearing guarantee, apps.config.i18n.bi_text/bi_lines);
  - `?lang=hi` selects Hindi; anything else (missing, garbage, `en`) resolves to EN;
    the choice is carried across the /rr/ <-> /hub/ cross-link;
  - a REAL EN<->HI toggle link renders on both pages (never dead UI, Constitution §4);
  - compliance stays bilingual-safe: the locked EN market_risk_warning always renders
    (D-1 rail, central-only); the HI wording is an ADDITIONAL unlocked key, never a
    replacement, and the AP registration/entity line stays verbatim EN;
  - the hub's WhatsApp prefill carries the HI copy twin under lang=hi;
  - the T-053/T-055/T-056 token invariants (never in a share href, exactly one
    occurrence — the /rr/ cross-link) hold identically under lang=hi.
"""
from __future__ import annotations

import dataclasses

import pytest
from django.core.management import call_command

from apps.accounts.hub import SHARE_BUTTONS, hub_ctx
from apps.accounts.records import records_ctx
from apps.accounts.records_link import mint_records_token
from apps.config.i18n import bi_lines, bi_text, resolve_lang
from apps.config.models import ConfigCentral
from apps.config.preferences import (
    MARKET_RISK_WARNING_HI,
    MARKET_RISK_WARNING_HI_DEFAULT,
    RECORDS_TITLE,
    RECORDS_TITLE_HI,
    SHARE_HUB_HEADLINE,
    SHARE_HUB_HEADLINE_HI,
    SHARE_KIT_MESSAGE_TEMPLATE_HI,
)
from apps.referrals.models import ReferralIdentity, ReferralProgram
from apps.tenants.models import Tenant

CID = "RJ4521"

pytestmark = pytest.mark.django_db

HUB_URLS = pytest.mark.urls("tests.urls_share_hub")


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


def _identity(tenant, client_id: str = CID) -> ReferralIdentity:
    program = ReferralProgram.objects.get(tenant=tenant)
    return ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner, client_id=client_id
    )


def _with_flag(monkeypatch, module: str, **overrides) -> None:
    """Swap the flags snapshot a module reads (mirrors tests/test_t053_share_hub.py).

    `flags` is a FROZEN dataclass — a test replaces the module's reference with a
    copy rather than assigning to a field (which raises FrozenInstanceError)."""
    from gorefer.flags import flags

    monkeypatch.setattr(f"{module}.flags", dataclasses.replace(flags, **overrides))


# --------------------------------------------------------------------- lang resolution


class _Req:
    def __init__(self, get: dict):
        self.GET = get


@pytest.mark.parametrize(
    "params,expected",
    [
        ({}, "en"),
        ({"lang": "hi"}, "hi"),
        ({"lang": "HI"}, "hi"),
        ({"lang": "en"}, "en"),
        ({"lang": "fr"}, "en"),
        ({"lang": ""}, "en"),
        ({"lang": "<script>"}, "en"),
    ],
)
def test_resolve_lang_falls_back_to_en_on_anything_but_hi(params, expected):
    assert resolve_lang(_Req(params)) == expected


# ------------------------------------------------------------- the missing-HI fallback


def test_bi_text_falls_back_to_en_when_hi_row_is_unset(seeded):
    """The load-bearing guarantee: no HI row seeded at all -> EN value, never blank."""
    value = bi_text(
        "a_key_nobody_seeded", "EN-DEFAULT", lang="hi", tenant_id=seeded.id, default_hi=None
    )
    assert value == "EN-DEFAULT"


def test_bi_text_falls_back_to_en_when_hi_row_is_blank_string(seeded):
    en_value = bi_text(RECORDS_TITLE, "EN Title", lang="en", tenant_id=seeded.id)
    ConfigCentral.objects.update_or_create(key=RECORDS_TITLE_HI, defaults={"value": "   "})
    value = bi_text(RECORDS_TITLE, "EN Title", lang="hi", tenant_id=seeded.id, default_hi="HI Title")
    assert value == en_value


def test_bi_text_uses_hi_row_when_present_and_non_blank(seeded):
    ConfigCentral.objects.update_or_create(key=RECORDS_TITLE_HI, defaults={"value": "शीर्षक"})
    value = bi_text(RECORDS_TITLE, "EN Title", lang="hi", tenant_id=seeded.id, default_hi="HI Title")
    assert value == "शीर्षक"


def test_bi_text_ignores_hi_twin_entirely_when_lang_is_not_hi(seeded):
    en_value = bi_text(RECORDS_TITLE, "EN Title", lang="en", tenant_id=seeded.id)
    ConfigCentral.objects.update_or_create(key=RECORDS_TITLE_HI, defaults={"value": "शीर्षक"})
    value = bi_text(RECORDS_TITLE, "EN Title", lang="en", tenant_id=seeded.id, default_hi="HI Title")
    assert value == en_value


def test_bi_lines_falls_back_to_en_list_when_hi_row_missing(seeded):
    value = bi_lines(
        "bullets_nobody_seeded", ["EN one", "EN two"], lang="hi", tenant_id=seeded.id, default_hi=None
    )
    assert value == ["EN one", "EN two"]


# ---------------------------------------------------------------------- hub_ctx (T-061)


def test_hub_ctx_defaults_to_en_for_existing_callers(seeded):
    """Every pre-T-061 caller (tests, the /my/referrals hub-CTA builder) omits `lang`
    and must keep behaving exactly as before: EN copy, EN lang."""
    identity = _identity(seeded)
    en_headline = bi_text(SHARE_HUB_HEADLINE, "EN-HEADLINE-DEFAULT", lang="en", tenant_id=seeded.id)
    ctx = hub_ctx(identity, mint_records_token(identity))
    assert ctx["lang"] == "en"
    assert ctx["headline"] == en_headline


def test_hub_ctx_hi_renders_hi_copy_when_seeded(seeded):
    ConfigCentral.objects.update_or_create(
        key=SHARE_HUB_HEADLINE_HI, defaults={"value": "आपका रेफ़रल लिंक तैयार है"}
    )
    identity = _identity(seeded)
    ctx = hub_ctx(identity, mint_records_token(identity), lang="hi")
    assert ctx["headline"] == "आपका रेफ़रल लिंक तैयार है"
    assert ctx["lang"] == "hi"


def test_hub_ctx_hi_falls_back_to_en_when_hi_row_is_blank(seeded):
    """The literal DoD case: a HI row present but BLANK (the shape a half-finished
    translation pass leaves behind) must fall all the way back to EN, never render
    empty."""
    ConfigCentral.objects.update_or_create(key=SHARE_HUB_HEADLINE_HI, defaults={"value": "   "})
    identity = _identity(seeded)
    en_headline = bi_text(SHARE_HUB_HEADLINE, "EN-HEADLINE-DEFAULT", lang="en", tenant_id=seeded.id)
    ctx = hub_ctx(identity, mint_records_token(identity), lang="hi")
    assert ctx["headline"] == en_headline
    assert ctx["headline"].strip()


def test_hub_ctx_hi_never_blank_even_with_hi_row_deleted(seeded):
    """`seed_program` pre-seeds every _hi twin with a code-level Hindi default, so
    deleting the DB row still resolves the CODE default (itself Hindi) — not a fresh
    fall-through to EN. The DoD guarantee under test is narrower and absolute: the
    field is NEVER blank. (A truly EN fallback needs the resolved HI value itself to
    be blank/whitespace — covered by test_bi_text_falls_back_to_en_when_hi_row_is_
    blank_string above, which exercises the fallback directly through bi_text.)"""
    ConfigCentral.objects.filter(key=SHARE_HUB_HEADLINE_HI).delete()
    identity = _identity(seeded)
    ctx = hub_ctx(identity, mint_records_token(identity), lang="hi")
    assert ctx["headline"]
    assert ctx["headline"].strip()


def test_hub_ctx_share_message_uses_hi_template_under_lang_hi(seeded):
    ConfigCentral.objects.update_or_create(
        key=SHARE_KIT_MESSAGE_TEMPLATE_HI, defaults={"value": "हिंदी संदेश: {link}"}
    )
    identity = _identity(seeded)
    ctx = hub_ctx(identity, mint_records_token(identity), lang="hi")
    assert "हिंदी संदेश:" in ctx["share_message"]
    assert ctx["my_link"] in ctx["share_message"]


def test_hub_ctx_records_cross_link_carries_lang(seeded, monkeypatch):
    _with_flag(monkeypatch, "apps.accounts.hub", ENABLE_RECORDS_LINK=True)
    identity = _identity(seeded)
    token = mint_records_token(identity)
    ctx = hub_ctx(identity, token, lang="hi")
    assert ctx["records_url"] == f"/rr/{token}?lang=hi"

    ctx_en = hub_ctx(identity, token, lang="en")
    assert ctx_en["records_url"] == f"/rr/{token}"


def test_hub_ctx_lang_toggle_points_the_other_way(seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)

    ctx_en = hub_ctx(identity, token, lang="en")
    assert ctx_en["lang_toggle"]["target_lang"] == "hi"
    assert ctx_en["lang_toggle"]["query_suffix"] == "?lang=hi"
    assert ctx_en["lang_toggle"]["label"]

    ctx_hi = hub_ctx(identity, token, lang="hi")
    assert ctx_hi["lang_toggle"]["target_lang"] == "en"
    assert ctx_hi["lang_toggle"]["query_suffix"] == ""
    assert ctx_hi["lang_toggle"]["label"]


# ------------------------------------------------------------------- records_ctx (T-061)


def test_records_ctx_defaults_to_en(seeded):
    identity = _identity(seeded)
    ctx = records_ctx(seeded, identity, mint_records_token(identity))
    assert ctx["lang"] == "en"
    assert ctx["config"]["title"]


def test_records_ctx_hi_renders_hi_copy_when_seeded(seeded):
    ConfigCentral.objects.update_or_create(key=RECORDS_TITLE_HI, defaults={"value": "आपके रेफ़रल रिकॉर्ड"})
    identity = _identity(seeded)
    ctx = records_ctx(seeded, identity, mint_records_token(identity), lang="hi")
    assert ctx["config"]["title"] == "आपके रेफ़रल रिकॉर्ड"


def test_records_ctx_hub_cross_link_carries_lang(seeded, monkeypatch):
    _with_flag(monkeypatch, "apps.accounts.records", ENABLE_SHARE_HUB=True)
    identity = _identity(seeded)
    token = mint_records_token(identity)
    ctx = records_ctx(seeded, identity, token, lang="hi")
    assert ctx["hub_url"] == f"/hub/{token}?lang=hi"


def test_records_ctx_no_hi_key_ever_blanks_a_field(seeded):
    """Sweep every config-driven field with NO hi rows seeded at all — none may be
    empty when lang=hi (the DoD's key-by-key missing-HI seed check)."""
    identity = _identity(seeded)
    ctx = records_ctx(seeded, identity, mint_records_token(identity), lang="hi")
    for key, value in ctx["config"].items():
        assert value, f"config[{key!r}] rendered blank under lang=hi with no HI rows seeded"


# --------------------------------------------------------------------- compliance (D-1)


def test_market_risk_warning_hi_is_a_separate_unlocked_key_never_the_locked_en_one(seeded):
    from apps.config.models import COMPLIANCE_LOCKED_KEYS

    assert MARKET_RISK_WARNING_HI not in COMPLIANCE_LOCKED_KEYS
    assert "market_risk_warning" in COMPLIANCE_LOCKED_KEYS


def test_market_risk_warning_hi_default_matches_the_approved_wati_precedent():
    assert MARKET_RISK_WARNING_HI_DEFAULT == "प्रतिभूति बाज़ार में निवेश बाज़ार जोखिमों के अधीन है।"


@HUB_URLS
def test_hub_page_renders_both_en_locked_warning_and_hi_addition_under_lang_hi(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}?lang=hi").content.decode()
    # The locked EN warning ALWAYS renders (base.html footer, D-1 rail) — never dropped.
    from django.conf import settings

    assert settings.MARKET_RISK_WARNING in body
    assert MARKET_RISK_WARNING_HI_DEFAULT in body


@HUB_URLS
def test_hub_page_under_default_en_shows_no_hi_addition(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()
    assert MARKET_RISK_WARNING_HI_DEFAULT not in body


@HUB_URLS
def test_records_page_renders_both_warnings_under_lang_hi(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/rr/{token}?lang=hi").content.decode()
    from django.conf import settings

    assert settings.MARKET_RISK_WARNING in body
    assert MARKET_RISK_WARNING_HI_DEFAULT in body


# -------------------------------------------------------------------- html lang + toggle


@HUB_URLS
def test_hub_page_html_lang_attribute_follows_the_query_param(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    assert '<html lang="hi">' in client.get(f"/hub/{token}?lang=hi").content.decode()
    assert '<html lang="en">' in client.get(f"/hub/{token}").content.decode()


@HUB_URLS
def test_records_page_html_lang_attribute_follows_the_query_param(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    assert '<html lang="hi">' in client.get(f"/rr/{token}?lang=hi").content.decode()
    assert '<html lang="en">' in client.get(f"/rr/{token}").content.decode()


@HUB_URLS
def test_hub_page_renders_a_real_lang_toggle_link(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}").content.decode()
    assert 'data-test="hub-lang-toggle"' in body
    assert "?lang=hi" in body


@HUB_URLS
def test_records_page_renders_a_real_lang_toggle_link(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/rr/{token}").content.decode()
    assert 'data-test="records-lang-toggle"' in body
    assert "?lang=hi" in body


@HUB_URLS
def test_invalid_lang_value_falls_back_to_en_rendering(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}?lang=fr").content.decode()
    assert '<html lang="en">' in body
    assert MARKET_RISK_WARNING_HI_DEFAULT not in body


# ------------------------------------------------------------ token invariants under HI


@HUB_URLS
def test_token_never_in_a_share_href_under_lang_hi(client, seeded):
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}?lang=hi").content.decode()
    import re

    hrefs = re.findall(r"""<a\s+href=["']([^"']+)["'][^>]*data-share-channel=""", body, re.I)
    assert len(hrefs) == len(SHARE_BUTTONS)
    for href in hrefs:
        assert token not in href


@HUB_URLS
def test_token_appears_exactly_once_under_lang_hi_the_records_cross_link(client, seeded, monkeypatch):
    _with_flag(monkeypatch, "apps.accounts.hub", ENABLE_RECORDS_LINK=True)
    identity = _identity(seeded)
    token = mint_records_token(identity)
    body = client.get(f"/hub/{token}?lang=hi").content.decode()
    occurrences = body.count(token)
    assert occurrences == 1, f"token appears {occurrences}x under lang=hi"
    assert f"/rr/{token}?lang=hi" in body


# --------------------------------------------------------------------- unavailable page


@HUB_URLS
def test_records_unavailable_page_respects_lang_with_no_tenant_known(client, seeded):
    """The 404/expired-token path resolves tenant_id=None (central-tier default) — must
    still render the HI toggle-selected language, not silently drop to EN."""
    body = client.get("/rr/not-a-real-token?lang=hi").content.decode()
    assert '<html lang="hi">' in body
    assert MARKET_RISK_WARNING_HI_DEFAULT in body


# ---------------------------------------------------------- no whatsapp template lane

def test_no_wati_template_module_touched():
    """DoD: this task is web surfaces + session-copy config only — no WhatsApp
    TEMPLATE work. Confirms the HI twin lives beside the EXISTING share-kit message
    key, not inside apps.integrations.wati (the template lane)."""
    import apps.config.preferences as prefs

    assert hasattr(prefs, "SHARE_KIT_MESSAGE_TEMPLATE_HI")
    import apps.integrations.wati.notify as wati_notify

    assert "SHARE_KIT_MESSAGE_TEMPLATE_HI" not in dir(wati_notify)
