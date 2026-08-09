"""Records/hub token MINT API (T-054) — `POST /api/records-tokens/mint`.

Who this exists for: the senders that carry a `[Referral Records]` / `[Refer Link]`
URL button are all OUTSIDE this process — the Zoho Deluge fallback sweep, the
Wati-Project broadcast scripts, and the owner's manual Wati broadcast. None of them
can compute a `django.core.signing` token, and every one of them needs the same four
things per recipient: the token, both page URLs, the referrer's name, and the date
their record is stated as of.

Auth is a shared-secret header, not a session: Deluge cannot hold a Django session or
a CSRF token. It follows the idiom the two webhook endpoints already use —
`hmac.compare_digest` against a key that lives ONLY in env, and **fail closed on a
blank key** (an unset secret must refuse everything, never accept anything).

Two things this endpoint deliberately does NOT do:

  * **it never fabricates a row.** An unknown or malformed client id comes back as an
    explicit error item. A caller CSV-ing the response gets a short row count and a
    visible reason, rather than a plausible token for an identity that does not exist;
  * **it makes no vendor call.** The name comes from GoRefer's own `Customer` record
    only. Routing it through `accounts.onfile.resolve_onfile` would fall back to a
    Zoho READ *per id*, so one 100-id call would become 100 sequential HTTP round
    trips and time out under gunicorn. A blank name is honest and the caller (the
    Deluge sweep runs inside Zoho) already has the better source.

`rr_url` / `hub_url` come back BLANK when their flag is off, because a template button
pointing at an unmounted route is a dead link in someone's chat history (Constitution
§4). The caller checks for the empty string before scheduling that send.
"""
from __future__ import annotations

import hmac
import logging

from django.conf import settings
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts.records_link import mint_records_token
from apps.common.ratelimit import RateLimited, check_rate, client_ip
from apps.config.cascade import resolve as resolve_config
from apps.config.preferences import (
    RECORDS_MINT_DATE_FORMAT,
    RECORDS_MINT_DATE_FORMAT_DEFAULT,
)
from apps.referrals.models import Customer, Referral, ReferralIdentity
from apps.referrals.validators import InvalidClientId, validate_client_id
from apps.tenants.resolve import get_current_tenant
from gorefer.flags import flags

logger = logging.getLogger("gorefer.api.records_tokens")

router = Router()

#: The shared-secret header. Named for what it mints, not for a vendor — the same key
#: serves Deluge, the Wati-Project scripts and any future sender.
AUTH_HEADER = "X-Records-Mint-Key"

#: Rate-limit scope. Its own bucket so a busy sweep cannot throttle the public pages.
RATE_SCOPE = "records_token_mint"

#: Per-item failure reasons. Stable strings — a caller branches on these.
ERROR_INVALID = "invalid_client_id"
ERROR_UNKNOWN = "unknown_client_id"


class MintIn(Schema):
    client_ids: list[str] = []


class MintItem(Schema):
    client_id: str
    token: str = ""
    rr_url: str = ""
    hub_url: str = ""
    name: str = ""
    record_date: str = ""
    #: Set ONLY on a failed item; empty on a minted one. Never both.
    error: str = ""


class MintOut(Schema):
    minted: int
    failed: int
    items: list[MintItem]


def _authenticated(request) -> bool:
    """Shared-secret check. Fails CLOSED on an unset key.

    Constant-time compare for the same reason the Zoho webhook uses one: the key is a
    secret, and `!=` leaks it a byte at a time to a caller who can time responses.
    """
    expected = getattr(settings, "RECORDS_TOKEN_MINT_KEY", "") or ""
    if not expected:
        # No key configured => this endpoint accepts NOTHING. An "open when unset"
        # default on a credential-issuing route would hand out tokens for every
        # client id in the tenant to anyone who found the path.
        logger.warning("records-token mint called with no RECORDS_TOKEN_MINT_KEY configured")
        return False
    return hmac.compare_digest(request.headers.get(AUTH_HEADER, "") or "", expected)


def _max_ids() -> int:
    """Cap on one request's list. Bounds both the DB work and the response size."""
    raw = getattr(settings, "RECORDS_TOKEN_MINT_MAX_IDS", 100)
    try:
        cap = int(raw)
    except (TypeError, ValueError):
        return 100
    return cap if cap > 0 else 100


def _base_url() -> str:
    return (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")


def _date_format(tenant_id: int | None) -> str:
    """Cascade-resolved strftime pattern for `record_date` (rail E-6).

    This value shapes what a message SAYS ("as per our records dated …"), so it is a
    config key, not a literal. A stored pattern that strftime rejects falls back to the
    default rather than 500-ing a bulk send.
    """
    raw = resolve_config(
        RECORDS_MINT_DATE_FORMAT, tenant_id=tenant_id, default=RECORDS_MINT_DATE_FORMAT_DEFAULT
    )
    value = str(raw or "").strip()
    return value or RECORDS_MINT_DATE_FORMAT_DEFAULT


def _format_date(moment, fmt: str) -> str:
    """Local (IST — settings.TIME_ZONE) date string, guarded against a bad pattern."""
    if moment is None:
        return ""
    local = timezone.localtime(moment)
    try:
        return local.strftime(fmt)
    except (ValueError, TypeError):
        return local.strftime(RECORDS_MINT_DATE_FORMAT_DEFAULT)


def _record_moment(tenant, identity: ReferralIdentity):
    """The instant `record_date` states the record as of.

    The referrer's MOST RECENT referral record; their identity's own creation when
    they have none yet (a referrer minted from a Zoho-imported conversion, or one who
    has only just been clicked). Never `now()` — the date has to describe the record,
    not the send.
    """
    latest = (
        Referral.objects.for_tenant(tenant)
        .filter(referral_identity=identity, deleted_at__isnull=True)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    return latest or identity.created_at


def _local_name(tenant, client_id: str) -> str:
    """The referrer's name from GoRefer's OWN record, or "". No vendor call (see the
    module docstring) and no guess — a blank name is a caller's cue to use a generic
    greeting, which is safer than a wrong one in a WhatsApp template."""
    customer = (
        Customer.objects.for_tenant(tenant)
        .filter(client_id=client_id, deleted_at__isnull=True)
        .only("first_name", "last_name")
        .first()
    )
    if customer is None:
        return ""
    return f"{customer.first_name} {customer.last_name}".strip()


def resolve_link_details(tenant, client_id: str) -> dict:
    """Public reuse point for the token/name/record_date a records-link send needs
    (T-057). Thin wrapper around `_mint_one` — same shape, same "never fabricate a
    row" guarantee — so a sender never re-implements the mint logic or calls this
    module's own HTTP endpoint from inside the process.
    """
    base = _base_url()
    fmt = _date_format(getattr(tenant, "id", None))
    return _mint_one(tenant, client_id, base=base, fmt=fmt)


def _mint_one(tenant, raw_client_id: str, *, base: str, fmt: str) -> dict:
    """One list entry — either a full minted row or an error row, never a half one."""
    client_id = (raw_client_id or "").strip()
    try:
        client_id = validate_client_id(client_id)
    except InvalidClientId:
        return {"client_id": client_id[:64], "error": ERROR_INVALID}

    identity = (
        ReferralIdentity.objects.for_tenant(tenant)
        .filter(client_id=client_id, status="active", deleted_at__isnull=True)
        .first()
    )
    if identity is None:
        # Lazy creation is a CLICK-time act (ADR-008). Minting a token must not bring
        # a referrer into existence, or a typo in a broadcast list would silently
        # create identities nobody referred through.
        return {"client_id": client_id, "error": ERROR_UNKNOWN}

    token = mint_records_token(identity)
    return {
        "client_id": client_id,
        "token": token,
        # Blank when the surface is not mounted — no dead buttons (Constitution §4).
        "rr_url": f"{base}/rr/{token}" if flags.ENABLE_RECORDS_LINK else "",
        "hub_url": f"{base}/hub/{token}" if flags.ENABLE_SHARE_HUB else "",
        "name": _local_name(tenant, client_id),
        "record_date": _format_date(_record_moment(tenant, identity), fmt),
    }


@router.post("/mint", response=MintOut)
def mint(request, payload: MintIn):
    """Mint records/hub tokens for a batch of client ids. Key-authed, rate-limited."""
    # AUTH FIRST — before the rate limiter and before any DB work, so an unauthenticated
    # caller can neither mint nor consume another caller's quota. Flat 401, no reason:
    # distinguishing "no key" from "wrong key" would be a probing oracle.
    if not _authenticated(request):
        raise HttpError(401, "unauthenticated")

    try:
        check_rate(
            RATE_SCOPE,
            client_ip(request),
            limit=settings.RATELIMIT_MINT_MAX,
            window=settings.RATELIMIT_API_WINDOW,
        )
    except RateLimited as exc:
        raise HttpError(429, f"rate limited; retry after {exc.retry_after}s") from exc

    client_ids = payload.client_ids or []
    cap = _max_ids()
    if len(client_ids) > cap:
        raise HttpError(422, f"at most {cap} client_ids per request")

    tenant = get_current_tenant(request)
    base = _base_url()
    fmt = _date_format(getattr(tenant, "id", None))

    items = [_mint_one(tenant, cid, base=base, fmt=fmt) for cid in client_ids]
    failed = sum(1 for item in items if item.get("error"))
    # Client ids only — never the names or the tokens (the log outlives an erasure
    # request, and a logged token is a live credential).
    logger.info("records-token mint: %s requested, %s failed", len(items), failed)
    return {"minted": len(items) - failed, "failed": failed, "items": items}
