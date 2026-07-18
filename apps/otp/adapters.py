"""OTP channel ADAPTERS (Q-M-OTP) — one concrete implementation per port.

Each adapter implements `OtpDeliveryChannel.send()`:
  - WatiWhatsAppOtpAdapter — PRIMARY. Sends the AUTHENTICATION-category template
    (copy-code button) via the M5 Wati adapter, then VERIFIES the terminal delivery
    status (delivered/read) — never trusts the HTTP-200 "accepted" ack (doc-08 A3).
    A non-delivered terminal status returns STATUS_FAILED so the service cascades.
  - SmsOtpAdapter — interface + STUB only (no provider chosen yet). Log-only; always
    returns STATUS_FAILED so a mis-set primary=sms never silently "succeeds" without
    a real send, and cascades to the next channel.
  - ManualOtpAdapter — routes to the assisted/Ashok path (Path B). Logs/queues an
    assisted-verification request; returns STATUS_QUEUED (handoff, not proven
    delivery) so it terminates a cascade without claiming machine delivery.
  - DemoOtpAdapter — log-only offline stand-in used whenever OTP is not live
    (ENABLE_OTP_LOGIN off). Logs the INTENDED send + returns STATUS_SUPPRESSED —
    sends nothing. (With OTP on but WATI off, the WhatsApp adapter still runs, routing
    through the M5 log-only Wati adapter — so it is exercised offline, not demo-gated.)

NONE of these ever log the plaintext code — only lengths/refs. The service passes the
code in; the adapter hands it to the provider payload and never to a logger.
"""
from __future__ import annotations

import logging

from .ports import (
    STATUS_DELIVERED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_SUPPRESSED,
    DeliveryResult,
)

logger = logging.getLogger("gorefer.otp")


class WatiWhatsAppOtpAdapter:
    """PRIMARY OTP channel — WhatsApp via the M5 Wati adapter/contract.

    Sends the AUTHENTICATION-category template with a copy-code button. The OTP code
    is passed as the template's body/button parameter; the Wati adapter's payload
    carries it, but this adapter logs only the recipient + template + code length.
    Delivery is proven by the TERMINAL status (delivered/read), NOT the accepted ack.
    """

    code = "whatsapp_wati"

    def send(self, *, recipient: str, code: str, ttl_seconds: int, context: dict) -> DeliveryResult:
        from apps.integrations.wati import status as st
        from apps.integrations.wati.adapter import get_wati_adapter

        template = context.get("template") or "gorefer_login_otp"
        adapter = get_wati_adapter()
        logger.info(
            "OTP whatsapp_wati send: to=%s template=%s code_len=%d ttl=%ds",
            recipient, template, len(code), ttl_seconds,
        )
        # AUTHENTICATION template params must be an ORDERED template_params list — the
        # same contract the notify path uses (Fable5 M4). The live adapter reads ONLY
        # params["template_params"] and remaps them to positional {{1}},{{2}}; a bare
        # {"code":…} dict is silently ignored and Wati rejects the send as "blank text".
        # {{1}} = the OTP code (body var AND copy-code button carry the same value).
        result = adapter.send_template(
            to=recipient,
            template=template,
            params={"template_params": [{"name": "code", "value": code}]},
        )
        if not result.accepted:
            return DeliveryResult(status=STATUS_FAILED, provider_ref=None, error="wati not accepted")

        # HTTP-200/accepted is NOT delivery — verify the terminal status (doc-08 A3).
        # The live ack has NO message id, so status is reconciled by mobile + template
        # (getMessages), NOT by id (Fable5 M4) — passing only the empty id would make
        # every live OTP report non-terminal -> FAILED and cascade.
        delivery = adapter.get_message_status(
            provider_message_id=result.provider_message_id or "",
            recipient_mobile=recipient,
            template=template,
        )
        if st.is_delivered(delivery.status):
            return DeliveryResult(status=STATUS_DELIVERED, provider_ref=result.provider_message_id)
        return DeliveryResult(
            status=STATUS_FAILED,
            provider_ref=result.provider_message_id,
            error=st.classify_failure(delivery.meta_error_code),
        )


class SmsOtpAdapter:
    """SMS channel — interface + STUB only (real provider TBD, DF-OTP-SMS).

    Logs the intended send and returns STATUS_FAILED (not delivered) so choosing
    `sms` as primary before a provider exists never silently "succeeds" — it cascades
    to the next configured fallback. Swap this body for the real provider client when
    the SMS vendor is chosen; the port contract does not change.
    """

    code = "sms"

    def send(self, *, recipient: str, code: str, ttl_seconds: int, context: dict) -> DeliveryResult:
        logger.info(
            "OTP sms send (STUB — no provider): to=%s code_len=%d ttl=%ds",
            recipient, len(code), ttl_seconds,
        )
        return DeliveryResult(status=STATUS_FAILED, error="sms provider not configured (stub)")


class ManualOtpAdapter:
    """Manual / assisted channel (Path B) — routes to Ashok for human-assisted OTP.

    Logs/queues an assisted request. Returns STATUS_QUEUED (a human handoff, not
    machine-proven delivery) — this is a valid terminal for a cascade: the identity
    now has an assisted path, so the service stops cascading here.
    """

    code = "manual"

    def send(self, *, recipient: str, code: str, ttl_seconds: int, context: dict) -> DeliveryResult:
        # Route to the assisted queue (Ashok). We record the request; the code is
        # relayed by a human out-of-band, so it is NOT logged here either.
        logger.info(
            "OTP manual/assisted handoff queued: to=%s purpose=%s code_len=%d",
            recipient, context.get("purpose", "login"), len(code),
        )
        return DeliveryResult(status=STATUS_QUEUED, provider_ref="manual-assisted")


class DemoOtpAdapter:
    """Offline demo channel — logs the INTENDED send and sends nothing.

    Used whenever OTP is not live (ENABLE_OTP_LOGIN off). Proves the whole flow
    end-to-end offline without any network call. Returns STATUS_SUPPRESSED so tests
    can assert "nothing was sent".
    """

    code = "demo"

    def send(self, *, recipient: str, code: str, ttl_seconds: int, context: dict) -> DeliveryResult:
        logger.info(
            "[demo] OTP send SUPPRESSED (flags off): channel=%s to=%s code_len=%d ttl=%ds",
            context.get("intended_channel", "?"), recipient, len(code), ttl_seconds,
        )
        return DeliveryResult(status=STATUS_SUPPRESSED, provider_ref="demo")
