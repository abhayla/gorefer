"""OTP delivery PORT (Q-M-OTP) — the ports-and-adapters seam.

`OtpDeliveryChannel` is the single interface every OTP channel implements. The
`OtpService` depends ONLY on this port, never on a concrete adapter, so swapping the
channel (WhatsApp/Wati -> SMS -> manual) is a config change, not a code change
(config-over-code, ADR-022).

Delivery is TERMINAL-STATUS aware (doc-08 A3): `send()` returns a `DeliveryResult`
whose `status` reflects the real terminal delivery outcome (delivered/read/failed/
queued), NEVER a bare HTTP-200 "accepted". The service treats a non-`delivered`
result as a failure and cascades to the next configured fallback channel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Terminal OTP delivery outcomes (aligned with apps.integrations.delivery_status).
STATUS_DELIVERED = "delivered"   # proven delivery (delivered/read) — the only success
STATUS_FAILED = "failed"         # terminal failure — cascade to fallback
STATUS_QUEUED = "queued"         # accepted/enqueued but delivery NOT yet proven — not success
STATUS_SUPPRESSED = "suppressed"  # demo/flag-off: intentionally not sent (logged only)


@dataclass
class DeliveryResult:
    """The outcome of one OTP send attempt through one channel.

    `status` is the terminal delivery status — the service only treats
    STATUS_DELIVERED as success. `provider_ref` is the channel's message id (for
    audit / status polling). `error` carries a human-readable classification on
    failure. NEVER put the OTP code in here — results are logged.
    """

    status: str
    provider_ref: str | None = None
    error: str | None = None
    channel: str | None = None  # which channel produced this result (set by the service)

    @property
    def delivered(self) -> bool:
        return self.status == STATUS_DELIVERED


class OtpDeliveryChannel(Protocol):
    """A pluggable OTP delivery channel.

    Implementations MUST assert terminal delivery (not HTTP 200) and MUST NOT log
    the plaintext code. `context` carries non-secret routing hints (tenant, template
    name, purpose) — never the code.
    """

    #: Stable channel code (matches the config-cascade value + registry key).
    code: str

    def send(
        self, *, recipient: str, code: str, ttl_seconds: int, context: dict
    ) -> DeliveryResult:
        ...
