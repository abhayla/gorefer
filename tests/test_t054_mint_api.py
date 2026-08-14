"""T-054 — the token-mint API + the logged-in door to the share hub.

Two surfaces, one theme: a signed records/hub token is a BEARER CREDENTIAL, so both
places that hand one out are tested for who may get one, and for whom it names.

What this locks down:

  * **the mint endpoint is shut without a key.** Missing header, wrong key, and — the
    one a config slip would cause — a BLANK `RECORDS_TOKEN_MINT_KEY` all get 401. An
    "open when unset" default would mint a token for any client id to anyone.
  * **no fabricated rows.** An unknown or malformed client id comes back as an error
    item with no token, and minting never lazily creates an identity.
  * **the batch is capped**, so one call cannot be turned into a full-tenant dump.
  * **`/my/referrals` links to the referrer's OWN hub** — the token in the rendered
    href verifies back to the session's identity and to no other, is absent when
    ENABLE_SHARE_HUB is off, and is absent when the account has no identity row.
"""
from __future__ import annotations

import dataclasses
import re

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.accounts import selfview
from apps.accounts.models import ReferrerAccount
from apps.accounts.records_link import verify_records_token
from apps.config.models import ConfigCentral
from apps.config.preferences import RECORDS_MINT_DATE_FORMAT
from apps.referrals.models import Customer, Referral, ReferralIdentity, ReferralProgram
from apps.tenants.models import Tenant

pytestmark = pytest.mark.django_db

CID = "RJ4521"
OTHER_CID = "ZZ9999"
MINT_URL = "/api/records-tokens/mint"
KEY = "t054-test-mint-key"
HEADER = "HTTP_X_RECORDS_MINT_KEY"


@pytest.fixture
def seeded(db):
    call_command("seed_program")
    return Tenant.objects.get(slug="pifs")


@pytest.fixture
def keyed(settings):
    """A configured mint key + the rate limiter left off (CI default)."""
    settings.RECORDS_TOKEN_MINT_KEY = KEY
    return KEY


def _identity(tenant, client_id: str = CID) -> ReferralIdentity:
    program = ReferralProgram.objects.get(tenant=tenant)
    return ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner, client_id=client_id
    )


def _post(client, body: dict, **extra):
    return client.post(MINT_URL, data=body, content_type="application/json", **extra)


def _with_flag(monkeypatch, module: str, **overrides) -> None:
    """Swap a module's frozen flags snapshot (see tests/test_t053_share_hub.py)."""
    from gorefer.flags import flags

    monkeypatch.setattr(f"{module}.flags", dataclasses.replace(flags, **overrides))


# ------------------------------------------------------------------------------ auth


def test_missing_key_header_is_401(client, seeded, keyed):
    resp = _post(client, {"client_ids": [CID]})
    assert resp.status_code == 401


def test_wrong_key_is_401(client, seeded, keyed):
    resp = _post(client, {"client_ids": [CID]}, **{HEADER: "not-the-key"})
    assert resp.status_code == 401


def test_blank_configured_key_refuses_everything(client, seeded, settings):
    """Fail CLOSED. A blank secret must not become "accept anything" — including a
    caller who politely sends an empty header, which `compare_digest("", "")` on an
    unguarded implementation would happily accept."""
    settings.RECORDS_TOKEN_MINT_KEY = ""
    assert _post(client, {"client_ids": [CID]}).status_code == 401
    assert _post(client, {"client_ids": [CID]}, **{HEADER: ""}).status_code == 401
    assert _post(client, {"client_ids": [CID]}, **{HEADER: "anything"}).status_code == 401


def test_auth_runs_before_any_minting(client, seeded, keyed):
    """An unauthenticated call must not create the RecordsLinkState row minting makes —
    proof that auth is checked before the work, not alongside it."""
    from apps.accounts.models import RecordsLinkState

    identity = _identity(seeded)
    _post(client, {"client_ids": [CID]})
    assert not RecordsLinkState.objects.filter(identity=identity).exists()


# ----------------------------------------------------------------------- happy path


def test_mint_returns_everything_a_send_needs(client, seeded, keyed, monkeypatch, settings):
    _with_flag(monkeypatch, "api.records_tokens", ENABLE_RECORDS_LINK=True, ENABLE_SHARE_HUB=True)
    identity = _identity(seeded)
    program = ReferralProgram.objects.get(tenant=seeded)
    Customer.objects.create(
        tenant=seeded, program=program, partner=program.partner,
        client_id=CID, first_name="Ramesh", last_name="Kumar", mobile="9876543210",
    )
    Referral.objects.create(
        tenant=seeded, program=program, referral_identity=identity, source="referral_link"
    )

    resp = _post(client, {"client_ids": [CID]}, **{HEADER: KEY})
    assert resp.status_code == 200
    body = resp.json()
    assert body["minted"] == 1 and body["failed"] == 0

    item = body["items"][0]
    assert item["client_id"] == CID
    assert item["error"] == ""
    assert item["name"] == "Ramesh Kumar"
    assert item["record_date"]
    # The token names THIS identity — the whole point of the endpoint.
    assert verify_records_token(item["token"]) == identity
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    # T-129: the records button carries the raw client_id, not the token — Meta
    # silently blanks a URL-button value containing ':', which every token has.
    assert item["rr_url"] == f"{base}/rr/{CID}"
    assert item["hub_url"] == f"{base}/hub/{item['token']}"


def test_urls_are_blank_when_their_surface_is_not_mounted(client, seeded, keyed, monkeypatch):
    """A template button pointing at an unmounted route is a dead link sitting in
    someone's chat history — the caller gets "" and can skip that send."""
    _with_flag(monkeypatch, "api.records_tokens", ENABLE_RECORDS_LINK=False, ENABLE_SHARE_HUB=False)
    _identity(seeded)
    item = _post(client, {"client_ids": [CID]}, **{HEADER: KEY}).json()["items"][0]
    assert item["token"]
    assert item["rr_url"] == "" and item["hub_url"] == ""


def test_record_date_format_comes_from_config(client, seeded, keyed):
    """rail E-6: the pattern that shapes what the message SAYS is a cascade key."""
    _identity(seeded)
    ConfigCentral.objects.update_or_create(
        key=RECORDS_MINT_DATE_FORMAT, defaults={"value": "%Y-%m-%d"}
    )
    item = _post(client, {"client_ids": [CID]}, **{HEADER: KEY}).json()["items"][0]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["record_date"]), item["record_date"]


def test_a_nonsense_stored_date_format_does_not_break_the_batch(client, seeded, keyed):
    _identity(seeded)
    ConfigCentral.objects.update_or_create(key=RECORDS_MINT_DATE_FORMAT, defaults={"value": ""})
    item = _post(client, {"client_ids": [CID]}, **{HEADER: KEY}).json()["items"][0]
    assert item["record_date"]


def test_unknown_name_is_blank_never_guessed(client, seeded, keyed):
    _identity(seeded)
    item = _post(client, {"client_ids": [CID]}, **{HEADER: KEY}).json()["items"][0]
    assert item["name"] == ""
    assert item["token"]


# -------------------------------------------------------------------- failure items


def test_unknown_client_id_is_an_error_item_not_a_fabricated_row(client, seeded, keyed):
    body = _post(client, {"client_ids": ["NOPE12"]}, **{HEADER: KEY}).json()
    assert body["minted"] == 0 and body["failed"] == 1
    item = body["items"][0]
    assert item["error"] == "unknown_client_id"
    assert item["token"] == "" and item["rr_url"] == "" and item["hub_url"] == ""


def test_minting_never_creates_an_identity(client, seeded, keyed):
    """Identities are created at CLICK time (ADR-008). A typo in a broadcast list must
    not conjure a referrer nobody referred through."""
    _post(client, {"client_ids": ["NOPE12"]}, **{HEADER: KEY})
    assert not ReferralIdentity.objects.filter(client_id="NOPE12").exists()


def test_malformed_client_id_is_rejected_per_item(client, seeded, keyed):
    _identity(seeded)
    body = _post(client, {"client_ids": ["!!! bad", CID]}, **{HEADER: KEY}).json()
    errors = {i["client_id"]: i["error"] for i in body["items"]}
    assert errors["!!! bad"] == "invalid_client_id"
    assert errors[CID] == ""
    assert body["minted"] == 1 and body["failed"] == 1


def test_over_cap_request_is_refused(client, seeded, keyed, settings):
    settings.RECORDS_TOKEN_MINT_MAX_IDS = 3
    resp = _post(client, {"client_ids": [CID] * 4}, **{HEADER: KEY})
    assert resp.status_code == 422
    resp_ok = _post(client, {"client_ids": [CID] * 3}, **{HEADER: KEY})
    assert resp_ok.status_code == 200


def test_empty_list_is_an_empty_batch_not_an_error(client, seeded, keyed):
    body = _post(client, {"client_ids": []}, **{HEADER: KEY}).json()
    assert body == {"minted": 0, "failed": 0, "items": []}


def test_the_endpoint_is_rate_limited(client, seeded, keyed, settings):
    """The limiter is off in CI by default; turned on, an authenticated caller is still
    capped — a credential-issuing endpoint must not be an unbounded oracle."""
    settings.RATELIMIT_ENABLED = True
    settings.RATELIMIT_MINT_MAX = 2
    _identity(seeded)
    codes = [
        _post(client, {"client_ids": [CID]}, **{HEADER: KEY}).status_code for _ in range(4)
    ]
    assert 429 in codes, codes


# ------------------------------------------------------------- /my/referrals hub door


def _account(tenant, client_id: str = CID) -> ReferrerAccount:
    user = get_user_model().objects.create_user(
        username=f"ref-{client_id}", password="x" * 14
    )
    return ReferrerAccount.objects.create(
        tenant=tenant, user=user, client_id=client_id,
        bound_via=ReferrerAccount.BOUND_VIA_OTP,
    )


def test_selfview_hub_link_present_when_the_flag_is_on(seeded, monkeypatch):
    _with_flag(monkeypatch, "apps.accounts.selfview", ENABLE_SHARE_HUB=True)
    identity = _identity(seeded)
    ctx = selfview.my_referrals_ctx(seeded, CID)
    assert ctx["hub_url"].startswith("/hub/")
    # ...and the minted token names the SESSION'S identity, never another.
    assert verify_records_token(ctx["hub_url"].removeprefix("/hub/")) == identity


def test_selfview_hub_link_absent_when_the_flag_is_off(seeded, monkeypatch):
    _with_flag(monkeypatch, "apps.accounts.selfview", ENABLE_SHARE_HUB=False)
    _identity(seeded)
    assert selfview.my_referrals_ctx(seeded, CID)["hub_url"] == ""


def test_selfview_hub_link_absent_when_the_account_owns_no_identity(seeded, monkeypatch):
    """Bound by login, never clicked: there is no identity to mint for, and rendering a
    page must not create one."""
    _with_flag(monkeypatch, "apps.accounts.selfview", ENABLE_SHARE_HUB=True)
    assert selfview.my_referrals_ctx(seeded, CID)["hub_url"] == ""
    assert not ReferralIdentity.objects.filter(client_id=CID).exists()


def test_selfview_never_mints_another_referrers_token(seeded, monkeypatch):
    """The one defect that would matter: two referrers exist, and the page must hand
    the logged-in one a token for THEIR identity."""
    _with_flag(monkeypatch, "apps.accounts.selfview", ENABLE_SHARE_HUB=True)
    mine = _identity(seeded, CID)
    theirs = _identity(seeded, OTHER_CID)

    token = selfview.my_referrals_ctx(seeded, CID)["hub_url"].removeprefix("/hub/")
    resolved = verify_records_token(token)
    assert resolved == mine
    assert resolved != theirs


@pytest.mark.urls("tests.urls_m13")
def test_rendered_page_carries_the_link_only_when_the_flag_is_on(
    client, seeded, monkeypatch, settings
):
    """End-to-end through the real view + template: the href is there with the flag on,
    and there is no dead button with it off (Constitution §4)."""
    settings.RATELIMIT_ENABLED = False
    identity = _identity(seeded)
    account = _account(seeded)

    _with_flag(monkeypatch, "apps.accounts.selfview", ENABLE_SHARE_HUB=True)
    client.force_login(account.user)
    body = client.get("/my/referrals").content.decode()
    hrefs = re.findall(r'id="shareHubLink"[^>]*', body) + re.findall(
        r'href="(/hub/[^"]+)"', body
    )
    assert hrefs, "the share-hub door is missing from the rendered page"
    token = re.search(r'href="/hub/([^"]+)"', body).group(1)
    assert verify_records_token(token) == identity

    _with_flag(monkeypatch, "apps.accounts.selfview", ENABLE_SHARE_HUB=False)
    body_off = client.get("/my/referrals").content.decode()
    assert "/hub/" not in body_off
    assert "shareHubLink" not in body_off
