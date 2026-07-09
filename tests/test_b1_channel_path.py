"""B1 — channel-as-path-prefix route /r/{channel}/{client_id} (ADR-028 extends M11).

WhatsApp dynamic URL buttons require the template variable LAST, so `?s=wa` can't
trail `{{client_id}}`; the channel therefore rides as a leading path segment
(`/r/wa/RJ4521`). This mission adds that route while keeping the legacy
`/r/{client_id}?s=` form working.

Guardrails asserted (S2-03 §11 / S2-04 B1):
  - /r/wa/RJ4521 records a click with channel=WhatsApp, sourced from the PATH.
  - the Continue 302 Location is exactly the server-assembled Zerodha URL — no
    channel, no s=, no partner-code leak in any client-facing body.
  - legacy /r/RJ4521?s=wa still works (back-compat).
  - an unknown channel code in the path normalizes to "other", never errors.
"""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event
from apps.referrals.models import Referral, ReferralIdentity


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.7"}


# --- channel read from the PATH prefix -------------------------------------

def test_channel_path_records_channel_from_path(seeded, client):
    resp = client.get("/r/wa/RJ4521", **HUMAN)
    assert resp.status_code == 200
    click = Event.objects.get(event_type="click")
    assert click.metadata.get("channel") == "WhatsApp"


@pytest.mark.parametrize(
    "code,label",
    [("fb", "Facebook"), ("li", "LinkedIn"), ("tg", "Telegram"), ("ig", "Instagram")],
)
def test_channel_path_other_codes(seeded, client, code, label):
    client.get(f"/r/{code}/RJ4521", **HUMAN)
    assert Event.objects.get(event_type="click").metadata.get("channel") == label


def test_channel_path_unknown_code_is_other_not_error(seeded, client):
    # A well-formed but unlisted code must normalize to "other" — never 404/500.
    resp = client.get("/r/zzz/RJ4521", **HUMAN)
    assert resp.status_code == 200
    assert Event.objects.get(event_type="click").metadata.get("channel") == "other"


def test_channel_path_creates_the_same_journey_as_legacy(seeded, client):
    # The channel-path form still lazily creates the referrer identity + journey.
    client.get("/r/wa/RJ4521", **HUMAN)
    assert ReferralIdentity.objects.filter(client_id="RJ4521").exists()
    assert Referral.objects.filter(source="referral_link").exists()


# --- Continue 302 strips the channel (never leaks into the Zerodha Location) ---

def test_channel_path_continue_302_is_clean(seeded, client):
    client.get("/r/wa/RJ4521", **HUMAN)
    resp = client.get("/r/wa/RJ4521/continue", HTTP_USER_AGENT="Mozilla/5.0")
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    # Exactly the server-assembled destination — no channel, no s=, nothing extra.
    assert loc == "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=RJ4521"
    assert "wa" not in loc.rsplit("r=", 1)[0]  # 'wa' never appears before the id param
    assert "s=" not in loc


def test_channel_path_continue_records_redirect_channel(
    seeded, client, django_capture_on_commit_callbacks
):
    # redirect_completed is written on transaction.on_commit — capture the callbacks
    # so the event lands within the test (the 302 itself never carries the channel).
    client.get("/r/wa/RJ4521", **HUMAN)
    with django_capture_on_commit_callbacks(execute=True):
        client.get("/r/wa/RJ4521/continue", HTTP_USER_AGENT="Mozilla/5.0")
    redirect_ev = Event.objects.filter(event_type="redirect_completed").first()
    assert redirect_ev is not None
    assert redirect_ev.metadata.get("channel") == "WhatsApp"


# --- legacy back-compat still works ----------------------------------------

def test_legacy_query_param_still_works(seeded, client):
    resp = client.get("/r/RJ4521?s=wa", **HUMAN)
    assert resp.status_code == 200
    assert Event.objects.get(event_type="click").metadata.get("channel") == "WhatsApp"


def test_legacy_continue_302_still_clean(seeded, client):
    client.get("/r/RJ4521?s=wa", **HUMAN)
    resp = client.get("/r/RJ4521/continue?s=wa", HTTP_USER_AGENT="Mozilla/5.0")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=RJ4521"


def test_bare_client_id_without_channel_unaffected(seeded, client):
    resp = client.get("/r/RJ4521", **HUMAN)
    assert resp.status_code == 200
    click = Event.objects.get(event_type="click")
    assert "channel" not in (click.metadata or {})  # renders as "Direct"


# --- routing: channel form never shadows the legacy single-id form ---------

def test_channel_converter_does_not_swallow_continue(seeded, client):
    # /r/RJ4521/continue must hit the legacy continue view (client_id=RJ4521),
    # NOT be parsed as channel=RJ4521 (uppercase → the converter rejects it anyway).
    resp = client.get("/r/RJ4521/continue", HTTP_USER_AGENT="Mozilla/5.0")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=RJ4521"


def test_guardrail_no_partner_code_in_channel_landing_body(seeded, client):
    html = client.get("/r/wa/RJ4521", **HUMAN).content.decode()
    assert "ZMPHZC" not in html
    assert "signup.zerodha.com" not in html


# --- crawler-not-a-click holds on the channel-path form too ----------------

@pytest.mark.parametrize("ua", ["facebookexternalhit/1.1", "WhatsApp/2.23.20"])
def test_crawler_on_channel_path_no_journey(seeded, client, ua):
    resp = client.get("/r/wa/RJ4521", HTTP_USER_AGENT=ua)
    assert resp.status_code == 200
    assert 'property="og:title"' in resp.content.decode()
    assert ReferralIdentity.objects.count() == 0
    assert Event.objects.count() == 0
