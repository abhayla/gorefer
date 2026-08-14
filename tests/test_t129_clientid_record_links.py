"""T-129 — client-ID "Referral Records" links (Meta strips colon tokens).

Root cause (proven live 2026-08-14 23:38 IST via a controlled A/B tap, nginx
by_host log): WhatsApp/Meta silently substitutes EMPTY for a URL-button variable
value containing ':'. A `django.core.signing` token is always colon-separated, so
every `[Referral Records]` button tap arrived at a blank `/rr/` and 404-ed.

Owner decision (2026-08-14 23:58 IST), superseding the url-safe-token direction:
the button carries the raw ZERODHA CLIENT ID instead. Client ids are already
public (Zerodha's own `r=` links), so a guessable `/rr/{client_id}` leaks nothing
new — the page it opens is the SAME masked, no-login view T-051 already ships.

What this file locks down:
  - `/rr/{client_id}` renders the masked records view directly, no token minted;
  - that view NEVER renders an unmasked name or full mobile logged-out;
  - `/rr/{legacy_token}` is untouched (T-051 regression covered in
    tests/test_t051_records_link.py — this file only proves the NEW branch);
  - `/rr/` and `/rr` (empty value) render the T-122 recovery page, not a 404;
  - a garbage, non-empty, non-client-id, non-token value renders the existing
    friendly "unavailable" page — never a crash;
  - every sender-bound RECORDS button value (records_link_send + campaign
    SendFamily) is colon-free and matches the safe URL-button charset — the
    CI-permanent lock against Meta's colon-stripping behavior recurring.
"""
from __future__ import annotations

import dataclasses
import re

import pytest
from django.conf import settings
from django.core.management import call_command

from api.records_tokens import resolve_link_details
from apps.accounts.records_link import mint_records_token
from apps.campaigns import send as campaign_send
from apps.common.masking import mask_mobile, mask_name
from apps.events.models import PII_KEYS, Event
from apps.integrations import records_link_send as rls
from apps.referrals.models import Lead, Prospect, Referral, ReferralIdentity, ReferralProgram
from apps.tenants.models import Tenant
from gorefer.flags import flags

CID = "RJ4521"
RAW_NAME = "Rahul"
RAW_MOBILE = "919876543221"

pytestmark = pytest.mark.django_db

RECORDS_URLS = pytest.mark.urls("tests.urls_records_link")

# The DoD-mandated safe charset for a value substituted into a WhatsApp URL button —
# no ':' (the exact character Meta silently strips the whole value on), and nothing
# else outside what a client_id / this charset can ever contain.
SAFE_BUTTON_VALUE_RE = r"^[A-Za-z0-9_.-]+$"


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
    referral, _ = Referral.objects.get_or_create(
        tenant=tenant, program=program, referral_identity=identity, source="referral_link"
    )
    prospect = Prospect.objects.create(tenant=tenant, mobile=mobile, name=name)
    return Lead.objects.create(tenant=tenant, referral=referral, prospect=prospect, status=status)


# --------------------------------------------------------------------- the client-id view


@RECORDS_URLS
def test_client_id_value_renders_masked_records(client, seeded):
    identity = _identity(seeded, CID)
    _lead(seeded, identity)
    resp = client.get(f"/rr/{CID}")

    assert resp.status_code == 200
    body = resp.content.decode()
    assert mask_name(RAW_NAME) in body
    assert mask_mobile(RAW_MOBILE) in body
    assert RAW_NAME not in body
    assert RAW_MOBILE not in body
    assert "9876543221" not in body


@RECORDS_URLS
def test_client_id_value_is_case_insensitive_like_every_other_client_id_path(client, seeded):
    identity = _identity(seeded, CID)
    _lead(seeded, identity)
    resp = client.get(f"/rr/{CID.lower()}")
    assert resp.status_code == 200


@RECORDS_URLS
def test_client_id_view_never_leaks_unmasked_pii_logged_out(client, seeded):
    """DoD: the client-id view must NEVER render an unmasked name or full mobile —
    masking is the security boundary now the URL is guessable by design."""
    identity = _identity(seeded, CID)
    _lead(seeded, identity, name="Priyanka Sharma", mobile="919000011122")
    body = client.get(f"/rr/{CID}").content.decode()

    assert "Priyanka Sharma" not in body
    assert "9000011122" not in body
    assert "919000011122" not in body
    # …and the masked forms ARE present — proving the assertion isn't vacuous.
    assert mask_name("Priyanka Sharma") in body
    assert mask_mobile("919000011122") in body


@RECORDS_URLS
def test_client_id_view_mints_no_token_so_the_hub_crosslink_stays_hidden(client, seeded):
    identity = _identity(seeded, CID)
    _lead(seeded, identity)
    resp = client.get(f"/rr/{CID}")
    assert resp.context["hub_url"] == ""


@RECORDS_URLS
def test_client_id_view_still_offers_the_step_up_login(client, seeded):
    _identity(seeded, CID)
    body = client.get(f"/rr/{CID}").content.decode()
    assert "/login/" in body
    assert "Log in for full details" in body


@RECORDS_URLS
def test_client_id_view_is_read_only(client, seeded):
    _identity(seeded, CID)
    assert client.post(f"/rr/{CID}").status_code == 405


@RECORDS_URLS
def test_client_id_view_emits_a_pii_free_event(client, seeded):
    identity = _identity(seeded, CID)
    _lead(seeded, identity)
    client.get(f"/rr/{CID}")

    event = Event.objects.get(event_type="records_link_viewed")
    assert event.metadata == {"client_id": CID}
    assert not ({k.lower() for k in event.metadata} & PII_KEYS)


@RECORDS_URLS
def test_unknown_client_id_shaped_value_renders_the_unavailable_page_not_a_500(client, seeded):
    """Shaped like a real Zerodha id, but nobody with it has ever clicked/converted —
    no identity exists. Same uniform failure page as a bad token; no oracle."""
    resp = client.get("/rr/ZZ9999")
    assert resp.status_code == 404
    assert "This link has expired" in resp.content.decode()


# --------------------------------------------------------------------- legacy token path


@RECORDS_URLS
def test_legacy_token_value_still_renders_the_masked_view_unchanged(client, seeded):
    identity = _identity(seeded, CID)
    _lead(seeded, identity)
    resp = client.get(f"/rr/{mint_records_token(identity)}")
    assert resp.status_code == 200
    assert mask_name(RAW_NAME) in resp.content.decode()


# --------------------------------------------------------------------- empty value -> recovery


@RECORDS_URLS
def test_rr_with_trailing_slash_and_no_value_renders_the_t122_recovery_page(client, seeded):
    resp = client.get("/rr/")
    assert resp.status_code == 200
    assert "wa.me/" in resp.content.decode()


@RECORDS_URLS
def test_rr_bare_with_no_value_renders_the_t122_recovery_page(client, seeded):
    resp = client.get("/rr")
    assert resp.status_code == 200
    assert "wa.me/" in resp.content.decode()


@RECORDS_URLS
def test_recovery_page_reuses_the_share_recovery_config_keys(client, seeded, settings):
    """DoD: "reusing T-122's template/config keys — extend, never duplicate." Proven
    by asserting the configured button label (not a hardcoded literal) appears."""
    from apps.config import preferences as prefkeys

    body = client.get("/rr/").content.decode()
    assert prefkeys.SHARE_RECOVERY_BUTTON_LABEL_DEFAULT in body


# --------------------------------------------------------------------- garbage -> invalid page


@RECORDS_URLS
@pytest.mark.parametrize("garbage", ["PLAINTESTTOKEN123", "not-a-real-value", "!!bad!!"])
def test_invalid_non_empty_value_renders_the_friendly_invalid_page_not_a_crash(
    client, seeded, garbage,
):
    resp = client.get(f"/rr/{garbage}")
    assert resp.status_code == 404
    body = resp.content.decode()
    assert "This link has expired" in body
    assert "/login/" in body


# --------------------------------------------------------------------- flag


def test_the_client_id_recovery_routes_are_absent_when_the_flag_is_off(client, seeded):
    assert flags.ENABLE_RECORDS_LINK is False
    assert client.get("/rr/").status_code == 404
    assert client.get("/rr").status_code == 404


# --------------------------------------------------------------------- sender-side guard rail


def _records_family_button_value(client_id: str) -> str:
    details = {"name": "Rahul", "record_date": "07 Aug 2026"}
    params = rls._records_params(client_id, details)
    return next(p["value"] for p in params if p["name"] == "token")


def _campaign_family_button_value(client_id: str) -> str:
    details = {"name": "Rahul", "record_date": "07 Aug 2026"}
    params = campaign_send._campaign_params(client_id, details)
    return next(p["value"] for p in params if p["name"] == "token")


@pytest.mark.parametrize(
    "build_value", [_records_family_button_value, _campaign_family_button_value]
)
def test_every_sender_bound_button_value_is_colon_free_and_url_button_safe(build_value):
    """CI-permanent lock (T-129): whatever the RECORDS button substitutes must never
    contain ':' — that single character is what made WhatsApp silently blank the
    whole button value, breaking every `[Referral Records]` tap in prod."""
    value = build_value(CID)
    assert value == CID
    assert ":" not in value
    assert re.fullmatch(SAFE_BUTTON_VALUE_RE, value)


def test_resolve_link_details_hands_senders_a_client_id_rr_url(seeded, monkeypatch):
    monkeypatch.setattr(
        "api.records_tokens.flags", dataclasses.replace(flags, ENABLE_RECORDS_LINK=True)
    )

    identity = _identity(seeded, CID)
    Referral.objects.create(
        tenant=seeded, program=ReferralProgram.objects.get(tenant=seeded),
        referral_identity=identity, source="referral_link",
    )

    details = resolve_link_details(seeded, CID)

    base = settings.PUBLIC_BASE_URL.rstrip("/")
    assert details["rr_url"] == f"{base}/rr/{CID}"
    assert ":" not in details["rr_url"].split("/rr/")[-1]
