"""WATI assisted-referral webhook endpoint (B4 / ADR-033).

POST /api/wati/webhook — AUTHENTICATE FIRST (static key + IP allowlist), THEN parse
+ validate the body and create ONE Zoho lead from an assisted capture
{client_id (referrer), name, mobile, email?, consent?}.

Security ordering (fixes the independent-verification finding): the shared-secret
check runs BEFORE any schema validation or business logic, so an unauthenticated or
wrong-key request is rejected with 401 regardless of the body — a malformed body can
never surface a 422 to an unauthenticated caller. Auth FAILS CLOSED: if
WATI_WEBHOOK_KEY is not configured, every request is rejected (never skip the check).

401 unauthenticated; 422 on a malformed/forbidden payload (only reachable AFTER
auth passes). Behind ENABLE_ZOHO_WRITE (log-only when off). Never stores a password;
deduped.
"""
from __future__ import annotations

import json

from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import ValidationError

from apps.common.phone import normalize_phone
from apps.followups.advisor_callback import request_and_schedule, send_alert
from apps.followups.models import AdvisorCallbackRequest
from apps.tenants.resolve import get_current_tenant
from gorefer.flags import flags

from .replay import claim_event, event_key
from .webhook import (
    FORBIDDEN_KEYS,
    AssistedCaptureError,
    authenticate,
    process_assisted_capture,
    record_inbound,
)

router = Router()

# T-104 — the three fixed call-back slots a Wati flow's buttons send back verbatim as
# ordinary inbound text (Wati has no HTTP flow node here; see COORDINATION.md 2026-08-12).
# Match EXACTLY these labels, case-insensitively and whitespace-trimmed — a message that
# merely contains one of them ("call me 9-12 please") must NOT trigger.
_CALLBACK_SLOTS = {
    AdvisorCallbackRequest.SLOT_9_12,
    AdvisorCallbackRequest.SLOT_12_3,
    AdvisorCallbackRequest.SLOT_3_6,
}


def _match_callback_slot(text) -> str | None:
    candidate = str(text or "").strip().lower()
    for slot in _CALLBACK_SLOTS:
        if candidate == slot.lower():
            return slot
    return None


class AssistedIn(Schema):
    client_id: str          # the REFERRER's Zerodha client id
    name: str               # prospect name
    mobile: str             # prospect mobile
    email: str | None = ""
    consent: bool | None = True


class AssistedOut(Schema):
    status: str
    lead_id: int
    lead_source: str
    consent: bool


@router.post("/webhook", response=AssistedOut)
def assisted_webhook(request):
    # 1) AUTH FIRST — before any body read / schema validation / business logic.
    #    authenticate() fails CLOSED when WATI_WEBHOOK_KEY is unset (never fail-open).
    #    NB: the view takes NO schema parameter, so Django Ninja does not eagerly
    #    validate the body ahead of this check (that ordering was the reported bug).
    if not authenticate(request):
        raise HttpError(401, "unauthenticated")

    # 2) Only an authenticated caller reaches body parsing.
    try:
        raw = json.loads(request.body or b"{}")
    except (ValueError, TypeError) as exc:
        raise HttpError(422, "malformed JSON body") from exc
    if not isinstance(raw, dict):
        raise HttpError(422, "body must be a JSON object")

    # Defense-in-depth: never accept a credential-shaped field (checked on the raw
    # body because a schema would silently drop unknown keys). Never a password.
    for key in raw:
        if str(key).lower() in FORBIDDEN_KEYS:
            raise HttpError(422, f"forbidden field in assisted capture: {key}")

    # 3) Validate the payload shape (post-auth). Ninja's schema does the coercion.
    try:
        payload = AssistedIn(**raw)
    except (ValidationError, TypeError) as exc:
        raise HttpError(422, "invalid assisted-capture payload") from exc

    # 4) REPLAY GUARD (T-048). The `?token=` credential is static and replayable, so a
    #    captured request stays valid forever; the claim below makes each Wati event
    #    single-use. Runs AFTER validation so a malformed body cannot burn a real key.
    if not claim_event("assisted", event_key("assisted", request.body or b"", raw)):
        raise HttpError(409, "duplicate webhook delivery (replay refused)")

    try:
        result = process_assisted_capture(request, payload.dict())
    except AssistedCaptureError as exc:
        raise HttpError(422, str(exc)) from exc
    return result


@router.post("/inbound")
def inbound_message(request):
    """Wati inbound-message webhook → 24h-window state feed (M-FUP-1).

    AUTH FIRST (same static key + IP allowlist as the assisted webhook, fail-closed).
    Stamps `last_inbound_at` for the CUSTOMER's number and, on a fresh 24h-window open,
    starts the AP's follow-up cadence. OUTBOUND events (owner/fromMe true) are ignored —
    a business-sent message does not open a customer window. Inert until
    `followups_enabled` is on (enqueue is flag-gated), so wiring Wati to this endpoint is
    safe ahead of the flag flip.
    """
    if not authenticate(request):
        raise HttpError(401, "unauthenticated")
    try:
        raw = json.loads(request.body or b"{}")
    except (ValueError, TypeError) as exc:
        raise HttpError(422, "malformed JSON body") from exc
    if not isinstance(raw, dict):
        raise HttpError(422, "body must be a JSON object")

    # OUTBOUND (business → customer) never opens a customer window. Wati marks direction
    # with `owner`/`fromMe` (both mean "sent by us"); treat either truthy as outbound.
    if _as_bool(raw.get("owner")) or _as_bool(raw.get("fromMe")):
        return {"status": "ignored", "reason": "outbound"}

    mobile = raw.get("waId") or raw.get("phone") or raw.get("mobile") or raw.get("senderId") or ""
    if not str(mobile).strip():
        return {"status": "ignored", "reason": "no mobile"}

    # REPLAY GUARD (T-048). This endpoint opens the 24h session window and, on a fresh
    # open, enqueues the whole nudge cadence — so a replayed capture is a message-spam
    # primitive. Claimed AFTER the outbound/no-mobile early returns (those change no
    # state, so they must not burn a key) and BEFORE any write.
    #
    # A duplicate answers 200 with a no-op rather than an error: Wati's native sender
    # RETRIES on a non-2xx, and a retry of a message we already recorded is benign — the
    # requirement is that it changes nothing, not that it fails loudly.
    if not claim_event("inbound", event_key("inbound", request.body or b"", raw)):
        return {"status": "ignored", "reason": "duplicate", "stamped": False, "enqueued": 0}

    tenant = get_current_tenant(request)

    # T-104 — advisor-callback slot tap (owner-approved Option B, 2026-08-12): an inbound
    # whose trimmed text EXACTLY matches one of the three slot labels a Wati flow's
    # buttons send back reuses the EXISTING advisor-callback service — the same
    # create-request + immediate-alert path POST /api/callback-request/ calls. Gated on
    # ENABLE_ADVISOR_CALLBACK; additive only — every existing behaviour below (window
    # stamp + cadence enqueue) still runs unchanged for every inbound, matched or not.
    if flags.ENABLE_ADVISOR_CALLBACK:
        slot = _match_callback_slot(raw.get("text"))
        if slot is not None:
            canonical = normalize_phone(str(mobile))
            if canonical:
                name = str(raw.get("senderName") or raw.get("name") or "").strip()[:80]
                req, created = request_and_schedule(tenant, mobile=canonical, name=name, slot=slot)
                if created:
                    send_alert(tenant, req)

    result = record_inbound(
        tenant, str(mobile), _parse_ts(raw.get("timestamp")), text=raw.get("text")
    )
    return {"status": "ok", **result}


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _parse_ts(value):
    """Parse a Wati inbound timestamp (epoch seconds, str or int) → aware datetime.

    Returns None (→ 'now' downstream) on anything unparseable — a missing/garbled
    timestamp must never crash the window feed.
    """
    if value in (None, ""):
        return None
    try:
        from datetime import datetime
        from datetime import timezone as _tz

        return datetime.fromtimestamp(int(value), tz=_tz.utc)
    except (ValueError, TypeError, OSError):
        return None
