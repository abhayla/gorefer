"""M5 WATI notification tests.

The DoD requires WATI send tests to assert on TERMINAL delivery status, not HTTP
200. All run in sync/demo mode (ENABLE_WATI_SEND=false → log-only adapter that
simulates a delivered terminal status), so the whole flow is exercised offline.
"""
import json

import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event
from apps.integrations.models import Notification
from apps.integrations.wati import status as st
from apps.integrations.wati.adapter import (
    LiveWatiAdapter,
    LogOnlyWatiAdapter,
    get_wati_adapter,
)
from apps.referrals.models import Customer, ReferralProgram


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


def _capture_lead(client, client_id="RJ4521", mobile="9876543210"):
    client.get(f"/r/{client_id}", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="1.2.3.4")
    return client.post(
        "/api/leads/",
        data={"client_id": client_id, "name": "Rahul Sharma", "mobile": mobile, "consent": True},
        content_type="application/json",
    )


# --- adapter contract: terminal status, not HTTP 200 ----------------------

def test_adapter_accept_is_not_delivery():
    a = LogOnlyWatiAdapter()
    res = a.send_template(to="919876543210", template="t", params={})
    # Accepted != delivered — raw_status is 'accepted', delivery proven separately.
    assert res.accepted is True
    assert res.raw_status == st.STATUS_ACCEPTED
    delivery = a.get_message_status(provider_message_id=res.provider_message_id)
    # The log-only adapter made NO network call: its terminal status is SIMULATED,
    # reported as such (Fable5 M7) and terminal — but NOT counted as a real delivery.
    assert delivery.status == st.STATUS_SIMULATED_DELIVERED
    assert st.is_terminal(delivery.status)
    assert not st.is_delivered(delivery.status)  # simulated is never a real delivery


def test_meta_error_classification():
    assert "marketing cap" in st.classify_failure(131049)
    assert "unclassified" in st.classify_failure(999999)


# --- config-driven template names (no hardcoded names in notify.py) ------------

def test_notify_template_names_resolve_to_approved(db):
    """The lead-time notifications resolve their Meta template name from config.

    Defaults realigned 2026-07-26 to the names production ACTUALLY resolves (office ..._19,
    referrer_update ..._19/hin_19). Previously the defaults still named the 2026-07-17 office
    alert and the older referrer THANK-YOU, both of which prod had overridden — so the
    defaults were a stale fallback. That matters beyond tidiness: a default naming a template
    that has been deleted at Meta fails silently at send time, which is exactly the OTP P0
    (`gorefer_login_otp` never existed → HTTP 400 → silent degrade to `manual`)."""
    from apps.config.preferences import notify_template_name

    office = "gr_brokers_zerodha_office_lead_alert_en_2026_07_19"
    prospect_en = "gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v2"
    prospect_hi = "gr_brokers_zerodha_prospect_welcome_hi_2026_07_17_v2"
    assert notify_template_name("office", lang="en") == office
    assert notify_template_name("prospect", lang="en") == prospect_en
    assert notify_template_name("prospect", lang="hi") == prospect_hi
    assert notify_template_name("referrer", lang="en") == "gr_brokers_zerodha_referrer_update_en_2026_07_19"
    assert notify_template_name("referrer", lang="hi") == "gr_brokers_zerodha_referrer_update_hin_2026_07_19"
    # office has no Hindi variant → falls back to the English office template
    assert notify_template_name("office", lang="hi") == office
    # unknown language → English
    assert notify_template_name("prospect", lang="xx") == prospect_en


def test_notify_template_name_tenant_override(db):
    """A tenant override swaps the template with NO code change (config-over-code)."""
    from apps.config.cascade import set_tenant
    from apps.config.preferences import notify_template_name
    from apps.tenants.resolve import get_current_tenant

    call_command("seed_program")
    t = get_current_tenant()
    set_tenant("notify_template_prospect_en", "some_other_approved_template", tenant_id=t.id)
    assert notify_template_name("prospect", lang="en", tenant_id=t.id) == "some_other_approved_template"


@pytest.mark.django_db(transaction=True)
def test_notifications_use_approved_names_and_named_params():
    """On capture, the 3 notifications carry the approved template names + ordered
    named params matching each approved template's variable order."""
    call_command("seed_program")
    # make the referrer a known customer so the office alert fills referrer fields
    program = ReferralProgram.objects.get()
    Customer.objects.create(
        tenant=program.tenant, program=program, partner=program.partner,
        client_id="RJ4521", mobile="9998887777", first_name="Ramesh", last_name="Kumar",
    )
    _capture_lead(Client())

    office = Notification.objects.get(recipient_role="office")
    assert office.template == "gr_brokers_zerodha_office_lead_alert_en_2026_07_19"
    names = [p["name"] for p in office.template_params]
    assert names == ["prospect_name", "prospect_mobile", "referrer_name", "referrer_client_id"]
    by = {p["name"]: p["value"] for p in office.template_params}
    assert by["referrer_name"] == "Ramesh Kumar"
    assert by["referrer_client_id"] == "RJ4521"

    prospect = Notification.objects.get(recipient_role="prospect")
    assert prospect.template == "gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v2"
    assert [p["name"] for p in prospect.template_params] == [
        "prospect_name", "referrer_name", "office_number",
    ]

    referrer = Notification.objects.get(recipient_role="referrer")
    assert referrer.template == "gr_brokers_zerodha_referrer_update_en_2026_07_19"
    assert [p["name"] for p in referrer.template_params] == ["referrer_name", "prospect_name"]


# --- LiveWatiAdapter: flag gating, refuse-loud, POST shape, honest status ------

def test_flag_off_selects_log_only_and_no_network(monkeypatch):
    """ENABLE_WATI_SEND resolving false -> LogOnlyWatiAdapter, which performs NO
    network call. We assert the selected type and that a send needs no transport."""
    monkeypatch.setattr(
        "apps.config.integration_flags.resolve_flag", lambda *a, **k: False
    )
    adapter = get_wati_adapter()
    assert isinstance(adapter, LogOnlyWatiAdapter)
    # log-only send touches no HTTP at all (it has no transport to call).
    res = adapter.send_template(to="919876543210", template="t", params={})
    assert res.accepted is True and res.provider_message_id.startswith("demo-")


def test_live_adapter_refuses_without_creds(monkeypatch):
    monkeypatch.delenv("WATI_API_ENDPOINT", raising=False)
    monkeypatch.delenv("WATI_BASE_URL", raising=False)
    monkeypatch.delenv("WATI_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        LiveWatiAdapter()


def test_live_send_template_post_shape(monkeypatch):
    """Flag-on send builds the exact Wati sendTemplateMessage call: tenant-in-path
    base, Bearer-stripped token re-added as the scheme, number in the query, and the
    {template_name, broadcast_name, parameters} JSON body. Ack {result:true} =>
    accepted, and NO fabricated message id."""
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/999999")
    monkeypatch.setenv("WATI_API_TOKEN", "Bearer abc.def.ghi")  # leading Bearer stripped
    monkeypatch.setenv("WATI_ALLOW_ALL_RECIPIENTS", "true")  # this test asserts the POST shape

    calls = []

    def fake_transport(method, url, headers, body):
        calls.append((method, url, headers, body))
        return 200, json.dumps({"result": True})

    adapter = LiveWatiAdapter(transport=fake_transport)
    res = adapter.send_template(
        to="+91 99999 00001", template="gorefer_prospect_welcome", params={"role": "prospect"}
    )

    assert res.accepted is True
    assert res.provider_message_id is None       # ack carries no id — never fabricated
    assert res.raw_status == st.STATUS_ACCEPTED

    method, url, headers, body = calls[0]
    assert method == "POST"
    assert url.startswith("https://live-mt-server.wati.io/999999/api/v1/sendTemplateMessage?")
    assert "whatsappNumber=919999900001" in url   # normalized to digits
    assert headers["Authorization"] == "Bearer abc.def.ghi"  # scheme re-added, once
    payload = json.loads(body.decode())
    assert payload["template_name"] == "gorefer_prospect_welcome"
    assert payload["broadcast_name"] == "gorefer_prospect_welcome"
    assert payload["parameters"] == []            # no positional vars for this template


def test_live_send_remaps_semantic_params_to_positional(monkeypatch):
    """Wati matches template vars POSITIONALLY (customParams named "1","2","3"). Callers
    pass semantic names; the adapter must remap them to "1","2",… by order, or Wati
    rejects the send as blank-text (HTTP 400). This was the E2E prospect-send failure."""
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    monkeypatch.setenv("WATI_ALLOW_ALL_RECIPIENTS", "true")
    sent = {}

    def transport(method, url, headers, body):
        sent["params"] = json.loads(body.decode())["parameters"]
        return 200, '{"result":true}'

    adapter = LiveWatiAdapter(transport=transport)
    adapter.send_template(to="919999900001", template="t", params={"template_params": [
        {"name": "prospect_name", "value": "Abhay"},
        {"name": "referrer_name", "value": "Ramesh"},
        {"name": "office_number", "value": "+91 73888 82020"},
    ]})
    assert sent["params"] == [
        {"name": "1", "value": "Abhay"},
        {"name": "2", "value": "Ramesh"},
        {"name": "3", "value": "+91 73888 82020"},
    ]


def test_live_send_blocked_for_non_allowlisted_recipient(monkeypatch):
    """Fail-closed: with allow-all off, a recipient NOT in WATI_TEST_RECIPIENTS is
    BLOCKED — no transport call, raw_status=blocked, not accepted."""
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    monkeypatch.setenv("WATI_TEST_RECIPIENTS", "919999900001")
    monkeypatch.setenv("WATI_ALLOW_ALL_RECIPIENTS", "false")

    called = []
    adapter = LiveWatiAdapter(transport=lambda *a: called.append(a) or (200, '{"result":true}'))
    res = adapter.send_template(to="917388882020", template="t", params={})  # office number
    assert res.accepted is False
    assert res.raw_status == st.STATUS_BLOCKED
    assert called == []  # NO network call was made


def test_live_send_allowed_for_allowlisted_recipient(monkeypatch):
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    monkeypatch.setenv("WATI_TEST_RECIPIENTS", "919999900001")
    monkeypatch.setenv("WATI_ALLOW_ALL_RECIPIENTS", "false")
    adapter = LiveWatiAdapter(transport=lambda *a: (200, '{"result":true}'))
    res = adapter.send_template(to="+91 99999 00001", template="t", params={})
    assert res.accepted is True  # the allowlisted number goes through


def test_live_send_allow_all_bypasses_the_gate(monkeypatch):
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    monkeypatch.setenv("WATI_TEST_RECIPIENTS", "")
    monkeypatch.setenv("WATI_ALLOW_ALL_RECIPIENTS", "true")
    adapter = LiveWatiAdapter(transport=lambda *a: (200, '{"result":true}'))
    res = adapter.send_template(to="919999999999", template="t", params={})
    assert res.accepted is True


def test_live_send_empty_allowlist_blocks_everything(monkeypatch):
    """Empty allowlist + allow-all off = block all (the safe default)."""
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    monkeypatch.setenv("WATI_TEST_RECIPIENTS", "")
    monkeypatch.setenv("WATI_ALLOW_ALL_RECIPIENTS", "false")
    adapter = LiveWatiAdapter(transport=lambda *a: (200, '{"result":true}'))
    res = adapter.send_template(to="919999900001", template="t", params={})
    assert res.accepted is False and res.raw_status == st.STATUS_BLOCKED


def test_live_send_non_result_true_is_not_accepted(monkeypatch):
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    monkeypatch.setenv("WATI_ALLOW_ALL_RECIPIENTS", "true")  # isolate the result-parse path from the gate
    adapter = LiveWatiAdapter(transport=lambda *a: (200, json.dumps({"result": False})))
    res = adapter.send_template(to="919876543210", template="t", params={})
    assert res.accepted is False
    assert res.raw_status == st.STATUS_FAILED


def test_live_status_reconcile_reads_terminal(monkeypatch):
    """get_message_status reconciles the terminal status from getMessages/{mobile},
    matching the newest broadcastMessage for the template."""
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    body = json.dumps({"messages": {"items": [
        {"eventType": "broadcastMessage", "templateName": "gorefer_prospect_welcome",
         "statusString": "DELIVERED"},
    ]}})
    adapter = LiveWatiAdapter(transport=lambda *a: (200, body))
    d = adapter.get_message_status(
        provider_message_id="", recipient_mobile="919999900001",
        template="gorefer_prospect_welcome",
    )
    assert d.status == st.STATUS_DELIVERED


def test_live_status_honest_accepted_when_no_terminal(monkeypatch):
    """When getMessages shows nothing terminal yet, we return the non-terminal
    'accepted' — NEVER a fabricated 'delivered'."""
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    adapter = LiveWatiAdapter(transport=lambda *a: (200, json.dumps({"messages": {"items": []}})))
    d = adapter.get_message_status(
        provider_message_id="", recipient_mobile="919999900001", template="t"
    )
    assert d.status == st.STATUS_ACCEPTED
    assert not st.is_delivered(d.status)


def test_live_status_exact_template_match_only(monkeypatch):
    """Fable5 M6: a row for a DIFFERENT template (or a blank templateName) must NOT
    lend its status to this one — mismatched rows => honest 'accepted', not another
    message's 'delivered'."""
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    body = json.dumps({"messages": {"items": [
        # newest-first: a blank-template row then a DIFFERENT template — neither is ours.
        {"eventType": "broadcastMessage", "templateName": "", "statusString": "DELIVERED"},
        {"eventType": "broadcastMessage", "templateName": "other_template", "statusString": "READ"},
    ]}})
    adapter = LiveWatiAdapter(transport=lambda *a: (200, body))
    d = adapter.get_message_status(
        provider_message_id="", recipient_mobile="919999900001", template="gr_ours",
    )
    assert d.status == st.STATUS_ACCEPTED  # no exact match -> stay honest
    assert not st.is_delivered(d.status)


def test_live_status_matches_template_in_eventdescription(monkeypatch):
    """WATI's real getMessages leaves templateName=null and names the template inside
    eventDescription. The reconcile must match there too, or genuinely-DELIVERED
    messages get stranded at 'accepted' (found live, 2026-07-19)."""
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    tpl = "gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v2"
    body = json.dumps({"messages": {"items": [
        {"eventType": "broadcastMessage", "templateName": None,
         "eventDescription": f'Broadcast message with using "{tpl}"',
         "statusString": "DELIVERED"},
    ]}})
    adapter = LiveWatiAdapter(transport=lambda *a: (200, body))
    d = adapter.get_message_status(
        provider_message_id="", recipient_mobile="919999900001", template=tpl,
    )
    assert d.status == st.STATUS_DELIVERED


def test_live_status_eventdescription_of_other_template_not_matched(monkeypatch):
    """An eventDescription naming a DIFFERENT template must NOT match ours."""
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    body = json.dumps({"messages": {"items": [
        {"eventType": "broadcastMessage", "templateName": None,
         "eventDescription": 'Broadcast message with using "some_other_template"',
         "statusString": "DELIVERED"},
    ]}})
    adapter = LiveWatiAdapter(transport=lambda *a: (200, body))
    d = adapter.get_message_status(
        provider_message_id="", recipient_mobile="919999900001", template="gr_ours",
    )
    assert d.status == st.STATUS_ACCEPTED  # not ours -> stay honest


def test_live_status_picks_the_matching_template_among_several(monkeypatch):
    """When several templates went to one number, read THIS template's row, exactly."""
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    body = json.dumps({"messages": {"items": [
        {"eventType": "broadcastMessage", "templateName": "office_alert", "statusString": "FAILED",
         "failedDetail": "Meta 131026 undeliverable"},
        {"eventType": "broadcastMessage", "templateName": "gr_ours", "statusString": "DELIVERED"},
    ]}})
    adapter = LiveWatiAdapter(transport=lambda *a: (200, body))
    d = adapter.get_message_status(
        provider_message_id="", recipient_mobile="919999900001", template="gr_ours",
    )
    assert d.status == st.STATUS_DELIVERED  # our row, not the other template's FAILED


def test_live_status_failed_classifies_meta_code(monkeypatch):
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    body = json.dumps({"messages": {"items": [
        {"eventType": "broadcastMessage", "templateName": "t",
         "statusString": "FAILED", "failedDetail": "Meta 131049 higher quality messaging"},
    ]}})
    adapter = LiveWatiAdapter(transport=lambda *a: (200, body))
    d = adapter.get_message_status(provider_message_id="", recipient_mobile="91999", template="t")
    assert d.status == st.STATUS_FAILED
    assert d.meta_error_code == 131049
    assert "marketing cap" in d.classification


# --- three notifications on lead capture ----------------------------------

@pytest.mark.django_db(transaction=True)
def test_three_notifications_fire_on_lead_capture():
    call_command("seed_program")
    resp = _capture_lead(Client())
    assert resp.status_code == 201
    roles = set(Notification.objects.values_list("recipient_role", flat=True))
    assert roles == {"office", "prospect", "referrer"}


@pytest.mark.django_db(transaction=True)
def test_notifications_reach_terminal_delivered_status():
    call_command("seed_program")
    _capture_lead(Client())
    # In demo (log-only adapter) office + prospect reach a TERMINAL status that is
    # honestly SIMULATED (M7) — never fabricated as a real 'delivered' — and stamped
    # with the adapter that produced it.
    for role in ("office", "prospect"):
        n = Notification.objects.get(recipient_role=role)
        assert n.status == st.STATUS_SIMULATED_DELIVERED  # terminal, not "accepted"
        assert st.is_terminal(n.status) and not st.is_delivered(n.status)
        assert n.adapter_kind == "log_only"
        assert n.provider_message_id  # a provider id was recorded


@pytest.mark.django_db(transaction=True)
def test_referrer_skipped_when_phone_unknown():
    call_command("seed_program")
    _capture_lead(Client())
    ref = Notification.objects.get(recipient_role="referrer")
    assert ref.status == "skipped"
    assert "phone unknown" in ref.skip_reason


@pytest.mark.django_db(transaction=True)
def test_referrer_notified_when_phone_known():
    call_command("seed_program")
    program = ReferralProgram.objects.get()
    Customer.objects.create(
        tenant=program.tenant, program=program, partner=program.partner,
        client_id="RJ4521", mobile="9998887777", first_name="Ramesh",
    )
    _capture_lead(Client())
    ref = Notification.objects.get(recipient_role="referrer")
    assert ref.status == st.STATUS_SIMULATED_DELIVERED  # demo/log-only terminal (M7)
    assert ref.recipient_mobile == "919998887777"  # canonical normalized


# --- reconcile sweep (Fable5 H4) ------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_reconcile_finalizes_a_stranded_accepted_row(monkeypatch):
    """A notification left at ACCEPTED (terminal status not ready at send time) is
    moved to its real terminal status by the scheduled reconcile sweep."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.integrations.wati import tasks
    from apps.integrations.wati.adapter import DeliveryResult
    from apps.tenants.resolve import get_bootstrap_tenant

    call_command("seed_program")
    t = get_bootstrap_tenant()
    n = Notification.objects.create(
        tenant=t, recipient_role="office", recipient_mobile="919999900001",
        template="gr_ours", idempotency_key="k1", status=st.STATUS_ACCEPTED,
        provider_message_id="", adapter_kind="live",
    )
    # Age the row past the min-age cutoff so the sweep considers it.
    Notification.objects.filter(pk=n.pk).update(
        updated_at=timezone.now() - timedelta(minutes=tasks.RECONCILE_MIN_AGE_MINUTES + 1)
    )
    # Fake a live adapter that now reports DELIVERED.
    class _A:
        def get_message_status(self, **kw):
            return DeliveryResult(status=st.STATUS_DELIVERED, meta_error_code=None, classification=None)
    monkeypatch.setattr(tasks, "_adapter_for_reconcile", lambda n: _A())

    out = tasks.reconcile_pending_deliveries()
    n.refresh_from_db()
    assert n.status == st.STATUS_DELIVERED
    assert out["finalized"] == 1


@pytest.mark.django_db(transaction=True)
def test_reconcile_expires_a_very_old_pending_row(monkeypatch):
    """A row still non-terminal past the expire window is marked FAILED so the leak is
    VISIBLE, never silently 'accepted' forever."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.integrations.wati import tasks
    from apps.integrations.wati.adapter import DeliveryResult
    from apps.tenants.resolve import get_bootstrap_tenant

    call_command("seed_program")
    t = get_bootstrap_tenant()
    n = Notification.objects.create(
        tenant=t, recipient_role="office", recipient_mobile="919999900001",
        template="gr_ours", idempotency_key="k2", status=st.STATUS_ACCEPTED, adapter_kind="live",
    )
    Notification.objects.filter(pk=n.pk).update(
        updated_at=timezone.now() - timedelta(minutes=tasks.RECONCILE_EXPIRE_MINUTES + 1)
    )
    class _A:
        def get_message_status(self, **kw):
            return DeliveryResult(status=st.STATUS_ACCEPTED, meta_error_code=None, classification=None)
    monkeypatch.setattr(tasks, "_adapter_for_reconcile", lambda n: _A())

    out = tasks.reconcile_pending_deliveries()
    n.refresh_from_db()
    assert n.status == st.STATUS_FAILED
    assert out["expired"] == 1
    assert "reconcile window" in n.failure_classification


# --- dedup ----------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_notifications_deduped_across_repeat_capture():
    call_command("seed_program")
    c = Client()
    _capture_lead(c)
    _capture_lead(c)  # same (client_id, mobile) -> lead dedups, notifications too
    # Exactly one row per role per journey.
    assert Notification.objects.filter(recipient_role="office").count() == 1
    assert Notification.objects.filter(recipient_role="prospect").count() == 1


# --- funnel starts at delivered (Gap 12) ----------------------------------

@pytest.mark.django_db(transaction=True)
def test_notification_events_recorded_for_funnel():
    call_command("seed_program")
    _capture_lead(Client())
    events = Event.objects.filter(event_type="notification")
    assert events.count() >= 2  # office + prospect (demo: simulated terminal)
    for e in events:
        assert e.source == "wati"
        # Demo path records the honest simulated terminal status (M7), not a fake real one.
        assert e.metadata.get("delivery_status") == "simulated_delivered"
        # no PII in the notification event
        assert "9876543210" not in str(e.metadata)


# --- no stale-lead nudge (explicitly NOT built — REQ-F01 deferred) --------

def test_no_stale_lead_nudge_function_exists():
    # The deferred stale-lead auto-nudge must not be implemented in Sprint 1.
    import apps.integrations.wati.notify as notify
    import apps.integrations.wati.tasks as tasks
    for mod in (notify, tasks):
        names = [n.lower() for n in dir(mod)]
        assert not any("nudge" in n or "stale" in n for n in names)


def test_live_status_versioned_prefix_name_does_not_bleed(monkeypatch):
    """A v1 template name is a SUBSTRING of its v2 sibling's eventDescription
    ("…_2026_07_17" ⊂ "…_2026_07_17_v2") — the quoted-name match must not let a
    v1 reconcile read the v2 row's status (found live, 2026-07-19). The v1 row
    further down the list must be the one matched."""
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/1")
    monkeypatch.setenv("WATI_API_TOKEN", "tok")
    v1 = "gr_brokers_zerodha_prospect_welcome_en_2026_07_17"
    v2 = v1 + "_v2"
    body = json.dumps({"messages": {"items": [
        # newest first: the v2 send FAILED...
        {"eventType": "broadcastMessage", "templateName": None,
         "eventDescription": f'Broadcast message with using "{v2}" template',
         "statusString": "FAILED", "failedDetail": "131049"},
        # ...the older v1 send was DELIVERED.
        {"eventType": "broadcastMessage", "templateName": None,
         "eventDescription": f'Broadcast message with using "{v1}" template',
         "statusString": "DELIVERED"},
    ]}})
    adapter = LiveWatiAdapter(transport=lambda *a: (200, body))
    d = adapter.get_message_status(
        provider_message_id="", recipient_mobile="919999900001", template=v1,
    )
    assert d.status == st.STATUS_DELIVERED  # v1 must match ITS row, not the v2 failure


# --- D9: NAMED template params (needed for dynamic URL buttons) --------------

def _capture_adapter(monkeypatch, calls):
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/999999")
    monkeypatch.setenv("WATI_API_TOKEN", "abc.def.ghi")
    monkeypatch.setenv("WATI_ALLOW_ALL_RECIPIENTS", "true")

    def transport(method, url, headers, body):
        calls.append(json.loads(body.decode()))
        return 200, json.dumps({"result": True})

    return LiveWatiAdapter(transport=transport)


def test_template_params_remap_to_positional_by_default(monkeypatch):
    """Default behaviour UNCHANGED: semantic names -> positional "1","2".

    Most templates were created with positional customParams and Wati rejects a send it
    cannot fill ("blank text", HTTP 400), so this remapping must keep working.
    """
    calls = []
    a = _capture_adapter(monkeypatch, calls)
    a.send_template(to="919999900002", template="tmpl", params={"template_params": [
        {"name": "name", "value": "Ramesh"}, {"name": "prospect", "value": "Rahul"},
    ]})
    assert [p["name"] for p in calls[0]["parameters"]] == ["1", "2"]
    assert [p["value"] for p in calls[0]["parameters"]] == ["Ramesh", "Rahul"]


def test_template_params_named_preserves_names_for_button_templates(monkeypatch):
    """D9: with template_params_named the names SURVIVE — required by a URL button.

    The v9 referrer-nudge templates carry the referral link in a dynamic URL button whose
    `buttonParamMapping` points at paramName `client_id`. A button variable has its OWN
    index space, so positional remapping can never reach it and the button would render
    unfilled. Verified against the live Wati contract 2026-07-27.
    """
    calls = []
    a = _capture_adapter(monkeypatch, calls)
    a.send_template(to="919999900002", template="tmpl", params={
        "template_params_named": True,
        "template_params": [
            {"name": "name", "value": "Ramesh"},
            {"name": "prospect", "value": "Rahul"},
            {"name": "client_id", "value": "RJ4521"},
        ],
    })
    sent = {p["name"]: p["value"] for p in calls[0]["parameters"]}
    assert sent == {"name": "Ramesh", "prospect": "Rahul", "client_id": "RJ4521"}
