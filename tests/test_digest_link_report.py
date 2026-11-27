"""Daily digest layout v2 — the link report (T-link-tracking, owner 2026-11-27).

Pins: what each figure counts (from real link hits), the slot shape Meta accepts (21
non-empty values, no newline/tab/4+ spaces), the length guard, the v1 default staying
byte-for-byte the old report, the v2 switch + rollback, and accounts by TRUE date.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.test import Client
from django.utils import timezone

from apps.campaigns import digest, digest_links
from apps.config.cascade import set_tenant
from apps.config.preferences import (
    MESSAGING_DIGEST_LAYOUT,
    MESSAGING_DIGEST_LAYOUT_DEFAULT,
    MESSAGING_DIGEST_PARAMS_BUDGET,
    MESSAGING_DIGEST_RECIPIENTS,
    MESSAGING_DIGEST_TEMPLATE_EN_DEFAULT,
    MESSAGING_DIGEST_TEMPLATE_EN_V2,
    MESSAGING_DIGEST_TEMPLATE_EN_V2_DEFAULT,
    MESSAGING_DIGEST_TOP_IDS_CAP,
    MESSAGING_DIGEST_TOP_IDS_CAP_DEFAULT,
)
from apps.events.models import Event
from apps.integrations.models import Conversion
from apps.integrations.zoho.read import SendQueueCounts
from apps.referrals.models import ReferralProgram
from tests.test_t127_funnel_digest import IST_OFFSET, _FakeCrmRead, _FakeMessaging, tenant  # noqa: F401

HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.9"}
EMPTY_ZOHO = {
    "referral_total": 0, "delivered": 0, "not_delivered": 0, "rate_pct": None, "capped": 0,
    "invalid": 0, "failed": 0, "pending": 0, "other_total": 0, "other_breakdown": {}, "truncated": False,
}


def _today():
    return (timezone.now() + IST_OFFSET).date()


def _hit(path, capture, client=None):
    with capture(execute=True):
        return (client or Client()).get(path, **HUMAN)


@pytest.fixture
def share_urls(settings):
    settings.ROOT_URLCONF = "tests.urls_share_intent"


@pytest.mark.django_db(transaction=True)
def test_link_counts_from_real_hits(tenant, share_urls, django_capture_on_commit_callbacks):  # noqa: F811
    cap = django_capture_on_commit_callbacks
    _hit("/zerodha/open", cap)                       # open link
    _hit("/zerodha/open/yt/hi", cap)                 # PIFS's own tagged post: still the open link
    _hit("/zerodha/open/wa", cap)                    # Step 2
    _hit("/zerodha/r/wa/XY9876", cap)                # referral link x2
    _hit("/zerodha/r/XY9876", cap)
    _hit("/zerodha/r/AB1234", cap)
    _hit("/zerodha/r/open", cap)                     # no-referrer: not the open link
    _hit("/zeroda/open", cap)                        # broken link -> fallback...
    _hit("/zerodha/open?from=fallback", cap)         # ...and the click it lands on
    _hit("/zerodha/share/wa/XY9876", cap)            # share with ID
    _hit("/zerodha/share/wa/KITEID?skip=1", cap)     # share without ID (pop-up skip)
    _hit("/d/pifs", cap)                             # disclosure
    visitor = Client()
    _hit("/zerodha/share/wa/KITEID", cap, visitor)   # share pop-up shown twice to one person
    _hit("/zerodha/share/wa/KITEID", cap, visitor)
    _hit("/zerodha/share/wa/KITEID?kite_id=9876543210", cap, visitor)  # wrong (a mobile)
    _hit("/zerodha/share/wa/KITEID?kite_id=RJ4521", cap, visitor)      # typed ID
    _hit("/zerodha/r/wa/KITEID", cap)                # referral pop-up shown
    _hit("/zerodha/r/wa/KITEID?skip=1", cap)         # "I don't have one"

    c = digest_links.link_counts(tenant, _today())
    assert (c["open_link"], c["step2"], c["fallback"]) == (2, 1, 1)
    assert c["referral_link"] == 3
    assert c["referral_ids"] == [("XY9876", 2), ("AB1234", 1)]
    assert (c["share_with_id"], c["share_without_id"]) == (1, 1)
    assert c["share_ids"] == [("XY9876", 1)]
    assert c["disclosure"] == 1
    assert c["share_prompt"] == {"shown": 2, "visitors": 1, "entered": 1, "skipped": 1, "wrong": 1}
    assert c["referral_prompt"] == {"shown": 1, "visitors": 1, "entered": 0, "skipped": 1, "wrong": 0}
    assert c["entered_ids"] == [("RJ4521", 1)]
    assert c["new_referrers"] == 2  # XY9876 and AB1234 clicked for the first time today
    for ev in Event.objects.all():
        assert "9876543210" not in str(ev.metadata)


@pytest.mark.django_db(transaction=True)
def test_bots_and_other_days_are_not_counted(tenant, django_capture_on_commit_callbacks):  # noqa: F811
    with django_capture_on_commit_callbacks(execute=True):
        Client().get("/zerodha/open", HTTP_USER_AGENT="WhatsApp/2.23.20 A")
        Client().get("/d/pifs", HTTP_USER_AGENT="facebookexternalhit/1.1")
        Client().get("/zerodha/open", HTTP_USER_AGENT="curl/8.0")  # synthetic
    _hit("/zerodha/open", django_capture_on_commit_callbacks)
    Event.objects.update(timestamp=timezone.now() - timedelta(days=2))
    c = digest_links.link_counts(tenant, _today())
    assert (c["open_link"], c["disclosure"], c["clicks"]) == (0, 0, 0)


def test_accounts_use_the_true_zoho_date(tenant):  # noqa: F811
    program = ReferralProgram.objects.get(tenant=tenant)
    day = date(2026, 11, 20)
    noon = timezone.datetime(2026, 11, 20, 6, 30, tzinfo=dt_timezone.utc)
    Conversion.objects.create(tenant=tenant, program=program, zoho_lead_id="L1",
                              referrer_client_id="XY9876", account_opened_at=noon)
    Conversion.objects.create(tenant=tenant, program=program, zoho_lead_id="L2",
                              referrer_client_id="XY9876", account_opened_at=noon)
    Conversion.objects.create(tenant=tenant, program=program, zoho_lead_id="L3",
                              account_opened_at=noon, is_reversed=True)
    # Imported today but opened on the 20th: lands on the 20th, never today (ADR-017).
    Conversion.objects.create(tenant=tenant, program=program, zoho_lead_id="L4",
                              account_opened_at=noon - timedelta(days=5))
    assert digest_links._accounts_opened(tenant, day) == {"total": 2, "top": ("XY9876", 2)}
    assert digest_links._accounts_opened(tenant, _today())["total"] == 0


# --------------------------------------------------------------------------- slot shape

def _links(**over):
    base = {
        "clicks": 14, "open_link": 12, "step2": 4, "fallback": 1, "referral_link": 8,
        "referral_ids": [("XY9876", 5), ("AB1234", 3)],
        "share_with_id": 4, "share_without_id": 1, "share_ids": [("XY9876", 3), ("RJ4521", 1)],
        "disclosure": 3,
        "share_prompt": {"shown": 6, "visitors": 4, "entered": 3, "skipped": 1, "wrong": 2},
        "referral_prompt": {"shown": 2, "visitors": 2, "entered": 1, "skipped": 1, "wrong": 0},
        "entered_ids": [("XY9876", 2), ("AB1234", 1)], "new_referrers": 1,
        "accounts": {"total": 2, "top": ("XY9876", 2)},
    }
    base.update(over)
    return base


AVG = {"open_link": 9, "step2": 2.5, "referral_link": 5, "share_with_id": 4.14, "disclosure": 0.43}


def test_v2_slots_read_as_designed():
    slots = digest_links.build_slots_v2(date(2026, 11, 26), EMPTY_ZOHO, _links(), AVG, "Abhay", cap=5)
    assert len(slots) == digest_links.SLOT_COUNT_V2 == 21
    assert slots[9] == "12 (7d avg 9)"
    assert slots[10] == "4 (7d avg 2.5)"
    assert slots[11] == "8 (7d avg 5) — XY9876 ×5 · AB1234 ×3"
    assert slots[12] == "4 with ID, 1 without (7d avg 4.1) — XY9876 ×3 · RJ4521 ×1"
    assert slots[13] == "3 (7d avg 0.4)"
    assert slots[14] == "shown 6 (4 people) · ID typed 3 · without ID 1 · wrong ID 2"
    assert slots[15] == "shown 2 (2 people) · ID typed 1 · no ID 1 · wrong ID 0"
    assert slots[16] == "XY9876 ×2 · AB1234 ×1"
    assert slots[17:] == ["14", "1", "2", "XY9876 (2)"]


def test_v2_values_are_meta_safe_even_on_an_empty_day():
    empty = _links(clicks=0, open_link=0, step2=0, referral_link=0, referral_ids=[], share_with_id=0,
                   share_without_id=0, share_ids=[], disclosure=0, entered_ids=[], new_referrers=0,
                   accounts={"total": 0, "top": None},
                   share_prompt={"shown": 0, "visitors": 0, "entered": 0, "skipped": 0, "wrong": 0},
                   referral_prompt={"shown": 0, "visitors": 0, "entered": 0, "skipped": 0, "wrong": 0})
    for slots in (digest_links.build_slots_v2(date(2026, 11, 26), EMPTY_ZOHO, empty, None, "Abhay", 5),
                  digest_links.build_slots_v2(date(2026, 11, 26), EMPTY_ZOHO, _links(), AVG, "Abhay", 5)):
        for v in slots:
            assert v and v.strip()                       # Meta rejects an empty variable
            assert not re.search(r"[\n\t]| {4,}", v)     # ... and newlines/tabs/4+ spaces (132018)


def test_long_lists_shrink_before_any_total_is_lost():
    many = [(f"AB{n:04d}", 100 - n) for n in range(40)]
    links = _links(referral_ids=many, share_ids=many, entered_ids=many)
    slots = digest_links.fit_slots_v2(date(2026, 11, 26), EMPTY_ZOHO, links, AVG, "Abhay", cap=5, budget=520)
    assert sum(len(v) for v in slots) <= 520
    assert slots[11].startswith("8 (7d avg 5) — ")       # the total stays
    assert "more" in slots[11] or "IDs" in slots[11]
    assert slots[16].endswith(("more", "IDs"))


def test_id_list_formats():
    assert digest_links.id_list([], 5) == "none"
    assert digest_links.id_list([("A1", 2), ("B2", 1)], 1) == "A1 ×2 · +1 more"
    assert digest_links.id_list([("A1", 2), ("B2", 1)], 0) == "2 IDs"


# --------------------------------------------------------------------------- switch

def _run(tenant, monkeypatch, **config):  # noqa: F811
    for key, value in {MESSAGING_DIGEST_RECIPIENTS: "919876543210", **config}.items():
        set_tenant(key, value, tenant_id=tenant.id)
    fake = _FakeMessaging()
    monkeypatch.setattr(digest, "get_crm_read_port",
                        lambda: _FakeCrmRead(SendQueueCounts(date_ist="x", referral={"SENT": 2}, other={})))
    monkeypatch.setattr(digest, "get_messaging_port", lambda: fake)
    return digest.run_digest_for_tenant(tenant, day=date(2026, 11, 26)), fake


def test_default_layout_is_still_the_v1_report(tenant, monkeypatch):  # noqa: F811
    assert MESSAGING_DIGEST_LAYOUT_DEFAULT == "v1"
    result, fake = _run(tenant, monkeypatch)
    (send,) = fake.template_sends
    assert send["template"] == MESSAGING_DIGEST_TEMPLATE_EN_DEFAULT
    assert len(send["params"]["template_params"]) == 15
    assert result["layout"] == "v1"


def test_v2_layout_sends_the_v2_template_and_v1_is_the_rollback(tenant, monkeypatch):  # noqa: F811
    result, fake = _run(tenant, monkeypatch, **{MESSAGING_DIGEST_LAYOUT: "v2"})
    (send,) = fake.template_sends
    assert send["template"] == MESSAGING_DIGEST_TEMPLATE_EN_V2_DEFAULT
    assert len(send["params"]["template_params"]) == 21
    assert result["results"][0]["outcome"] == "sent"  # terminal status read back, not HTTP 200
    result, fake = _run(tenant, monkeypatch, **{MESSAGING_DIGEST_LAYOUT: "v1"})
    assert len(fake.template_sends[0]["params"]["template_params"]) == 15


def test_v2_knobs_are_cascade_keys(tenant, monkeypatch):  # noqa: F811
    """Rail E-6 spot test: template name, id cap and budget resolve from the cascade."""
    assert MESSAGING_DIGEST_TOP_IDS_CAP_DEFAULT == 5
    _, fake = _run(tenant, monkeypatch, **{
        MESSAGING_DIGEST_LAYOUT: "v2", MESSAGING_DIGEST_TEMPLATE_EN_V2: "renamed_v2_template",
        MESSAGING_DIGEST_TOP_IDS_CAP: 1, MESSAGING_DIGEST_PARAMS_BUDGET: 520,
    })
    assert fake.template_sends[0]["template"] == "renamed_v2_template"


def test_unknown_layout_value_falls_back_to_v1(tenant, monkeypatch):  # noqa: F811
    _, fake = _run(tenant, monkeypatch, **{MESSAGING_DIGEST_LAYOUT: "v9"})
    assert len(fake.template_sends[0]["params"]["template_params"]) == 15
