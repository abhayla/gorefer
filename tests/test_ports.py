"""T-040 W1 — vendor-neutral port layer (ADR-045/046).

Covers: each factory satisfies its Protocol, flags-off resolves to the log-only
adapter and a send through the port logs rather than sends, delivery_status
re-exports behave identically to wati.status, and the services facade functions
delegate to their existing targets (pure pass-through, no new logic).
"""
from __future__ import annotations

from unittest.mock import patch

from apps.integrations import delivery_status, ports, services
from apps.integrations.wati import status as wati_status
from apps.integrations.wati.adapter import LogOnlyWatiAdapter
from apps.integrations.zoho.adapter import LogOnlyZohoAdapter
from apps.integrations.zoho.read import LogOnlyZohoReadAdapter

# --- factories satisfy their Protocol -------------------------------------

def test_messaging_port_satisfies_protocol():
    port = ports.get_messaging_port()
    assert isinstance(port, ports.MessagingPort)


def test_crm_port_satisfies_protocol():
    port = ports.get_crm_port()
    assert isinstance(port, ports.CrmPort)


def test_crm_read_port_satisfies_protocol():
    port = ports.get_crm_read_port()
    assert isinstance(port, ports.CrmReadPort)


# --- flags-off resolves to log-only, and a send logs (not sends) ----------

def test_messaging_port_is_log_only_when_flag_off():
    port = ports.get_messaging_port()
    # T-073: the factory now returns the adapter WRAPPED in the fail-closed
    # computed-variable guard. The flag still decides which adapter is inside.
    assert isinstance(port, ports.GuardedMessagingPort)
    assert isinstance(port._inner, LogOnlyWatiAdapter)
    assert port.kind == "log_only"  # delegation keeps the wrapper invisible


def test_crm_port_is_log_only_when_flag_off():
    port = ports.get_crm_port()
    assert isinstance(port, LogOnlyZohoAdapter)


def test_crm_read_port_is_log_only_when_flag_off():
    port = ports.get_crm_read_port()
    assert isinstance(port, LogOnlyZohoReadAdapter)


def test_send_via_port_logs_not_sends(caplog):
    port = ports.get_messaging_port()
    with caplog.at_level("INFO"):
        result = port.send_template(to="919876543210", template="t", params={})
    assert result.accepted is True
    assert "suppressed" in caplog.text


# --- delivery_status re-exports behave identically to wati.status ---------

def test_delivery_status_reexports_match_wati_status():
    assert delivery_status.is_terminal is wati_status.is_terminal
    assert delivery_status.is_delivered is wati_status.is_delivered
    assert delivery_status.classify_failure is wati_status.classify_failure

    for value in (wati_status.STATUS_ACCEPTED, wati_status.STATUS_SIMULATED_DELIVERED):
        assert delivery_status.is_terminal(value) == wati_status.is_terminal(value)
        assert delivery_status.is_delivered(value) == wati_status.is_delivered(value)

    assert delivery_status.classify_failure(131049) == wati_status.classify_failure(131049)


# --- services facade delegates to its target, pure pass-through -----------

def test_queue_lead_notifications_delegates():
    with patch("apps.integrations.wati.notify.queue_lead_notifications") as target:
        target.return_value = [1, 2]
        result = services.queue_lead_notifications(
            tenant="t", referral="r", prospect="p", client_id="RJ4521",
        )
    target.assert_called_once_with(tenant="t", referral="r", prospect="p", client_id="RJ4521")
    assert result == [1, 2]


def test_enqueue_lead_upsert_delegates():
    with patch("apps.integrations.zoho.tasks.enqueue_upsert") as target:
        services.enqueue_lead_upsert(42)
    target.assert_called_once_with(42)


def test_record_inbound_delegates():
    with patch("apps.integrations.wati.webhook.record_inbound") as target:
        target.return_value = {"ok": True}
        result = services.record_inbound(
            "tenant", "919876543210", "at",
            prospect_id=7, source_event="wati_inbound", pref_lang="en", text="hi",
        )
    target.assert_called_once_with(
        "tenant", "919876543210", "at",
        prospect_id=7, source_event="wati_inbound", pref_lang="en", text="hi",
    )
    assert result == {"ok": True}


def test_ingest_conversion_delegates():
    with patch("apps.integrations.zoho.ingest.ingest_conversion") as target:
        target.return_value = "conv"
        result = services.ingest_conversion(tenant="tenant", payload={"a": 1})
    target.assert_called_once_with(tenant="tenant", payload={"a": 1})
    assert result == "conv"


def test_max_sync_attempts_reexport():
    from apps.integrations.zoho.tasks import MAX_SYNC_ATTEMPTS

    assert services.MAX_SYNC_ATTEMPTS == MAX_SYNC_ATTEMPTS
