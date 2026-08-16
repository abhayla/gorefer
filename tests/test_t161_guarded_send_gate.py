"""T-161 pt 15 — the template-approval gate lives at `GuardedMessagingPort`, not in
one sender's good manners, so EVERY send path inherits it.

Three things this locks down:
  - approved-cached: a repeated send of the SAME template hits the vendor probe once,
    not once per recipient — the short-TTL cache exists so Wati is never hammered.
  - unapproved-refused: a DRAFT/UNKNOWN template refuses BEFORE the adapter's own
    send_template is ever called — zero accidental sends of an unapproved template.
  - demo-exempt: the log-only/demo adapter needs no special-casing — its own
    `get_template_status` already simulates an always-APPROVED answer, so demo mode
    (CLAUDE.md §7 "demo mode still works end-to-end") keeps sending with zero network
    calls, exactly as before this gate moved.
"""
from __future__ import annotations

import pytest

from apps.integrations import ports
from apps.integrations.wati.adapter import DeliveryResult, SendResult, TemplateStatus

TEMPLATE = "gr_test_t161_guard"


class _CountingAdapter:
    kind = "live"

    def __init__(self, *, state="APPROVED"):
        self.sent = []
        self.probe_calls = 0
        self._state = state

    def send_template(self, *, to, template, params):
        self.sent.append((to, template))
        return SendResult(accepted=True, provider_message_id="mid", raw_status="accepted")

    def get_message_status(self, *, provider_message_id, recipient_mobile=None, template=None):
        return DeliveryResult(status="delivered", meta_error_code=None, classification=None)

    def get_template_status(self, *, template):
        self.probe_calls += 1
        return TemplateStatus(name=template, status=self._state, category="UTILITY")


def test_approved_template_is_probed_once_then_cached():
    fake = _CountingAdapter(state="APPROVED")
    port = ports.GuardedMessagingPort(fake)

    for _ in range(5):
        port.send_template(to="919876543210", template=TEMPLATE, params={})

    assert len(fake.sent) == 5           # every send still goes through
    assert fake.probe_calls == 1         # but the vendor was asked exactly once


def test_unapproved_template_is_refused_before_any_send():
    fake = _CountingAdapter(state="DRAFT")
    port = ports.GuardedMessagingPort(fake)

    with pytest.raises(ports.SendRefused):
        port.send_template(to="919876543210", template=TEMPLATE, params={})

    assert fake.sent == []
    assert fake.probe_calls == 1


def test_a_vendor_error_refuses_and_is_never_cached():
    class _Flaky(_CountingAdapter):
        def get_template_status(self, *, template):
            self.probe_calls += 1
            raise RuntimeError("vendor unreachable")

    fake = _Flaky()
    port = ports.GuardedMessagingPort(fake)

    with pytest.raises(ports.SendRefused):
        port.send_template(to="919876543210", template=TEMPLATE, params={})
    with pytest.raises(ports.SendRefused):
        port.send_template(to="919876543210", template=TEMPLATE, params={})

    assert fake.sent == []
    assert fake.probe_calls == 2  # NOT cached — a transient blip is retried, not memoized


def test_an_adapter_with_no_approval_probe_refuses():
    class _NoProbe(_CountingAdapter):
        get_template_status = None

    fake = _NoProbe()
    port = ports.GuardedMessagingPort(fake)

    with pytest.raises(ports.SendRefused):
        port.send_template(to="919876543210", template=TEMPLATE, params={})
    assert fake.sent == []


def test_the_real_demo_log_only_adapter_is_exempt_with_zero_network_calls():
    """No kind-based special-case needed: LogOnlyWatiAdapter's own
    get_template_status ALREADY simulates APPROVED (no network call) — proving the
    port needs no separate demo-mode branch."""
    from apps.integrations.wati.adapter import LogOnlyWatiAdapter

    port = ports.GuardedMessagingPort(LogOnlyWatiAdapter())
    result = port.send_template(to="919876543210", template=TEMPLATE, params={})
    assert result.accepted is True


def test_the_factory_wraps_every_caller_the_same_way():
    port = ports.get_messaging_port()
    assert isinstance(port, ports.GuardedMessagingPort)
