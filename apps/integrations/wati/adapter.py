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

    def send_template(self, *, to: str, template: str, params: dict) -> SendResult:
        logger.info("[demo] WATI send suppressed: to=%s template=%s params=%s", to, template, params)
        return SendResult(
            accepted=True,
            provider_message_id=f"demo-{template}-{to}",
            raw_status=status.STATUS_ACCEPTED,
        )

    def get_message_status(self, *, provider_message_id: str, recipient_mobile: str | None = None,
                           template: str | None = None) -> DeliveryResult:
        # Demo simulates a successful terminal delivery so the flow completes.
        return DeliveryResult(status=status.STATUS_DELIVERED, meta_error_code=None, classification=None)


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
        best = None
        for it in items:
            if it.get("eventType") != "broadcastMessage":
                continue
            # Match the template when we can identify it in the row.
            desc = f"{it.get('templateName', '')} {it.get('eventDescription', '')}"
            if template and template not in desc and it.get("templateName") not in (template, None, ""):
                # Not clearly this template; skip unless nothing else matches.
                if it.get("templateName"):
                    continue
            best = it  # items are newest-first; take the first plausible match
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
