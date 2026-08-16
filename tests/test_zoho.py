"""M6 Zoho conversion sync tests.

The truth layer. Conversion status comes ONLY from the webhook ingest path
(guardrail #2). All run offline (ENABLE_ZOHO_WRITE=false → log-only adapter; the
webhook path is exercised with fixture payloads — the same path Zoho uses live).
"""
import json

import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event, SyncHealth
from apps.integrations.models import Conversion
from apps.referrals.models import Referral, ReferralIdentity
from apps.tenants.resolve import get_bootstrap_tenant

WEBHOOK = "/api/zoho/status-webhook"
KEY_HEADER = {"HTTP_X_ZOHO_WEBHOOK_KEY": "testkey"}


@pytest.fixture
def seeded(db, settings):
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


def _post(client, payload, **extra):
    return client.post(WEBHOOK, data=json.dumps(payload), content_type="application/json", **extra)


# --- webhook auth ----------------------------------------------------------

def test_webhook_rejects_without_key(seeded, client):
    r = _post(client, {"event_id": "e1", "opener_zerodha_account_id": "ZA1"})
    assert r.status_code == 401


def test_webhook_rejects_wrong_key(seeded, client):
    r = _post(client, {"event_id": "e1"}, HTTP_X_ZOHO_WEBHOOK_KEY="wrong")
    assert r.status_code == 401


# --- on-platform conversion: credit referrer by client id -----------------

@pytest.mark.django_db(transaction=True)
def test_conversion_credits_referrer_by_client_id(settings):
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")  # on-platform journey exists
    r = _post(c, {
        "event_id": "e1", "opener_zerodha_account_id": "ZA100",
        "referrer_client_id": "RJ4521", "status": "Account Opened",
        "account_opened_at": "2026-05-10T09:00:00",
    }, **KEY_HEADER)
    assert r.status_code == 200 and r.json()["applied"] is True
    conv = Conversion.objects.get()
    assert conv.referrer_client_id == "RJ4521"           # credited by client id, not mobile
    assert conv.opener_zerodha_account_id == "ZA100"     # keyed by account id
    assert conv.account_opened_at is not None            # TRUE open date stored
    # mirrored onto the referral; an account_opened event exists (Zoho-sourced)
    referral = Referral.objects.get(referral_identity__client_id="RJ4521")
    assert referral.credited_referrer == "RJ4521"
    assert Event.objects.filter(event_type="account_opened", source="zoho").count() == 1


@pytest.mark.django_db(transaction=True)
def test_real_pifs_opened_status_maps_explicitly(settings):
    """The REAL PIFS Leads picklist value 'Account Opened with Us' registers a
    conversion by EXPLICIT status-map entry (not merely the ingest fallback), so a
    non-opened status like 'Contacted' can never be mistaken for a conversion."""
    from apps.integrations.zoho import statusmap

    # Explicit mapping (verified against the live Zoho Leads layout).
    assert statusmap.map_zoho_status("Account Opened with Us") == "account_opened"
    assert statusmap.map_zoho_status("Contacted") == "contacted"        # NOT account_opened
    assert statusmap.map_zoho_status("Not Interested") == "rejected"

    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    r = _post(c, {
        "event_id": "e-realstatus", "opener_zerodha_account_id": "ZA200",
        "referrer_client_id": "RJ4521", "status": "Account Opened with Us",
        "account_opened_at": "2026-05-10T09:00:00",
    }, **KEY_HEADER)
    assert r.status_code == 200 and r.json()["applied"] is True
    conv = Conversion.objects.get()
    assert conv.status == "account_opened"
    assert Event.objects.filter(event_type="account_opened", source="zoho").count() == 1


# --- idempotency: replay is a no-op ---------------------------------------

@pytest.mark.django_db(transaction=True)
def test_replay_is_idempotent(settings):
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")
    c = Client()
    payload = {"event_id": "e1", "opener_zerodha_account_id": "ZA100",
               "referrer_client_id": "RJ4521", "status": "Account Opened"}
    assert _post(c, payload, **KEY_HEADER).json()["applied"] is True
    r2 = _post(c, payload, **KEY_HEADER)
    assert r2.json()["status"] == "duplicate"
    assert Conversion.objects.count() == 1
    assert Event.objects.filter(event_type="account_opened").count() == 1  # not double-counted


# --- off-platform zero-click conversion auto-creates journey --------------

@pytest.mark.django_db(transaction=True)
def test_offplatform_zero_click_conversion_autocreates(settings):
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")
    c = Client()
    # DA1707 never clicked — conversion arrives with zero clicks.
    r = _post(c, {
        "event_id": "e2", "opener_zerodha_account_id": "ZA200",
        "referrer_client_id": "DA1707", "status": "Account Opened",
        "account_opened_at": "2026-04-01T10:00:00",
    }, **KEY_HEADER)
    assert r.json()["applied"] is True
    assert ReferralIdentity.objects.filter(client_id="DA1707").exists()
    ref = Referral.objects.get(referral_identity__client_id="DA1707")
    assert ref.source == "zoho_import"
    assert ref.events.filter(event_type="click").count() == 0  # zero clicks


# --- reward only if Zoho signals; no amounts ------------------------------

@pytest.mark.django_db(transaction=True)
def test_reward_only_when_zoho_signals(settings):
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")
    c = Client()
    # No reward field -> account_opened terminal, no reward event.
    _post(c, {"event_id": "e1", "opener_zerodha_account_id": "ZA1", "referrer_client_id": "RJ4521",
              "status": "Account Opened"}, **KEY_HEADER)
    assert Event.objects.filter(event_type="reward_status_changed").count() == 0
    # With a reward signal -> reward event (status only, never an amount).
    _post(c, {"event_id": "e2", "opener_zerodha_account_id": "ZA2", "referrer_client_id": "DA1707",
              "status": "Account Opened", "reward_status": "credited"}, **KEY_HEADER)
    rewards = Event.objects.filter(event_type="reward_status_changed")
    assert rewards.count() == 1
    assert "amount" not in str(rewards.first().metadata)


# --- removals propagate (reversal/tombstone) ------------------------------

@pytest.mark.django_db(transaction=True)
def test_reversal_tombstones_and_emits_removed(settings):
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")
    c = Client()
    _post(c, {"event_id": "e1", "opener_zerodha_account_id": "ZA100", "referrer_client_id": "RJ4521",
              "status": "Account Opened", "account_opened_at": "2026-05-10T09:00:00"}, **KEY_HEADER)
    r = _post(c, {"event_id": "e9", "opener_zerodha_account_id": "ZA100", "reversed": True}, **KEY_HEADER)
    assert r.json()["applied"] is True
    conv = Conversion.objects.get(opener_zerodha_account_id="ZA100")
    assert conv.is_reversed is True                    # tombstoned, not deleted (audit kept)
    assert Event.objects.filter(event_type="conversion_removed").count() == 1


@pytest.mark.django_db(transaction=True)
def test_reversal_uncredits_the_referral_when_it_was_the_last_live_conversion(settings):
    """Reversal used to tombstone the Conversion and stop, leaving the Referral converted.

    Demonstrated live 2026-07-26: after Zoho de-mapped a conversion the referral still read
    conversion_status="account_opened" with the referrer credited and zero live conversions,
    so the dashboard showed a conversion that no longer existed and
    followups.services.has_converted() kept the prospect permanently suppressed.
    """
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")
    c = Client()
    _post(c, {"event_id": "r1", "opener_zerodha_account_id": "ZA200", "referrer_client_id": "RJ4521",
              "status": "Account Opened", "account_opened_at": "2026-05-10T09:00:00"}, **KEY_HEADER)
    ref = Referral.objects.get(referral_identity__client_id="RJ4521")
    assert ref.conversion_status == "account_opened"
    assert ref.credited_referrer == "RJ4521"

    _post(c, {"event_id": "r2", "opener_zerodha_account_id": "ZA200", "reversed": True}, **KEY_HEADER)
    ref.refresh_from_db()
    assert ref.conversion_status == "", "a reversed conversion must not leave the referral converted"
    assert ref.credited_referrer == "", "the referrer must not stay credited after a reversal"
    assert ref.account_opened_at is None
    assert ref.status == "opened", "journey returns to in-progress, not 'confirmed'"


@pytest.mark.django_db(transaction=True)
def test_reversal_does_NOT_uncredit_while_another_live_conversion_remains(settings):
    """A referral can carry several conversions — reversing one must not un-credit a referral
    that is still legitimately converted by another (prod referral 1 is exactly this shape)."""
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")
    c = Client()
    for eid, acct in (("m1", "ZA301"), ("m2", "ZA302")):
        _post(c, {"event_id": eid, "opener_zerodha_account_id": acct, "referrer_client_id": "RJ4521",
                  "status": "Account Opened", "account_opened_at": "2026-05-11T09:00:00"}, **KEY_HEADER)
    _post(c, {"event_id": "m3", "opener_zerodha_account_id": "ZA301", "reversed": True}, **KEY_HEADER)

    ref = Referral.objects.get(referral_identity__client_id="RJ4521")
    assert Conversion.objects.filter(referral=ref, is_reversed=False).count() == 1
    assert ref.conversion_status == "account_opened", "still converted via the surviving conversion"
    assert ref.credited_referrer == "RJ4521"


# --- composite dedupe fallback carries the reversed flag (M7 pt 14) --------

@pytest.mark.django_db(transaction=True)
def test_composite_dedupe_forward_then_reversal_both_apply(settings):
    """No `event_id` on either payload -> composite fallback. Before the fix, a
    forward event and its reversal shared the SAME composite key (account + referrer
    + date) and the reversal was silently dropped as a DuplicateDelivery of the
    forward event it was supposed to undo."""
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")
    c = Client()
    forward = {"opener_zerodha_account_id": "ZA900", "referrer_client_id": "RJ4521",
               "status": "Account Opened", "account_opened_at": "2026-05-12T09:00:00"}
    r1 = _post(c, forward, **KEY_HEADER)
    assert r1.json()["applied"] is True

    reversal = {**forward, "reversed": True}
    r2 = _post(c, reversal, **KEY_HEADER)
    assert r2.json()["applied"] is True, "the reversal must apply, not be dropped as a duplicate"
    conv = Conversion.objects.get(opener_zerodha_account_id="ZA900")
    assert conv.is_reversed is True


@pytest.mark.django_db(transaction=True)
def test_composite_dedupe_forward_replay_still_dedupes(settings):
    """The reversed-flag fold must not break the existing no-`event_id` replay
    guard — a REPEAT of the exact same forward payload is still a no-op."""
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")
    c = Client()
    forward = {"opener_zerodha_account_id": "ZA901", "referrer_client_id": "RJ4521",
               "status": "Account Opened", "account_opened_at": "2026-05-12T09:00:00"}
    assert _post(c, forward, **KEY_HEADER).json()["applied"] is True
    r2 = _post(c, forward, **KEY_HEADER)
    assert r2.json()["status"] == "duplicate"
    assert Conversion.objects.filter(opener_zerodha_account_id="ZA901").count() == 1


def test_dedupe_key_composite_includes_reversed_flag():
    """Unit-level pin on the key shape itself, independent of the webhook path."""
    from apps.integrations.zoho.ingest import _dedupe_key

    base = {"opener_zerodha_account_id": "ZA1", "referrer_client_id": "RJ1",
            "account_opened_at": "2026-01-01"}
    fwd_key = _dedupe_key(base)
    rev_key = _dedupe_key({**base, "reversed": True})
    assert fwd_key != rev_key
    # Stable/deterministic, and the event_id branch is untouched by this fix.
    assert _dedupe_key({"event_id": "abc"}) == "evt:abc"


# --- sync-freshness lights up ---------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_sync_freshness_populated_on_success(settings):
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    call_command("seed_program")
    _post(Client(), {"event_id": "e1", "opener_zerodha_account_id": "ZA1",
                     "referrer_client_id": "RJ4521", "status": "Account Opened"}, **KEY_HEADER)
    health = SyncHealth.objects.get(tenant=get_bootstrap_tenant())
    assert health.zoho_state == "healthy"
    assert health.last_successful_zoho_sync_at is not None
