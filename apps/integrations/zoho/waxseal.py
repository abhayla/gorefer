"""DF-2 — the HMAC "wax-seal" on the Zoho status webhook.

Why this matters more than a normal auth upgrade: this webhook is the SOLE writer of
conversion / `credited_referrer` (guardrail #2). A leaked static key therefore buys an
attacker the ability to FABRICATE conversions — i.e. to credit an arbitrary referrer
for an account that never opened. DF-2 was originally a P0 for exactly that reason,
and it must be closed before any real referrer-reward payout trusts the webhook.

What the seal adds over the static key (all four are required together):

  signature = HMAC-SHA256(secret, f"{timestamp}.{nonce}.{raw_body}")

1. **HMAC over the RAW BODY** — proves the sender holds the secret AND that not one
   byte of the payload was altered in flight. The static key proved neither: anyone
   who saw the key could send any body they liked.
2. **Timestamp + freshness window** — a captured request goes stale, so a recording
   of yesterday's "account opened" cannot be re-fired forever.
3. **One-time nonce** — closes the window the timestamp leaves open: inside the
   freshness window a byte-identical replay would otherwise still verify. The nonce
   makes each sealed request usable exactly once.
4. **Zoho server-IP allowlist** — retained from the interim (cheap hygiene).

The signature MUST be computed over the raw request bytes, never over a re-serialized
dict: `json.dumps(json.loads(body))` can reorder keys or renormalize spacing, so a
re-serialized payload would fail to verify (or, worse, verify a payload that differs
from what was actually signed).

FAIL-CLOSED everywhere: an unset secret REJECTS. A webhook that authenticates
everything when misconfigured is worse than one that is simply off.

Flag: `ENABLE_ZOHO_WEBHOOK_HMAC` (default OFF) so the seal can be built + tested and
the Zoho-side Deluge signer rolled out without breaking the live static-key webhook
mid-flight. With it off, the interim static-key + IP-allowlist path is unchanged.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time

from django.conf import settings

logger = logging.getLogger("gorefer.zoho.waxseal")

# Header names the Zoho-side Deluge signer must send.
SIG_HEADER = "X-Zoho-Signature"
TS_HEADER = "X-Zoho-Timestamp"
NONCE_HEADER = "X-Zoho-Nonce"

# How old a sealed request may be. 300s absorbs real clock skew between Zoho's
# servers and ours while keeping the replay window small. Paired with the nonce, a
# replay inside this window is still rejected — the window only bounds how long a
# captured request is even worth trying.
DEFAULT_MAX_SKEW_SECONDS = 300

# Bound the stored nonce: a nonce only needs to outlive the freshness window, since
# anything older is already rejected on timestamp alone. Without a bound the table
# would grow forever.
NONCE_RETENTION_SECONDS = DEFAULT_MAX_SKEW_SECONDS * 4


def _max_skew() -> int:
    return int(getattr(settings, "ZOHO_WEBHOOK_MAX_SKEW_SECONDS", DEFAULT_MAX_SKEW_SECONDS))


# A plain epoch-SECONDS value is ~1.0e9–2.0e9 (10 digits) through year 2033; a
# millisecond value is ~1.0e12–2.0e12 (13 digits). Anything at/above this threshold is
# treated as milliseconds and divided down. The gap between the two ranges is enormous,
# so there is no realistic ambiguity for any near-current timestamp.
_MILLIS_THRESHOLD = 10_000_000_000  # 1e10: above => milliseconds, below => seconds


def _normalize_epoch_seconds(timestamp: str) -> int | None:
    """Parse an epoch timestamp string as SECONDS, auto-scaling from milliseconds.

    Returns integer epoch seconds, or None if the value isn't a number. Accepting both
    units lets the Deluge signer (which emits milliseconds via unixEpoch) and a
    seconds-based caller share one verifier without a format handshake.
    """
    try:
        value = int(float(timestamp))
    except (TypeError, ValueError):
        return None
    if abs(value) >= _MILLIS_THRESHOLD:
        return value // 1000
    return value


def compute_signature(*, secret: str, timestamp: str, nonce: str, raw_body: bytes) -> str:
    """The canonical seal: HMAC-SHA256 over `timestamp.nonce.raw_body`.

    Binding the timestamp and nonce INTO the signed material (rather than sending them
    alongside it) is what stops an attacker from keeping a valid signature and swapping
    in a fresh timestamp/nonce to bypass the freshness and replay checks.
    """
    mac = hmac.new(secret.encode("utf-8"), digestmod=hashlib.sha256)
    mac.update(timestamp.encode("utf-8"))
    mac.update(b".")
    mac.update(nonce.encode("utf-8"))
    mac.update(b".")
    mac.update(raw_body)
    return mac.hexdigest()


class SealRejected(Exception):
    """The seal failed. `reason` is for OUR logs — never echo it to the caller.

    Telling an unauthenticated caller *why* it failed (bad signature vs stale vs
    replayed) hands them an oracle for probing the scheme. The endpoint answers a
    flat 401.
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def verify_seal(request, raw_body: bytes) -> None:
    """Verify the wax-seal, or raise SealRejected. Returns None on success.

    Order is deliberate: cheap local checks (secret present, headers present, freshness)
    run before the signature computation, and the nonce burn — the only write — happens
    LAST, so an unsigned flood cannot fill the nonce table.
    """
    secret = getattr(settings, "ZOHO_WEBHOOK_HMAC_SECRET", "")
    if not secret:
        # Fail CLOSED. With the flag on and no secret, reject everything rather than
        # silently degrade to "any caller welcome".
        raise SealRejected("ZOHO_WEBHOOK_HMAC_SECRET unset (fail-closed)")

    signature = request.headers.get(SIG_HEADER, "")
    timestamp = request.headers.get(TS_HEADER, "")
    nonce = request.headers.get(NONCE_HEADER, "")
    if not (signature and timestamp and nonce):
        raise SealRejected("missing signature/timestamp/nonce header")

    # --- freshness -------------------------------------------------------------
    # Accept the timestamp in epoch SECONDS or epoch MILLISECONDS. Deluge's native
    # unit is milliseconds (`unixEpoch()` returns ms, and there is no `toEpoch()`),
    # so the Zoho signer sends ms; other callers (and the tests) may send seconds.
    # We normalize by magnitude — a ms epoch is ~1000x a seconds epoch (13 vs 10
    # digits) — so the freshness/skew check stays meaningful either way. The SIGNATURE
    # is still computed over the exact `timestamp` STRING that was sent, so this
    # tolerance never weakens the seal: it only interprets the freshness value.
    sent_at = _normalize_epoch_seconds(timestamp)
    if sent_at is None:
        raise SealRejected("timestamp not an epoch integer")

    skew = abs(int(time.time()) - sent_at)
    if skew > _max_skew():
        # abs() rejects far-FUTURE timestamps too: a forged one would otherwise stay
        # "fresh" indefinitely and defeat the whole freshness check.
        raise SealRejected(f"stale or future timestamp (skew {skew}s > {_max_skew()}s)")

    # --- signature -------------------------------------------------------------
    expected = compute_signature(
        secret=secret, timestamp=timestamp, nonce=nonce, raw_body=raw_body
    )
    if not hmac.compare_digest(signature, expected):
        # Constant-time: a byte-by-byte comparison leaks, via timing, how much of a
        # guessed signature was correct — enough to forge one byte at a time.
        raise SealRejected("signature mismatch")

    # --- replay (nonce burn — the only write, deliberately last) ----------------
    _burn_nonce(nonce)


def _burn_nonce(nonce: str) -> None:
    """Consume a one-time nonce. A second use of the same nonce is a replay.

    Relies on the DB unique constraint rather than a check-then-insert: two concurrent
    replays could both pass an existence check and both proceed. Letting the database
    arbitrate makes exactly one win.

    The insert is wrapped in its OWN atomic block. Without it, the IntegrityError on a
    replay marks the surrounding transaction broken, and every later query on that
    connection raises TransactionManagementError — so a rejected replay would poison
    the request instead of returning a clean 401.
    """
    from django.db import IntegrityError, transaction

    from apps.integrations.models import ZohoWebhookNonce

    try:
        with transaction.atomic():
            ZohoWebhookNonce.objects.create(nonce=nonce)
    except IntegrityError as exc:
        raise SealRejected("nonce already used (replay)") from exc


def purge_expired_nonces() -> int:
    """Delete nonces older than the retention window. Returns how many were removed.

    Safe because anything that old already fails the freshness check on its timestamp,
    so forgetting it cannot enable a replay. Scheduled next to the other sweeps.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.integrations.models import ZohoWebhookNonce

    cutoff = timezone.now() - timedelta(seconds=NONCE_RETENTION_SECONDS)
    deleted, _ = ZohoWebhookNonce.objects.filter(created_at__lt=cutoff).delete()
    if deleted:
        logger.info("Purged %d expired Zoho webhook nonce(s)", deleted)
    return deleted
