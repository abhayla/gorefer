"""M5 WATI notification tests.

The DoD requires WATI send tests to assert on TERMINAL delivery status, not HTTP
200. All run in sync/demo mode (ENABLE_WATI_SEND=false → log-only adapter that
simulates a delivered terminal status), so the whole flow is exercised offline.
"""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event
from apps.integrations.models import Notification
from apps.integrations.wati import status as st
from apps.integrations.wati.adapter import LogOnlyWatiAdapter
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
    assert st.is_terminal(delivery.status)
    assert st.is_delivered(delivery.status)


def test_meta_error_classification():
    assert "marketing cap" in st.classify_failure(131049)
    assert "unclassified" in st.classify_failure(999999)


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
    # office + prospect are sent and verified to a TERMINAL delivered status.
    for role in ("office", "prospect"):
        n = Notification.objects.get(recipient_role=role)
        assert n.status == st.STATUS_DELIVERED  # terminal, not "accepted"
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
    assert ref.status == st.STATUS_DELIVERED
    assert ref.recipient_mobile == "919998887777"  # canonical normalized


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
    assert events.count() >= 2  # office + prospect delivered
    for e in events:
        assert e.source == "wati"
        assert e.metadata.get("delivery_status") == "delivered"
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
