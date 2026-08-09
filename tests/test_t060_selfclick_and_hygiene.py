"""T-060 — self-click display tag (P-06/DF-11 display half) + three queued hygiene
fixes: deterministic ReferralIdentity lookups (T-054 finding 1), the `hub_cta`
cascade key (T-054 finding 2), and the T-054/T-057/T-058/T-059 checker's flagged
vacuous assertion in tests/test_t056_hub_program_brand.py (fixed in place there).

Self-click is DISPLAY-ONLY: it must never change any aggregate/rollup/count. That
invariant is asserted directly alongside the tag itself.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.config.models import ConfigGlobal
from apps.events.models import Event
from apps.integrations.zoho.read import ZohoContact
from apps.referrals.models import (
    Lead,
    Partner,
    Prospect,
    Referral,
    ReferralIdentity,
    ReferralProgram,
)
from apps.tenants.resolve import get_bootstrap_tenant

pytestmark = pytest.mark.django_db

CID = "SC1001"


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return get_bootstrap_tenant()


def _make_journey(tenant, client_id, *, lead_mobile):
    """One referral identity with one click that goes on to submit a lead with
    `lead_mobile`. Returns (referral, prospect)."""
    program = ReferralProgram.objects.get(tenant=tenant)
    identity = ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner,
        client_id=client_id, status="active",
    )
    ref = Referral.objects.create(
        tenant=tenant, program=program, referral_identity=identity,
        source="referral_link", status="opened",
    )
    prospect = Prospect.objects.create(tenant=tenant, mobile=lead_mobile, name="Friend")
    Lead.objects.create(tenant=tenant, referral=ref, prospect=prospect, status="new")
    t0 = timezone.now() - timedelta(hours=1)
    spec = [("click", 0, None), ("lead_captured", 2, prospect.pk)]
    for event_type, minutes, pid in spec:
        e = Event.objects.create(
            tenant=tenant, referral=ref, event_type=event_type, person_ref_id=pid
        )
        Event.objects.filter(pk=e.pk).update(timestamp=t0 + timedelta(minutes=minutes))
    return ref, prospect


class _FakeReadAdapter:
    """Stands in for get_zoho_read_adapter — matches the pattern already used by
    tests/test_referral_profile.py's _FakeReadAdapter."""

    def __init__(self, contacts: dict):
        self.contacts = contacts

    def fetch_contact_by_client_id(self, *, client_id):
        contact = self.contacts.get(client_id)
        if contact is None:
            return ZohoContact(client_id=client_id, matched=False)
        return contact

    def fetch_referred_people(self, *, referrer_client_id):
        from apps.integrations.zoho.read import ReferredPeople
        return ReferredPeople(referrer_client_id=referrer_client_id, people=[])


# --- self-click tag: matches ------------------------------------------------


def test_click_tagged_self_click_when_lead_mobile_matches_referrers_own(seeded, monkeypatch):
    from apps.dashboard.profile import clicks_rows

    _make_journey(seeded, CID, lead_mobile="919876543210")
    monkeypatch.setattr(
        "apps.integrations.zoho.read.get_zoho_read_adapter",
        lambda: _FakeReadAdapter({
            CID: ZohoContact(client_id=CID, matched=True, mobile="9876543210"),
        }),
    )
    rows = clicks_rows(seeded, CID)
    assert len(rows) == 1
    assert rows[0]["self_click"] is True


# --- self-click tag: does NOT match ------------------------------------------


def test_click_not_tagged_when_lead_mobile_differs(seeded, monkeypatch):
    from apps.dashboard.profile import clicks_rows

    _make_journey(seeded, CID, lead_mobile="919876500000")
    monkeypatch.setattr(
        "apps.integrations.zoho.read.get_zoho_read_adapter",
        lambda: _FakeReadAdapter({
            CID: ZohoContact(client_id=CID, matched=True, mobile="9876543210"),
        }),
    )
    rows = clicks_rows(seeded, CID)
    assert rows[0]["self_click"] is False


# --- unmatched / mobile-less / unreachable Zoho: no tag, render exactly as today --


def test_click_not_tagged_when_referrer_unmatched_in_zoho(seeded, monkeypatch):
    from apps.dashboard.profile import clicks_rows

    _make_journey(seeded, CID, lead_mobile="919876543210")
    monkeypatch.setattr(
        "apps.integrations.zoho.read.get_zoho_read_adapter",
        lambda: _FakeReadAdapter({}),  # no fixture => unmatched
    )
    rows = clicks_rows(seeded, CID)
    assert rows[0]["self_click"] is False
    # every other key renders exactly as it did before self-click existed
    assert set(rows[0]) == {
        "t", "partner", "channel", "city", "region", "country", "ip", "device", "ua",
        "bot", "synthetic", "self_click", "outcome", "outcome_class",
    }


def test_click_not_tagged_when_referrer_matched_but_no_mobile_on_file(seeded, monkeypatch):
    from apps.dashboard.profile import clicks_rows

    _make_journey(seeded, CID, lead_mobile="919876543210")
    monkeypatch.setattr(
        "apps.integrations.zoho.read.get_zoho_read_adapter",
        lambda: _FakeReadAdapter({CID: ZohoContact(client_id=CID, matched=True)}),
    )
    rows = clicks_rows(seeded, CID)
    assert rows[0]["self_click"] is False


def test_click_not_tagged_when_zoho_read_raises(seeded, monkeypatch):
    """An unreachable Zoho degrades to no tag — same degrade path as _safe_zoho_contact
    uses everywhere else on this page (never a guess)."""
    from apps.dashboard.profile import clicks_rows

    _make_journey(seeded, CID, lead_mobile="919876543210")

    class _Boom:
        def fetch_contact_by_client_id(self, *, client_id):
            raise RuntimeError("zoho unreachable")

    monkeypatch.setattr(
        "apps.integrations.zoho.read.get_zoho_read_adapter", lambda: _Boom()
    )
    rows = clicks_rows(seeded, CID)
    assert rows[0]["self_click"] is False


def test_click_with_no_lead_at_all_is_not_tagged(seeded, monkeypatch):
    """A bare click (no lead ever submitted) must never be tagged, matched referrer
    or not."""
    from apps.dashboard.profile import clicks_rows

    program = ReferralProgram.objects.get(tenant=seeded)
    identity = ReferralIdentity.objects.create(
        tenant=seeded, program=program, partner=program.partner,
        client_id=CID, status="active",
    )
    ref = Referral.objects.create(
        tenant=seeded, program=program, referral_identity=identity,
        source="referral_link", status="opened",
    )
    Event.objects.create(tenant=seeded, referral=ref, event_type="click")
    monkeypatch.setattr(
        "apps.integrations.zoho.read.get_zoho_read_adapter",
        lambda: _FakeReadAdapter({
            CID: ZohoContact(client_id=CID, matched=True, mobile="9876543210"),
        }),
    )
    rows = clicks_rows(seeded, CID)
    assert rows[0]["self_click"] is False
    assert rows[0]["outcome"] == "Clicked"


# --- DISPLAY-ONLY: zero aggregate/rollup/count mutation ----------------------


def test_self_click_never_changes_top_band_or_card_aggregates(seeded, monkeypatch):
    from apps.dashboard import profile

    _make_journey(seeded, CID, lead_mobile="919876543210")
    monkeypatch.setattr(
        "apps.integrations.zoho.read.get_zoho_read_adapter",
        lambda: _FakeReadAdapter({
            CID: ZohoContact(client_id=CID, matched=True, mobile="9876543210"),
        }),
    )
    rows = profile.clicks_rows(seeded, CID)
    assert rows[0]["self_click"] is True  # this click IS a self-click...

    band = profile.top_band(seeded, CID)
    assert band["aggregates"]["clicks"] == 1     # ...but every count is untouched
    assert band["aggregates"]["leads"] == 1
    cards = profile.per_link_cards(seeded, CID)
    assert cards[0]["clicks"] == 1
    assert cards[0]["leads"] == 1


# --- T-054 finding 1: deterministic ReferralIdentity lookups -----------------


def _two_partner_duplicate_client_id(tenant):
    """Two DIFFERENT partners' identities sharing one client_id — legal under the
    uq_referral_identity_key constraint (tenant, partner, client_id, id_source), and
    exactly the shape the T-054 checker flagged as ambiguous without an order_by."""
    program1 = ReferralProgram.objects.get(tenant=tenant)
    partner2 = Partner.objects.create(tenant=tenant, name="Second Partner", code="SECPTNR")
    program2 = ReferralProgram.objects.create(
        tenant=tenant, partner=partner2, name="second", display_name="Second",
        status="active", regulator="sebi_nse",
    )
    older = ReferralIdentity.objects.create(
        tenant=tenant, program=program1, partner=program1.partner,
        client_id="DUP0001", status="active",
    )
    newer = ReferralIdentity.objects.create(
        tenant=tenant, program=program2, partner=partner2,
        client_id="DUP0001", status="active",
    )
    assert older.id < newer.id
    return older, newer


def test_records_tokens_mint_resolves_deterministically_across_duplicate_client_id(seeded):
    from api.records_tokens import resolve_link_details
    from apps.accounts.records_link import verify_records_token

    older, _newer = _two_partner_duplicate_client_id(seeded)
    result = resolve_link_details(seeded, "DUP0001")
    resolved = verify_records_token(result["token"])
    assert resolved is not None
    assert resolved.id == older.id
    # deterministic across repeated calls, not just "happened to match once"
    result2 = resolve_link_details(seeded, "DUP0001")
    assert result2["token"] == result["token"] or verify_records_token(result2["token"]).id == older.id


def test_selfview_hub_url_for_resolves_deterministically_across_duplicate_client_id(
    seeded, monkeypatch
):
    import dataclasses

    from apps.accounts.records_link import verify_records_token
    from apps.accounts.selfview import hub_url_for
    from gorefer.flags import flags

    older, _newer = _two_partner_duplicate_client_id(seeded)
    # flags is a frozen snapshot — swap selfview's reference, never assert the env value
    # (the T-053 suite's _with_flag idiom; asserting raw env made this test env-dependent)
    monkeypatch.setattr(
        "apps.accounts.selfview.flags",
        dataclasses.replace(flags, ENABLE_SHARE_HUB=True),
    )
    url = hub_url_for(seeded, "DUP0001")
    assert url
    token = url.rsplit("/", 1)[-1]
    resolved = verify_records_token(token)
    assert resolved.id == older.id


def test_selfview_program_brand_resolves_deterministically_across_duplicate_client_id(seeded):
    from apps.accounts.selfview import _program_brand

    older, _newer = _two_partner_duplicate_client_id(seeded)
    brand = _program_brand(seeded, "DUP0001")
    # older is on program1 (Zerodha, seeded display_name) — never program2's "Second"
    assert brand != "Second"
    assert brand == (older.program.display_name or older.program.name)


# --- T-054 finding 2: hub_cta is a cascade key, default unchanged ------------


def test_hub_cta_default_is_unchanged_share_your_link(seeded):
    from apps.accounts.selfview import my_referrals_ctx
    from apps.config.preferences import MY_REFERRALS_HUB_CTA_DEFAULT

    assert MY_REFERRALS_HUB_CTA_DEFAULT == "Share your link"
    program = ReferralProgram.objects.get(tenant=seeded)
    ReferralIdentity.objects.create(
        tenant=seeded, program=program, partner=program.partner,
        client_id="CTA0001", status="active",
    )
    ctx = my_referrals_ctx(seeded, "CTA0001")
    assert ctx["hub_cta"] == "Share your link"


def test_hub_cta_is_overridable_through_the_cascade(seeded):
    from apps.accounts.selfview import my_referrals_ctx
    from apps.config.preferences import MY_REFERRALS_HUB_CTA

    program = ReferralProgram.objects.get(tenant=seeded)
    ReferralIdentity.objects.create(
        tenant=seeded, program=program, partner=program.partner,
        client_id="CTA0002", status="active",
    )
    ConfigGlobal.objects.create(tenant_id=seeded.id, key=MY_REFERRALS_HUB_CTA, value="Refer a friend")
    ctx = my_referrals_ctx(seeded, "CTA0002")
    assert ctx["hub_cta"] == "Refer a friend"
