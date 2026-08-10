"""OTP channel REGISTRY (Q-M-OTP) — resolve a config channel code to an adapter.

The registry is the ONE place a channel code (`whatsapp_wati|sms|manual`, from the
config cascade) maps to a concrete adapter instance. `resolve_channel()` also applies
the DEMO GATE: when OTP is not live (ENABLE_OTP_LOGIN off), or the WhatsApp path's
ENABLE_WATI_SEND is off, it returns the DemoOtpAdapter (log-only, sends nothing) —
so demo mode logs the intended send and sends nothing (guardrail #3), and switching
the primary channel via config takes effect with NO code change (guardrail #4:
the service reads the code from config and this registry does the rest).
"""
from __future__ import annotations

from gorefer.flags import flags  # noqa: F401  (is_otp_live reads the current snapshot)

from .adapters import (
    DemoOtpAdapter,
    EmailOtpAdapter,
    ManualOtpAdapter,
    SmsOtpAdapter,
    WatiWhatsAppOtpAdapter,
)

#: The T-078 second-leg channel code. Deliberately NOT in OTP_CHANNEL_CHOICES: email
#: is a simultaneous ADDITION governed by ENABLE_EMAIL_OTP, not a cascade slot an
#: admin picks as primary/fallback.
EMAIL_CHANNEL = "email"

# Config channel code -> adapter factory. Adding a channel is a one-line entry here
# plus its adapter — never a change to the service.
_REGISTRY = {
    "whatsapp_wati": WatiWhatsAppOtpAdapter,
    "sms": SmsOtpAdapter,
    "manual": ManualOtpAdapter,
    # T-078: resolved through the SAME registry + demo gate as every other channel,
    # so ENABLE_OTP_LOGIN off => DemoOtpAdapter => nothing is emailed either.
    EMAIL_CHANNEL: EmailOtpAdapter,
}


def is_otp_live() -> bool:
    """OTP actually sends only when the master flag is on. Off => demo (log-only)."""
    return bool(flags.ENABLE_OTP_LOGIN)


def is_email_otp_live() -> bool:
    """The email leg fires only with BOTH flags on (T-078).

    ENABLE_EMAIL_OTP alone is not enough: with the OTP master flag off the whole
    login OTP feature is in demo mode, and a demo challenge must not send real mail.
    """
    return bool(flags.ENABLE_EMAIL_OTP) and bool(flags.ENABLE_OTP_LOGIN)


def resolve_channel(code: str):
    """Return the adapter for a channel code, applying the demo/flag gate.

    - OTP master flag off -> DemoOtpAdapter (log-only, sends nothing) for EVERY
      channel: demo mode logs the intended send and sends nothing (guardrail #3).
    - master on -> the real adapter for the code. The WhatsApp adapter itself routes
      through the M5 Wati adapter, which is ALREADY log-only when ENABLE_WATI_SEND is
      off — so WhatsApp is still exercised end-to-end offline (terminal-status path)
      without a second demo gate.
    - unknown code -> ManualOtpAdapter (fail safe to the assisted path, never crash).
    """
    if not is_otp_live():
        adapter = DemoOtpAdapter()
        adapter.code = code  # preserve the intended code for audit
        return adapter

    factory = _REGISTRY.get(code)
    if factory is None:
        return ManualOtpAdapter()
    return factory()
