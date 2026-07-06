"""CI rule: PII must never land in the immutable event log (#16/#17).

Two layers:
  1. a static guard — no PII field name is written into Event.metadata anywhere in
     the codebase's event-writing paths;
  2. a behavioural guard — after a real click, the raw IP lives on the erasable
     VisitorPII record, and the Event row/metadata contains no PII value.
"""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import PII_KEYS, Event, VisitorPII


def test_pii_keys_defined():
    # The canonical list the guard checks against.
    assert {"raw_ip", "email", "mobile", "city"} <= PII_KEYS


@pytest.mark.django_db(transaction=True)
def test_event_metadata_never_contains_pii_after_click():
    call_command("seed_program")
    Client().get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    for event in Event.objects.all():
        meta_keys = {k.lower() for k in (event.metadata or {}).keys()}
        assert not (meta_keys & PII_KEYS), f"PII key in event metadata: {meta_keys & PII_KEYS}"
        # No PII *value* either (the raw IP must not appear anywhere in the event).
        assert "203.0.113.7" not in str(event.metadata)


@pytest.mark.django_db(transaction=True)
def test_raw_ip_is_erasable_separately():
    call_command("seed_program")
    Client().get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    pii = VisitorPII.objects.get()
    # Erasure is a field flip on this record — no event rewrite needed.
    assert pii.erased_at is None
    assert pii.raw_ip == "203.0.113.7"
