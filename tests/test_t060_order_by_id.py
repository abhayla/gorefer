"""T-060 — T-054 checker finding 1: deterministic `.order_by('id')` on the
`ReferralIdentity` `.filter(client_id=...).first()` lookups in `api/records_tokens.py`
and `apps/accounts/selfview.py`.

Two different partners can legitimately hold the same raw `client_id` (uniqueness is
`(tenant, partner, client_id, id_source)` — see `ReferralIdentity.Meta`), so a plain
`.filter(client_id=...).first()` has no defined order and Postgres is free to return
either row. Both call sites now pin `.order_by("id")`, so the OLDEST identity for that
`client_id` always wins, regardless of insertion/scan order.
"""
from __future__ import annotations

import pytest
from django.core.management import call_command

from apps.accounts import selfview
from apps.referrals.models import Partner, ReferralIdentity, ReferralProgram
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

CID = "DUP001"


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


def _second_partner_program(tenant):
    """A second (partner, program) pair under the SAME tenant, so a shared client_id
    across the two partners is possible without violating the identity uniqueness
    constraint."""
    partner2 = Partner.objects.create(tenant=tenant, name="Second Partner", code="SECOND01")
    program2 = ReferralProgram.objects.create(
        tenant=tenant, partner=partner2, name="second", display_name="Second",
        status="active", regulator="sebi_nse",
    )
    return partner2, program2


def test_records_tokens_mint_resolves_the_oldest_identity_deterministically(seeded):
    """Two ReferralIdentity rows share CID under different partners; `_mint_one` (via
    `resolve_link_details`) must always resolve the older (lower id) one, on repeat
    calls, regardless of DB scan order."""
    from api.records_tokens import resolve_link_details

    program1 = ReferralProgram.objects.get(tenant=seeded)
    older = ReferralIdentity.objects.create(
        tenant=seeded, program=program1, partner=program1.partner, client_id=CID,
    )
    _, program2 = _second_partner_program(seeded)
    ReferralIdentity.objects.create(
        tenant=seeded, program=program2, partner=program2.partner, client_id=CID,
    )

    for _ in range(5):
        result = resolve_link_details(seeded, CID)
        assert "error" not in result
        from apps.accounts.records_link import verify_records_token
        assert verify_records_token(result["token"]).id == older.id


def test_selfview_program_brand_resolves_the_oldest_identity_deterministically(seeded, monkeypatch):
    """`_program_brand` must consistently pick the SAME (oldest) identity's program
    brand across repeated calls, never flipping between the two partners' brands."""

    program1 = ReferralProgram.objects.get(tenant=seeded)
    older = ReferralIdentity.objects.create(
        tenant=seeded, program=program1, partner=program1.partner, client_id=CID,
    )
    _, program2 = _second_partner_program(seeded)
    ReferralIdentity.objects.create(
        tenant=seeded, program=program2, partner=program2.partner, client_id=CID,
    )

    from apps.referrals.branding import brand_for_program

    expected = brand_for_program(older.program)
    for _ in range(5):
        assert selfview._program_brand(seeded, CID) == expected


def test_selfview_hub_url_resolves_the_oldest_identity_deterministically(seeded, monkeypatch):
    """`hub_url_for` must mint a token for the SAME (oldest) identity every call."""
    import dataclasses

    from gorefer.flags import flags as live_flags

    monkeypatch.setattr(
        "apps.accounts.selfview.flags", dataclasses.replace(live_flags, ENABLE_SHARE_HUB=True)
    )

    program1 = ReferralProgram.objects.get(tenant=seeded)
    older = ReferralIdentity.objects.create(
        tenant=seeded, program=program1, partner=program1.partner, client_id=CID,
    )
    _, program2 = _second_partner_program(seeded)
    ReferralIdentity.objects.create(
        tenant=seeded, program=program2, partner=program2.partner, client_id=CID,
    )

    from apps.accounts.records_link import verify_records_token

    for _ in range(5):
        url = selfview.hub_url_for(seeded, CID)
        assert url
        token = url.rsplit("/", 1)[-1]
        assert verify_records_token(token).id == older.id
