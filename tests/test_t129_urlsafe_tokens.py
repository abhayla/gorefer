"""T-129 — URL-button-safe magic-link tokens.

Root cause (proven live 2026-08-14 by a controlled tap A/B, nginx by_host log):
WhatsApp/Meta silently substitutes EMPTY for a URL-button variable value that
contains ':'. Django's `signing.dumps()` output is `payload:timestamp:signature`,
so every records/hub link button suffix arrived blank — every recipient tap on
`gorefer.in/rr/{token}` hit the bare route instead.

Fix: encode the signed token's ':' separators as '.' at mint (the transport form);
decode accepts BOTH the new dot-form and the legacy colon-form, so any link already
sent before this fix keeps working. This file locks the encoding down + proves the
bare `/rr/` and `/rr` routes recover instead of 404ing, mirroring the T-122 pattern.
"""
from __future__ import annotations

import dataclasses
import re

import pytest
from django.core import signing
from django.core.management import call_command

from api.records_tokens import resolve_link_details
from apps.accounts.records_link import (
    TOKEN_SALT,
    mint_records_token,
    verify_records_token,
)
from apps.campaigns.send import _campaign_params
from apps.referrals.models import ReferralIdentity, ReferralProgram
from apps.tenants.models import Tenant


def _with_flag(monkeypatch, module: str, **overrides) -> None:
    """Rebuild that module's frozen flags snapshot with overrides (mirrors
    test_t054_mint_api._with_flag — `flags` is bound per-module at import time)."""
    from gorefer.flags import flags

    monkeypatch.setattr(f"{module}.flags", dataclasses.replace(flags, **overrides))

CID = "RJ4521"
INVALID_TOKEN = "PLAINTESTTOKEN123"
HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.7"}

pytestmark = pytest.mark.django_db

RECORDS_URLS = pytest.mark.urls("tests.urls_records_link")

#: URL-button-safe charset a button suffix may carry (rail asserted by the DoD).
TOKEN_CHARSET_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


def _identity(tenant, client_id: str) -> ReferralIdentity:
    program = ReferralProgram.objects.get(tenant=tenant)
    return ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner, client_id=client_id
    )


# ------------------------------------------------------------- separator safety


def test_dot_never_appears_in_a_raw_signed_token(seeded):
    """The premise the '.' <-> ':' swap relies on: a raw `signing.dumps()` token,
    BEFORE any T-129 transform, never itself contains a literal '.' — payload and
    signature are unpadded urlsafe-base64 ([A-Za-z0-9_-]) and the timestamp is
    base62 ([A-Za-z0-9]). If this ever failed, the dot-swap would be ambiguous."""
    for _ in range(20):
        raw = signing.dumps({"t": seeded.id, "i": 1, "e": 1}, salt=TOKEN_SALT)
        assert "." not in raw
        assert raw.count(":") == 2


def test_minted_token_has_no_colon_and_matches_the_button_safe_charset(seeded):
    identity = _identity(seeded, CID)
    token = mint_records_token(identity)
    assert ":" not in token
    assert TOKEN_CHARSET_RE.match(token), token


def test_resolve_link_details_token_and_urls_are_colon_free(seeded, monkeypatch):
    _with_flag(monkeypatch, "api.records_tokens", ENABLE_RECORDS_LINK=True, ENABLE_SHARE_HUB=True)
    _identity(seeded, CID)
    details = resolve_link_details(seeded, CID)
    assert details["token"]
    assert TOKEN_CHARSET_RE.match(details["token"])
    # The scheme's own "https://" colon is not the button-suffix value — only what
    # follows it (and in particular the token) is what a URL-button variable carries.
    assert ":" not in details["rr_url"].split("//", 1)[-1]
    assert ":" not in details["hub_url"].split("//", 1)[-1]


def test_campaign_send_token_param_is_colon_free(seeded, monkeypatch):
    _with_flag(monkeypatch, "api.records_tokens", ENABLE_RECORDS_LINK=True)
    _identity(seeded, CID)
    details = resolve_link_details(seeded, CID)
    params = _campaign_params(CID, details)
    token_param = next(p for p in params if p["name"] == "token")
    assert token_param["value"]
    assert ":" not in token_param["value"]


# ------------------------------------------------------------- decode compat


def test_new_dot_form_token_round_trips(seeded):
    identity = _identity(seeded, CID)
    token = mint_records_token(identity)
    assert "." in token  # sanity: this test is exercising the new transport form
    assert verify_records_token(token).pk == identity.pk


def test_legacy_colon_form_token_still_verifies(seeded):
    """A link minted and sent BEFORE this fix carries the raw colon form. Decode must
    keep accepting it — an already-delivered link must not go dead on deploy."""
    identity = _identity(seeded, CID)
    # Mint through the real path: minting is what creates the `RecordsLinkState`
    # revocation row, and verification fails CLOSED without one (T-052 —
    # `test_t051_records_link.py::test_a_missing_state_row_fails_closed`). Hand-rolling
    # the payload with `signing.dumps()` would build a token that could never have been
    # sent in the first place, which is not the pre-fix link this test is about.
    legacy_raw = mint_records_token(identity).replace(".", ":")
    assert ":" in legacy_raw
    assert verify_records_token(legacy_raw).pk == identity.pk


def test_invalid_plain_token_is_rejected_not_crashed(seeded):
    _identity(seeded, CID)  # a realistic tenant, though the token names nobody
    assert verify_records_token(INVALID_TOKEN) is None


@RECORDS_URLS
def test_invalid_plain_token_on_rr_renders_the_friendly_invalid_page_not_a_crash(client, seeded):
    resp = client.get(f"/rr/{INVALID_TOKEN}", **HUMAN)
    assert resp.status_code == 404
    assert "This link has expired" in resp.content.decode()


# ------------------------------------------------------------- bare /rr/ recovery


@RECORDS_URLS
def test_bare_rr_with_trailing_slash_returns_200(seeded, client):
    resp = client.get("/rr/", **HUMAN)
    assert resp.status_code == 200
    assert "wa.me/" in resp.content.decode()


@RECORDS_URLS
def test_bare_rr_without_trailing_slash_returns_200(seeded, client):
    resp = client.get("/rr", **HUMAN)
    assert resp.status_code == 200


@RECORDS_URLS
def test_bare_rr_renders_compliance_disclosure(seeded, client):
    body = client.get("/rr/", **HUMAN).content.decode()
    assert "AP2516003693" in body  # NSE AP reg. no., part of the disclosure block


def test_bare_rr_routes_are_absent_when_the_flag_is_off(client, seeded):
    """ENABLE_RECORDS_LINK defaults off, so the prod urlconf must not mount /rr/ or
    /rr at all — no dead route (Constitution §4), matching /rr/<token>'s own gate."""
    from gorefer.flags import flags

    assert flags.ENABLE_RECORDS_LINK is False
    assert client.get("/rr/", **HUMAN).status_code == 404
    assert client.get("/rr", **HUMAN).status_code == 404
