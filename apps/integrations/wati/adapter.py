"""WATI adapter behind the doc-08 contract (M5).

Two responsibilities:
  - send_template(): submit an approved template to a recipient. Returns an
    ACCEPTED acknowledgement (HTTP-200-equivalent) — NEVER treated as delivery.
    Wati's sendTemplateMessage ack is `{"result": true}` with **no message id**
    (proven live on the Zoho-queue side, 2026-07-16), so there is nothing to key a
    webhook on; we record `accepted` and never fabricate a message id.
  - get_message_status(): fetch the TERMINAL delivery status (delivered/read/failed)
    + any Meta error code. This is the ONLY proof of delivery (doc-08 A3). Because
    the ack carries no id, terminal status is reconciled from getMessages/{mobile}
    (keyed by mobile, matched on template) — not by a message id.

ENABLE_WATI_SEND gates real sending:
  - false (default, dev/CI/demo): LogOnlyWatiAdapter logs the intended call + payload
    and simulates a delivered terminal status, so the whole flow is testable offline.
  - true: LiveWatiAdapter reads WATI_* config from env/secret store (never inline)
    and calls the real Wati API.

Secrets (WATI bearer JWT etc.) come from env/secret store — never inline (A7).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from . import status

logger = logging.getLogger("gorefer.wati")

HTTP_TIMEOUT_SECONDS = 15


@dataclass
class SendResult:
    accepted: bool
    provider_message_id: str | None
    raw_status: str  # 'accepted' on submit — NOT delivery


@dataclass
class DeliveryResult:
    status: str                 # terminal status: delivered/read/failed (or 'accepted' if unknown)
    meta_error_code: int | None
    classification: str | None


class LogOnlyWatiAdapter:
    """Demo/dev adapter: logs the intended send, simulates a delivered terminal status.

    Performs NO network call. The notification service still verifies the terminal
    status via get_message_status — proving the "assert on terminal status, not
    HTTP 200" discipline works end-to-end offline.
    """

    kind = "log_only"

    def send_template(self, *, to: str, template: str, params: dict) -> SendResult:
        # REDACT values (Fable5 M5): with OTP on + WATI off this log-only path handles
        # OTP sends, and params carries the plaintext code under template_params. Log
        # only the variable NAMES/positions + count, never the values — the OTP module's
        # "the code is never logged" invariant must hold for the log-only adapter too.
        logger.info(
            "[demo] WATI send suppressed: to=%s template=%s param_names=%s",
            to, template, _redact_param_names(params),
        )
        return SendResult(
            accepted=True,
            provider_message_id=f"demo-{template}-{to}",
            raw_status=status.STATUS_ACCEPTED,
        )

    def send_session_text(self, *, to: str, message: str) -> SendResult:
        # Demo/dev: log the intended free-form session send WITHOUT the body (a follow-up
        # body is config copy, but log length only to keep the same "never print message
        # content" discipline the template path uses for OTP/PII). No network call.
        logger.info("[demo] WATI session-text suppressed: to=%s len=%s", to, len(message or ""))
        return SendResult(
            accepted=True,
            provider_message_id=f"demo-session-{to}",
            raw_status=status.STATUS_ACCEPTED,
        )

    def get_message_status(self, *, provider_message_id: str, recipient_mobile: str | None = None,
                           template: str | None = None) -> DeliveryResult:
        # Demo made NO network call, so this is a SIMULATED terminal status, reported as
        # such (Fable5 M7) — never as a real 'delivered'. Delivery metrics exclude it,
        # so a demo/degraded send can't be mistaken for a real delivery.
        return DeliveryResult(
            status=status.STATUS_SIMULATED_DELIVERED, meta_error_code=None, classification=None
        )

    def get_latest_inbound_at(self, mobile: str):
        # Demo/dev: no real inbound to read (no network) — the poll finds nothing to do.
        return None


class LiveWatiAdapter:
    """Real WATI adapter. Reads secrets from env/secret store (never inline).

    Config (env only):
      - WATI_API_ENDPOINT: tenant base URL, e.g. https://live-mt-server.wati.io/<tenantId>
        (tenant is IN THE PATH; there is no separate tenant query param). Trailing
        slash trimmed. WATI_BASE_URL is accepted as a legacy alias.
      - WATI_API_TOKEN: access token. A leading "Bearer " is stripped — we add the
        scheme ourselves.

    Refuses to construct without a base + token so a flag flip against missing config
    fails LOUDLY here instead of silently degrading to a no-op.
    """

    kind = "live"

    def __init__(self, *, transport=None):
        base = os.environ.get("WATI_API_ENDPOINT") or os.environ.get("WATI_BASE_URL") or ""
        self.base_url = base.rstrip("/")
        # Strip a leading "Bearer " if the stored token already carries the scheme.
        raw_token = os.environ.get("WATI_API_TOKEN", "")
        self.token = raw_token[len("Bearer "):] if raw_token.startswith("Bearer ") else raw_token
        if not (self.base_url and self.token):
            raise RuntimeError(
                "WATI_API_ENDPOINT / WATI_API_TOKEN not configured — cannot send live."
            )
        # Injectable transport for tests (default = real HTTP). A transport is a
        # callable(method, url, headers, body_bytes) -> (status_code, text).
        self._transport = transport or self._http

    # --- HTTP -------------------------------------------------------------------

    def _http(self, method: str, url: str, headers: dict, body: bytes | None):
        # A real User-Agent is REQUIRED: Wati sits behind Cloudflare, which 403s the
        # default `Python-urllib/x.y` UA as a bot signature. curl (UA `curl/x`) passes,
        # which is why manual curl sends worked while the adapter's urllib send got 403.
        headers = {**headers, "User-Agent": "GoRefer/1.0 (+https://gorefer.in)"}
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                return resp.getcode(), resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")
        except (urllib.error.URLError, OSError) as exc:
            # Connection refused / DNS / timeout — a transport failure, not a crash.
            # Return a synthetic 5xx so the caller records FAILED (never delivered).
            logger.warning("WATI transport error: %s", exc.__class__.__name__)
            return 599, ""

    def _auth_headers(self, *, json_body: bool) -> dict:
        h = {"Authorization": f"Bearer {self.token}"}
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    # --- Contract ---------------------------------------------------------------

    def send_template(self, *, to: str, template: str, params: dict) -> SendResult:
        """POST sendTemplateMessage. Returns ACCEPTED — never delivery.

        `params` is the notification's context dict (e.g. {"role": ...}); Wati wants
        an ordered list of {"name","value"} positional/named template variables. The
        three Sprint-1 templates carry no positional variables, so we send an empty
        list unless the caller supplied concrete template variables under
        params["template_params"] (a list of {name,value}) — future-proofing without
        guessing a mapping we don't have.
        """
        number = "".join(ch for ch in str(to) if ch.isdigit())

        # FAIL-CLOSED recipient allowlist. Unless WATI_ALLOW_ALL_RECIPIENTS is
        # explicitly "true", a send is REFUSED for any number not in
        # WATI_TEST_RECIPIENTS — no network call is made. This is the same rail the
        # test-send skill enforces, now enforced inside GoRefer's own send path so a
        # capture during testing can never fire a real message to a non-test number
        # (e.g. the office/Ashok alert). A blocked send is recorded, not sent.
        if not _recipient_allowed(number):
            logger.warning("WATI send BLOCKED by allowlist: template=%s (recipient not allowlisted)",
                           template)
            return SendResult(accepted=False, provider_message_id=None, raw_status=status.STATUS_BLOCKED)

        tvars = params.get("template_params") if isinstance(params, dict) else None
        if not isinstance(tvars, list):
            tvars = []
        # Wati matches template variables POSITIONALLY: its customParams are named
        # "1","2","3" (the {{1}}/{{2}} placeholders). Our callers pass SEMANTIC names
        # (prospect_name, office_number, …) so the code stays order-independent — but at
        # the Wati boundary they MUST be remapped to positional "1","2",… by their order,
        # or Wati can't fill the template and rejects the send as "blank text" (HTTP 400).
        wati_params = [
            {"name": str(i), "value": (p.get("value") if isinstance(p, dict) else "")}
            for i, p in enumerate(tvars, start=1)
        ]
        url = (
            f"{self.base_url}/api/v1/sendTemplateMessage"
            f"?whatsappNumber={urllib.parse.quote(number)}"
        )
        body = json.dumps({
            "template_name": template,
            "broadcast_name": template,
            "parameters": wati_params,
        }).encode("utf-8")

        code, text = self._transport("POST", url, self._auth_headers(json_body=True), body)
        ok = False
        if 200 <= code < 300:
            try:
                ok = bool(json.loads(text or "{}").get("result", False))
            except (ValueError, AttributeError):
                ok = False
        if not ok:
            # Do NOT raise — a failed send is a recorded FAILED notification, not a
            # crash that strands the lead. Log without the token or body.
            logger.warning("WATI send not accepted: template=%s http=%s", template, code)
        else:
            logger.info("WATI send accepted: template=%s http=%s", template, code)
        # The ack has NO message id — we deliberately return None, not a fabricated id.
        return SendResult(
            accepted=ok,
            provider_message_id=None,
            raw_status=status.STATUS_ACCEPTED if ok else status.STATUS_FAILED,
        )

    def send_session_text(self, *, to: str, message: str) -> SendResult:
        """POST a FREE-FORM session message (only valid inside the 24h window).

        Used by the follow-up engine's in-session nudge. Inherits the SAME fail-closed
        recipient allowlist as send_template — a session send can no more reach a
        non-allowlisted number during testing than a template can.

        Endpoint: the Wati v1 session-message surface on the tenant base URL
        (`/api/v1/sendSessionMessage/{number}?messageText=…`), consistent with the proven
        `/api/v1/` calls this adapter already makes. CONFIRMED correct by a live probe on
        2026-07-24: a real POST to this endpoint for a closed window returned
        `{"result":false,"message":"Ticket has been expired.","ticketStatus":"CLOSED"}` —
        proving both that this is the right endpoint (the Phase-1 checklist's v3
        `/conversations/messages/text` path was wrong — it does not compose with the v1
        tenant base) and that `result:false` is the out-of-window signal we parse. Returns
        ACCEPTED (never treated as delivery); a session message carries no template to
        reconcile terminal status by, so in-window delivery is verified at the destination
        (getMessages statusString), not fabricated here.
        """
        number = "".join(ch for ch in str(to) if ch.isdigit())

        if not _recipient_allowed(number):
            logger.warning("WATI session-text BLOCKED by allowlist (recipient not allowlisted)")
            return SendResult(accepted=False, provider_message_id=None, raw_status=status.STATUS_BLOCKED)

        url = (
            f"{self.base_url}/api/v1/sendSessionMessage/{urllib.parse.quote(number)}"
            f"?messageText={urllib.parse.quote(message or '')}"
        )
        # No JSON body — the text rides in the query per the v1 sendSessionMessage shape.
        code, text = self._transport("POST", url, self._auth_headers(json_body=False), None)
        ok = False
        if 200 <= code < 300:
            try:
                payload = json.loads(text or "{}")
                ok = bool(payload.get("result", payload.get("ok", False)))
            except (ValueError, AttributeError):
                ok = False
        if not ok:
            logger.warning("WATI session-text not accepted: http=%s", code)
        else:
            logger.info("WATI session-text accepted: http=%s", code)
        return SendResult(
            accepted=ok,
            provider_message_id=None,
            raw_status=status.STATUS_ACCEPTED if ok else status.STATUS_FAILED,
        )

    def get_message_status(self, *, provider_message_id: str, recipient_mobile: str | None = None,
                           template: str | None = None) -> DeliveryResult:
        """Reconcile the TERMINAL status from getMessages/{mobile}.

        The send ack has no id, so we cannot key by message id — we read the recent
        messages for the recipient and match the newest broadcastMessage for this
        template. If we can't (yet) find a terminal status, we HONESTLY return the
        non-terminal 'accepted' rather than fabricating 'delivered'. A later
        reconcile pass (or webhook) can move it to terminal.
        """
        number = "".join(ch for ch in str(recipient_mobile or "") if ch.isdigit())
        if not number:
            # No mobile to reconcile against — stay honest: accepted, not delivered.
            return DeliveryResult(status=status.STATUS_ACCEPTED, meta_error_code=None, classification=None)

        url = f"{self.base_url}/api/v1/getMessages/{urllib.parse.quote(number)}?pageSize=10"
        code, text = self._transport("GET", url, self._auth_headers(json_body=False), None)
        if not (200 <= code < 300):
            logger.warning("WATI getMessages http=%s for status reconcile", code)
            return DeliveryResult(status=status.STATUS_ACCEPTED, meta_error_code=None, classification=None)

        try:
            payload = json.loads(text or "{}")
        except ValueError:
            return DeliveryResult(status=status.STATUS_ACCEPTED, meta_error_code=None, classification=None)

        items = (((payload.get("messages") or {}).get("items")) or [])
        # POSITIVE, SPECIFIC template match (Fable5 M6, refined for WATI's real shape).
        # Two templates to one number close together must not read each other's status,
        # so we still require a positive identification of THIS template. But WATI's
        # getMessages leaves `templateName` = null and instead names the template inside
        # `eventDescription` (e.g. 'Broadcast message with using "gr_..._v2"'). Matching
        # ONLY on templateName therefore never matched, stranding delivered messages at
        # 'accepted'. We now match the FULL template name against templateName OR
        # eventDescription — the full name is a unique string, so this stays specific
        # (no cross-message bleed) while actually working against the live API.
        best = None
        for it in items:  # newest-first
            if it.get("eventType") != "broadcastMessage":
                continue
            if not template:
                continue
            tname = (it.get("templateName") or "")
            desc = (it.get("eventDescription") or "")
            # QUOTED match on the description: eventDescription names the template in
            # double quotes ('… with using "<tmpl>" template …'). A bare substring test
            # bleeds across versioned names — "…_2026_07_17" is a substring of a
            # "…_2026_07_17_v2" row's description, so reconciling a v1 send could read
            # the v2 message's status (our real template family has exactly this shape).
            # The closing quote makes the match exact-name-only.
            if tname == template or f'"{template}"' in desc:
                best = it
                break

        if best is None:
            return DeliveryResult(status=status.STATUS_ACCEPTED, meta_error_code=None, classification=None)

        raw = (best.get("statusString") or "").upper()
        mapping = {
            "SENT": status.STATUS_SENT,
            "DELIVERED": status.STATUS_DELIVERED,
            "READ": status.STATUS_READ,
            "FAILED": status.STATUS_FAILED,
        }
        mapped = mapping.get(raw, status.STATUS_ACCEPTED)
        meta_code = None
        classification = None
        if mapped == status.STATUS_FAILED:
            failed_detail = best.get("failedDetail") or ""
            meta_code = _extract_meta_code(failed_detail)
            classification = status.classify_failure(meta_code)
        return DeliveryResult(status=mapped, meta_error_code=meta_code, classification=classification)

    def get_latest_inbound_at(self, mobile: str):
        """Return the newest CUSTOMER-inbound timestamp for a number (aware UTC), or None.

        The window-feed poll (apps.followups.tasks.poll_inbound_windows) uses this to
        detect when a known prospect has messaged the business (opening/refreshing their
        24h window) — the reliable trigger given Wati's inbound webhook is chatbot-
        suppressed. Reads getMessages/{number} (the SAME real-time endpoint get_message_status
        uses) and returns the newest item that is a customer message (owner is False; Wati
        marks business-sent items owner=True and broadcasts owner=None). Returns None on any
        error/absence — the poll then simply skips that contact this round.
        """
        from datetime import datetime
        from datetime import timezone as _tz

        number = "".join(ch for ch in str(mobile or "") if ch.isdigit())
        if not number:
            return None
        url = f"{self.base_url}/api/v1/getMessages/{urllib.parse.quote(number)}?pageSize=15"
        try:
            code, text = self._transport("GET", url, self._auth_headers(json_body=False), None)
            if not (200 <= code < 300):
                return None
            items = (((json.loads(text or "{}").get("messages") or {}).get("items")) or [])
        except (ValueError, AttributeError, TypeError):
            return None
        for it in items:  # newest-first
            if it.get("owner") is False:  # a genuine customer inbound (not True/None)
                raw = it.get("created") or it.get("timestamp")
                if not raw:
                    continue
                try:
                    # Wati 'created' is ISO-8601 Z; 'timestamp' may be epoch seconds.
                    if isinstance(raw, str) and "T" in raw:
                        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    return datetime.fromtimestamp(int(raw), tz=_tz.utc)
                except (ValueError, TypeError, OSError):
                    return None
        return None


def _redact_param_names(params: dict) -> str:
    """Return only the template-variable NAMES/count from a params dict — never values.

    OTP codes (and prospect PII) ride in params['template_params'] as {name,value}; the
    log-only adapter must never print the values (Fable5 M5). Returns e.g. "['code'] (1)".
    """
    if not isinstance(params, dict):
        return "()"
    tvars = params.get("template_params")
    if not isinstance(tvars, list):
        return "()"
    names = [str(p.get("name")) for p in tvars if isinstance(p, dict)]
    return f"{names} ({len(names)})"


def _extract_meta_code(failed_detail: str) -> int | None:
    """Pull the first known Meta error code out of a free-text failedDetail string."""
    for code in status.META_ERROR_MEANINGS:
        if str(code) in (failed_detail or ""):
            return code
    return None


def _recipient_allowed(number: str) -> bool:
    """Fail-closed allowlist check for the LIVE send path.

    Returns True only if WATI_ALLOW_ALL_RECIPIENTS is explicitly "true", OR the number
    (digits only) is in WATI_TEST_RECIPIENTS. An empty allowlist with allow-all off
    blocks everything (the safe default for a test run). Reading env every call is
    deliberate — the gate must reflect the CURRENT config, never a cached value.
    """
    allow_all = os.environ.get("WATI_ALLOW_ALL_RECIPIENTS", "").strip().lower() == "true"
    if allow_all:
        return True
    raw = os.environ.get("WATI_TEST_RECIPIENTS", "")
    allowed = {"".join(ch for ch in item if ch.isdigit()) for item in raw.split(",")}
    allowed.discard("")
    return number in allowed


def get_wati_adapter():
    """Return the adapter for the EFFECTIVE flag state (log-only unless sending is on).

    Reads the resolved flag (admin override -> env default), not `flags.ENABLE_WATI_SEND`
    directly: the Settings checkbox must actually change behaviour. Reading raw env here
    would let the checkbox show "on" while the code kept sending nothing — or worse, show
    "off" while it kept sending.
    """
    from apps.config.integration_flags import ENABLE_WATI_SEND, resolve_flag

    if resolve_flag(ENABLE_WATI_SEND):
        return LiveWatiAdapter()
    return LogOnlyWatiAdapter()
