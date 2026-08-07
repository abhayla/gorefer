"""T-051 — the tokened, read-only "Referral Records" page (GET /rr/{token}).

What this locks down:
  - the token round-trips, and fails CLOSED on tamper, expiry and rotation;
  - rotation is per-referrer: bumping one epoch must not touch anybody else's link;
  - every referred person's name + mobile are masked, asserted on the RESPONSE BYTES
    (the /my/referrals partner-code leak of 2026-07-26 got in through a field nobody
    thought was client-facing — bytes, not intentions, are the check);
  - all four failure modes render ONE identical page, so the endpoint is no oracle;
  - the surface is read-only (no form, exactly one new GET route) and absent entirely
    when ENABLE_RECORDS_LINK is off;
  - guardrail 3: no partner code, no raw Zerodha URL in the response;
  - the page-view event carries ids only — no name, no mobile, no token.
"""
from __future__ import annotations

from unittest import mock

import pytest
from django.core import signing
from django.core.management import call_command

from apps.accounts.models import RecordsLinkState
from apps.accounts.records_link import (
    SECONDS_PER_DAY,
    TOKEN_SALT,
    mint_records_token,
    rotate_records_token,
    ttl_days,
    verify_records_token,
)
from apps.common.masking import mask_mobile, mask_name
from apps.config.models import ConfigCentral
from apps.config.preferences import RECORDS_LINK_TTL_DAYS
from apps.events.models import PII_KEYS, Event
from apps.referrals.models import Lead, Prospect, Referral, ReferralIdentity, ReferralProgram
from apps.tenants.models import Tenant

CID = "RJ4521"
OTHER_CID = "EKU497"
RAW_NAME = "Rahul"
RAW_MOBILE = "919876543221"

pytestmark = pytest.mark.django_db

RECORDS_URLS = pytest.mark.urls("tests.urls_records_link")


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


def _identity(tenant, client_id: str) -> ReferralIdentity:
    program = ReferralProgram.objects.get(tenant=tenant)
    return ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner, client_id=client_id
    )


def _lead(tenant, identity, *, name=RAW_NAME, mobile=RAW_MOBILE, status="new"):
    program = ReferralProgram.objects.get(tenant=tenant)
    # One journey per (identity, source) — the partial unique constraint on Referral
    # models exactly that, so several referred people hang off the SAME journey.
    referral, _ = Referral.objects.get_or_create(
        tenant=tenant, program=program, referral_identity=identity, source="referral_link"
    )
    prospect = Prospect.objects.create(tenant=tenant, mobile=mobile, name=name)
    return Lead.objects.create(
        tenant=tenant, referral=referral, prospect=prospect, status=status
    )


def _mint_aged(identity, days_ago: int) -> str:
    """A token that was minted `days_ago` days ago.

    Signing timestamps come from `time.time()` inside django.core.signing, so an old
    token is produced by minting under a patched clock — the only way to test expiry
    without adding a freezegun dependency for one assertion.
    """
    import time as _time

    with mock.patch.object(
        signing.time, "time", return_value=_time.time() - days_ago * SECONDS_PER_DAY
    ):
        return mint_records_token(identity)


# --------------------------------------------------------------------------- masking


def test_mask_name_keeps_two_and_one():
    assert mask_name(RAW_NAME) == "Ra••••l"
    assert mask_name("Rahul Sharma") == "Ra••••a"
    # A fixed bullet run, so the mask never leaks how long the name is.
    assert mask_name("Ab") == "A••"
    assert mask_name("Anu") == "A••"
    assert mask_name("") == ""
    assert mask_name(None) == ""


def test_mask_mobile_keeps_two_and_two_of_the_national_number():
    assert mask_mobile(RAW_MOBILE) == "98••••••21"
    # Same output whichever stored form it arrives in — one normalizer, no drift.
    assert mask_mobile("9876543221") == "98••••••21"
    assert mask_mobile("+91 98765 43221") == "98••••••21"
    assert mask_mobile("") == ""
    assert mask_mobile(None) == ""


# ----------------------------------------------------------------------- token service


def test_token_round_trips(seeded):
    identity = _identity(seeded, CID)
    assert verify_records_token(mint_records_token(identity)).pk == identity.pk


def test_minting_creates_the_revocation_row_at_epoch_one(seeded):
    identity = _identity(seeded, CID)
    mint_records_token(identity)
    state = RecordsLinkState.objects.get(identity=identity)
    assert state.epoch == 1
    assert state.tenant_id == seeded.id


def test_tampered_token_is_rejected(seeded):
    identity = _identity(seeded, CID)
    token = mint_records_token(identity)
    assert verify_records_token(token[:-1] + ("A" if token[-1] != "A" else "B")) is None
    assert verify_records_token("not-a-token") is None
    assert verify_records_token("") is None
    assert verify_records_token(None) is None


def test_a_token_signed_with_another_salt_is_rejected(seeded):
    identity = _identity(seeded, CID)
    forged = signing.dumps({"t": seeded.id, "i": identity.pk, "e": 1}, salt="some-other-salt")
    assert verify_records_token(forged) is None


def test_expired_token_is_rejected(seeded):
    identity = _identity(seeded, CID)
    assert verify_records_token(_mint_aged(identity, 89)) is not None
    assert verify_records_token(_mint_aged(identity, 91)) is None


def test_ttl_is_cascade_config_not_a_literal(seeded):
    identity = _identity(seeded, CID)
    assert ttl_days(seeded.id) == 90
    ConfigCentral.objects.update_or_create(
        key=RECORDS_LINK_TTL_DAYS, defaults={"value": 7}
    )
    assert ttl_days(seeded.id) == 7
    # Shortening the window kills links ALREADY minted — the whole point of resolving
    # the TTL at verify time rather than baking it into the token.
    assert verify_records_token(_mint_aged(identity, 30)) is None
    # A nonsensical stored value falls back to the default instead of killing every link.
    ConfigCentral.objects.update_or_create(key=RECORDS_LINK_TTL_DAYS, defaults={"value": 0})
    assert ttl_days(seeded.id) == 90


def test_rotation_kills_that_referrers_tokens_only(seeded):
    mine = _identity(seeded, CID)
    theirs = _identity(seeded, OTHER_CID)
    my_first, my_second = mint_records_token(mine), mint_records_token(mine)
    their_token = mint_records_token(theirs)

    assert rotate_records_token(mine) == 2
    # EVERY token previously minted for this referrer dies, not just the latest.
    assert verify_records_token(my_first) is None
    assert verify_records_token(my_second) is None
    # …and nobody else is affected.
    assert verify_records_token(their_token).pk == theirs.pk
    # A freshly minted one works again.
    assert verify_records_token(mint_records_token(mine)).pk == mine.pk


def test_a_missing_state_row_fails_closed(seeded):
    """T-052: no revocation row → every token for that referrer is INVALID.

    The old code defaulted a missing row to epoch 1, so deleting the row (a manual DB
    op, a bad cleanup script) silently revived every epoch-1 token ever minted. Minting
    always creates the row, so "no row" can only mean state we cannot vouch for.
    """
    identity = _identity(seeded, CID)
    first, second = mint_records_token(identity), mint_records_token(identity)
    RecordsLinkState.objects.filter(identity=identity).delete()

    assert verify_records_token(first) is None
    assert verify_records_token(second) is None
    # Minting again re-creates the row, so the referrer is not locked out forever.
    assert verify_records_token(mint_records_token(identity)).pk == identity.pk


def test_rotation_holds_when_the_state_rows_tenant_diverges(seeded):
    """T-052 regression — the checker's PROBE-D/E sequence, verbatim.

    A referrer whose identity predates the tenant backfill gets a TENANTLESS state row;
    the identity is later backfilled with a tenant, so tokens minted from then on carry
    `t=<tenant>`. The old lookup re-filtered the state row by that payload tenant, missed
    the tenantless row, fell back to epoch 1 — and rotation INVERTED: the pre-rotation
    token kept working while the freshly minted one was refused.
    """
    identity = _identity(seeded, CID)
    mint_records_token(identity)
    # The divergence: state row tenantless, identity still carrying its tenant.
    RecordsLinkState.objects.filter(identity=identity).update(tenant=None)
    assert identity.tenant_id is not None

    old_token = mint_records_token(identity)
    assert verify_records_token(old_token).pk == identity.pk, "pre-rotation token should work"

    rotate_records_token(identity)
    new_token = mint_records_token(identity)

    # Rotation points the right way: OLD dead, NEW alive (the old code had it backwards).
    assert verify_records_token(old_token) is None
    assert verify_records_token(new_token).pk == identity.pk


def test_disabled_identity_cannot_be_opened(seeded):
    identity = _identity(seeded, CID)
    token = mint_records_token(identity)
    identity.status = "disabled"
    identity.save(update_fields=["status"])
    assert verify_records_token(token) is None


# ------------------------------------------------------------------------------ page


@RECORDS_URLS
def test_valid_token_renders_masked_records(client, seeded):
    identity = _identity(seeded, CID)
    _lead(seeded, identity)
    resp = client.get(f"/rr/{mint_records_token(identity)}")

    assert resp.status_code == 200
    body = resp.content.decode()
    # The masked forms are what the visitor sees…
    assert mask_name(RAW_NAME) in body
    assert mask_mobile(RAW_MOBILE) in body
    # …and the raw PII appears NOWHERE in the response bytes.
    assert RAW_NAME not in body
    assert RAW_MOBILE not in body
    assert "9876543221" not in body


@RECORDS_URLS
def test_page_shows_the_aggregate_funnel(client, seeded):
    identity = _identity(seeded, CID)
    _lead(seeded, identity, name="Anita", mobile="919000000001", status="account_opened")
    _lead(seeded, identity, name="Bhavna", mobile="919000000002")
    resp = client.get(f"/rr/{mint_records_token(identity)}")
    ctx = resp.context["totals"]
    assert (ctx["referrals"], ctx["converted"], ctx["pending"]) == (2, 1, 1)
    assert resp.context["first_referred_at"] is not None


@RECORDS_URLS
def test_page_is_read_only(client, seeded):
    identity = _identity(seeded, CID)
    _lead(seeded, identity)
    body = client.get(f"/rr/{mint_records_token(identity)}").content.decode()
    assert "<form" not in body.lower()
    # …and the route itself refuses anything but GET.
    assert client.post(f"/rr/{mint_records_token(identity)}").status_code == 405


@RECORDS_URLS
def test_page_offers_the_step_up_login(client, seeded):
    identity = _identity(seeded, CID)
    body = client.get(f"/rr/{mint_records_token(identity)}").content.decode()
    assert "/login/" in body
    assert "Log in for full details" in body


@RECORDS_URLS
@pytest.mark.parametrize("case", ["invalid", "expired", "rotated"])
def test_all_failures_render_one_identical_page(client, seeded, case):
    identity = _identity(seeded, CID)
    _lead(seeded, identity)
    if case == "invalid":
        token = "garbage-token"
    elif case == "expired":
        token = _mint_aged(identity, 200)
    else:
        token = mint_records_token(identity)
        rotate_records_token(identity)

    resp = client.get(f"/rr/{token}")
    body = resp.content.decode()
    assert resp.status_code == 404
    assert "This link has expired" in body
    assert "/login/" in body
    # Zero referral data leaks on the failure page — not even a masked name.
    assert mask_name(RAW_NAME) not in body
    assert CID not in body


@RECORDS_URLS
def test_no_partner_code_or_zerodha_url_in_the_response(client, seeded, settings):
    identity = _identity(seeded, CID)
    _lead(seeded, identity)
    body = client.get(f"/rr/{mint_records_token(identity)}").content.decode()
    assert settings.PARTNER_CODE not in body
    assert "signup.zerodha.com" not in body


@RECORDS_URLS
def test_view_emits_a_pii_free_event(client, seeded):
    identity = _identity(seeded, CID)
    _lead(seeded, identity)
    token = mint_records_token(identity)
    client.get(f"/rr/{token}")

    event = Event.objects.get(event_type="records_link_viewed")
    assert event.tenant_id == seeded.id
    assert event.metadata == {"client_id": CID}
    assert not ({k.lower() for k in event.metadata} & PII_KEYS)
    payload = str(event.metadata)
    assert RAW_NAME not in payload
    assert RAW_MOBILE not in payload
    # The token must never enter the append-only log — it is a live credential.
    assert token not in payload


@RECORDS_URLS
def test_a_failed_open_records_no_event(client, seeded):
    client.get("/rr/garbage")
    assert not Event.objects.filter(event_type="records_link_viewed").exists()


# ------------------------------------------------------------------------------ flag


def test_route_is_absent_when_the_flag_is_off(client, seeded):
    """Default flags have ENABLE_RECORDS_LINK off, so the prod urlconf must not mount
    it at all — no dead route (Constitution §4)."""
    from gorefer.flags import flags

    assert flags.ENABLE_RECORDS_LINK is False
    assert client.get("/rr/anything").status_code == 404


@RECORDS_URLS
def test_route_is_present_when_the_flag_is_on(client, seeded):
    identity = _identity(seeded, CID)
    assert client.get(f"/rr/{mint_records_token(identity)}").status_code == 200


def test_the_flag_mounts_exactly_one_new_get_route():
    """Read-only, proven structurally: the gated urlconf adds ONE pattern over base."""
    from gorefer.urls import urlpatterns as base
    from tests import urls_records_link

    added = urls_records_link.urlpatterns[len(base):]
    assert len(added) == 1
    assert added[0].name == "records_link"


def test_the_token_salt_is_namespaced():
    """A shared salt would let a token minted for another purpose open this page."""
    assert TOKEN_SALT.startswith("gorefer.records-link")
