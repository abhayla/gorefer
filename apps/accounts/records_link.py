"""Signed, revocable "Referral Records" magic-link tokens (T-051).

WhatsApp templates carry a [Referral Records] URL button whose per-recipient suffix is
one of these tokens. Tapping it opens `/rr/{token}` — a READ-ONLY, MASKED view of that
referrer's own records, with no login wall, because a login wall in the middle of a
WhatsApp tap is where referrers drop off.

Design (owner-locked 2026-08-07):

  * **Token = `django.core.signing`.** Stateless and tamper-proof, no new dependency,
    and — the reason a hashed-random-token design was rejected — the send-time path can
    RE-DERIVE an embeddable token for any referrer without a lookup table.
  * **Revocation = an epoch integer** on `accounts.RecordsLinkState`, keyed to the
    `referrals.ReferralIdentity`. A token carries the epoch it was minted under;
    `rotate_records_token()` bumps it, which kills every link previously sent to that
    ONE referrer and leaves everybody else's working.
  * **TTL is config, not a literal** — `records_link_ttl_days` resolves through the
    ADR-022 cascade at VERIFY time (rail E-6), so shortening the window takes effect on
    already-sent links immediately, with no deploy and no re-send.

Failure is deliberately uniform: expired, rotated, tampered and never-existed all
return `None`, and the view renders one identical page for all four. A caller that
could tell them apart would be an oracle for probing which client ids exist.
"""
from __future__ import annotations

from django.core import signing
from django.utils import timezone

from apps.config.cascade import resolve as resolve_config
from apps.config.preferences import RECORDS_LINK_TTL_DAYS, RECORDS_LINK_TTL_DAYS_DEFAULT
from apps.referrals.models import ReferralIdentity

from .models import RecordsLinkState

#: Namespaces the signature. Changing it invalidates every token ever minted — which is
#: the intended escape hatch if the payload shape ever has to change incompatibly.
TOKEN_SALT = "gorefer.records-link.v1"

SECONDS_PER_DAY = 86400

#: T-129 root cause: WhatsApp/Meta silently substitutes EMPTY for a URL-button
#: variable value containing ':'. Django's `signing.dumps()` output is
#: `payload:timestamp:signature`, so every records/hub link's button suffix arrived
#: blank in the wild (proven 2026-08-14 by a controlled tap A/B, nginx by_host log).
#: '.' never appears in a raw signed token — the payload/signature are urlsafe base64
#: (`[A-Za-z0-9_-]`, no padding) and the timestamp is base62 (`[A-Za-z0-9]`) — so it is
#: an unambiguous, reversible stand-in for ':' (see `test_dot_never_appears_in_a_raw_signed_token`).
_TRANSPORT_SEP = "."
_SIGNING_SEP = ":"


def _to_transport(raw_token: str) -> str:
    """Colon-free, URL-button-safe form of a freshly `signing.dumps()`-minted token."""
    return raw_token.replace(_SIGNING_SEP, _TRANSPORT_SEP)


def _from_transport(token: str) -> str:
    """Reverse of `_to_transport`. A token that still carries a literal ':' is a
    legacy (pre-T-129) link — passed through unchanged so it keeps opening."""
    if _SIGNING_SEP in token:
        return token
    return token.replace(_TRANSPORT_SEP, _SIGNING_SEP)

# Payload keys kept to one letter: the token rides inside a WhatsApp URL-button suffix,
# where every character counts against the button's length budget.
_KEY_TENANT = "t"
_KEY_IDENTITY = "i"
_KEY_EPOCH = "e"


def _state_for(identity: ReferralIdentity) -> RecordsLinkState:
    """The referrer's revocation row, created on first use at epoch 1."""
    state, _ = RecordsLinkState.objects.get_or_create(
        identity=identity, defaults={"tenant_id": identity.tenant_id}
    )
    return state


def ttl_days(tenant_id: int | None) -> int:
    """Cascade-resolved link lifetime in days (rail E-6). Falls back to the default on
    a missing or nonsensical stored value — a zero/negative TTL would silently make
    every link dead-on-arrival, which is worse than the default being slightly long."""
    raw = resolve_config(
        RECORDS_LINK_TTL_DAYS, tenant_id=tenant_id, default=RECORDS_LINK_TTL_DAYS_DEFAULT
    )
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return RECORDS_LINK_TTL_DAYS_DEFAULT
    return days if days > 0 else RECORDS_LINK_TTL_DAYS_DEFAULT


def mint_records_token(referrer: ReferralIdentity) -> str:
    """Mint a URL-safe records token for `referrer` (a `ReferralIdentity`).

    Idempotent in effect: minting twice under the same epoch yields two different
    strings (the signature is timestamped) that are equally valid — there is no
    "current token" to invalidate by re-minting. Only `rotate_records_token()` revokes.
    """
    state = _state_for(referrer)
    raw = signing.dumps(
        {
            _KEY_TENANT: referrer.tenant_id,
            _KEY_IDENTITY: referrer.pk,
            _KEY_EPOCH: state.epoch,
        },
        salt=TOKEN_SALT,
    )
    return _to_transport(raw)


def rotate_records_token(referrer: ReferralIdentity) -> int:
    """Revoke every token previously minted for `referrer`. Returns the new epoch."""
    state = _state_for(referrer)
    state.epoch += 1
    state.rotated_at = timezone.now()
    state.save(update_fields=["epoch", "rotated_at", "updated_at"])
    return state.epoch


def verify_records_token(token: str | None) -> ReferralIdentity | None:
    """Return the `ReferralIdentity` a valid token names, else `None`.

    `None` covers, indistinguishably: a bad/absent/tampered token, one older than the
    configured TTL, one minted under a superseded epoch, and one naming an identity
    that no longer exists or is disabled.
    """
    if not token:
        return None
    signed = _from_transport(token)
    try:
        payload = signing.loads(signed, salt=TOKEN_SALT)
    except signing.BadSignature:
        return None
    if not isinstance(payload, dict):
        return None

    tenant_id = payload.get(_KEY_TENANT)
    identity_id = payload.get(_KEY_IDENTITY)
    epoch = payload.get(_KEY_EPOCH)
    if identity_id is None or epoch is None:
        return None

    # Age is checked SECOND, against the tenant's own configured window — which is why
    # the payload has to be read (signature-verified) before the TTL is known. The
    # first loads() above already proved the payload is authentic; this second one only
    # adds the max_age assertion. SignatureExpired subclasses BadSignature.
    try:
        signing.loads(
            signed, salt=TOKEN_SALT, max_age=ttl_days(tenant_id) * SECONDS_PER_DAY
        )
    except signing.BadSignature:
        return None

    identity = (
        ReferralIdentity.objects.for_tenant(tenant_id)
        .filter(pk=identity_id, status="active", deleted_at__isnull=True)
        .first()
    )
    if identity is None:
        return None

    # Resolved THROUGH the identity (a OneToOne), never by re-filtering on the tenant
    # carried in the payload: the identity lookup above already pinned the ADR-023
    # scope, and a second tenant filter here could only ever MISS — which is exactly
    # what a divergent `RecordsLinkState.tenant` (e.g. a row minted before the tenant
    # backfill) would cause. When it missed, the old code fell back to epoch 1, so
    # rotation INVERTED: pre-rotation links kept working and the new one was refused.
    # Missing state now fails CLOSED — minting always creates the row, so a token that
    # has no row is a token we cannot vouch for.
    state = RecordsLinkState.objects.filter(identity=identity).first()
    if state is None or int(epoch) != int(state.epoch):
        return None
    return identity
