"""Two share-message fixes (owner go-ahead 2026-11-02).

1. My Referrals' WhatsApp share text is now the SAME message the one-tap /share/wa/ link
   sends — the owner's edited share message, the referrer's own opener and the disclosure
   line — instead of a separate hard-coded sentence that ignored those edits.
2. The Preferences screen refuses a share message with no {link}, or with a placeholder
   the message builder can't fill (which would break the share link), and keeps the
   previous message.
"""
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.management import call_command
from django.test import Client

from apps.config import preferences as prefkeys
from apps.config.cascade import resolve, set_tenant
from apps.tenants.resolve import get_bootstrap_tenant

CID = "RJ4521"


@pytest.fixture
def tenant(db, settings):
    settings.PUBLIC_BASE_URL = "https://gorefer.in"
    call_command("seed_program")
    return get_bootstrap_tenant()


@pytest.mark.urls("tests.urls_share_intent")
def test_my_referrals_shares_exactly_what_the_one_tap_link_shares(tenant, django_capture_on_commit_callbacks):
    from apps.accounts.selfview import my_referrals_ctx

    set_tenant(prefkeys.SHARE_KIT_MESSAGE_TEMPLATE, "*Open a free {program_brand} account online:*\n{link}",
               tenant_id=tenant.id)
    with django_capture_on_commit_callbacks(execute=True):
        resp = Client().get(f"/share/wa/{CID}", HTTP_USER_AGENT="Mozilla/5.0 (Android)")
    one_tap = parse_qs(urlparse(resp.headers["Location"]).query)["text"][0]
    share_text = my_referrals_ctx(tenant, CID)["share_text"]
    assert share_text == one_tap
    assert share_text.startswith("*Open a free Zerodha account online:*\nhttps://gorefer.in/zerodha/r/wa/RJ4521")
    assert share_text.endswith("Disclosures: https://gorefer.in/d/pifs")


@pytest.mark.parametrize("message,reason", [
    ("Open a free account today!", "must contain {link}"),
    ("Open {program_brand}: {link} {name}", "only {link} and {program_brand}"),
    ("Broken {link} {", "only {link} and {program_brand}"),
])
def test_preferences_refuse_a_broken_share_message(tenant, message, reason):
    from apps.dashboard.preferences_service import save_preferences

    before = resolve(prefkeys.SHARE_KIT_MESSAGE_TEMPLATE, tenant_id=tenant.id)
    notices = save_preferences(tenant, {"share_kit_message_template": message})
    assert any("Share message (English)" in n and reason in n for n in notices), notices
    assert resolve(prefkeys.SHARE_KIT_MESSAGE_TEMPLATE, tenant_id=tenant.id) == before


def test_preferences_save_a_good_share_message_and_x_message(tenant):
    from apps.dashboard.preferences_service import save_preferences

    notices = save_preferences(tenant, {
        "share_kit_message_template": "Join {program_brand}: {link}",
        prefkeys.SHARE_KIT_MESSAGE_TEMPLATE_X: "X: {link}",
    })
    assert not any("Share message" in n for n in notices)
    assert resolve(prefkeys.SHARE_KIT_MESSAGE_TEMPLATE, tenant_id=tenant.id) == "Join {program_brand}: {link}"
    assert resolve(prefkeys.SHARE_KIT_MESSAGE_TEMPLATE_X, tenant_id=tenant.id) == "X: {link}"


def test_x_message_without_link_is_refused(tenant):
    from apps.dashboard.preferences_service import save_preferences

    notices = save_preferences(tenant, {prefkeys.SHARE_KIT_MESSAGE_TEMPLATE_X: "No link here"})
    assert any("Share message for X" in n for n in notices)
    assert resolve(prefkeys.SHARE_KIT_MESSAGE_TEMPLATE_X, tenant_id=tenant.id) == (
        prefkeys.SHARE_KIT_MESSAGE_TEMPLATE_X_DEFAULT
    )
