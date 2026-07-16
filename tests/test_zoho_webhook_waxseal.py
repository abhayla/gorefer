"""DF-2 — the HMAC wax-seal on the Zoho status webhook.

Why these tests are worth their weight: this webhook is the SOLE writer of
conversion / `credited_referrer` (guardrail #2). A forged or replayed request here
fabricates a conversion and credits a referrer for an account that never opened —
which is why DF-2 was originally a P0. Each test below maps to one attack:

  forged body        -> signature mismatch                (test_tampered_body_*)
  captured + resent  -> nonce burn                        (test_replay_*)
  captured + aged    -> freshness window                  (test_stale_*)
  leaked static key  -> static key is NOT a seal fallback (test_static_key_*)
  misconfiguration   -> fail closed, never fail open      (test_*_fail_closed)
  wrong network      -> IP allowlist applies in both modes(test_ip_allowlist_*)
"""
from __future__ import annotations

import json
import time

import pytest
from django.test import Client

from apps.integrations.models import ZohoWebhookNonce
from apps.integrations.zoho.waxseal import (
    NONCE_RETENTION_SECONDS,
    compute_signature,
    purge_expired_nonces,
)

WEBHOOK = "/api/zoho/status-webhook"
SECRET = "wax-seal-test-secret"


def _payload(**over) -> dict:
    body = {
        "event_id": "evt-waxseal-1",
        "opener_zerodha_account_id": "ZA0001",
        "referrer_client_id": "RJ4521",
        "status": "account opened",
        "account_opened_at": "2026-07-10",
    }
    body.update(over)
    return body


def _sealed_headers(raw: bytes, *, secret=SECRET, ts=None, nonce="nonce-1"):
    ts = str(int(time.time())) if ts is None else str(ts)
    sig = compute_signature(secret=secret, timestamp=ts, nonce=nonce, raw_body=raw)
    return {
        "HTTP_X_ZOHO_SIGNATURE": sig,
        "HTTP_X_ZOHO_TIMESTAMP": ts,
        "HTTP_X_ZOHO_NONCE": nonce,
    }


def _post(client, raw: bytes, headers: dict):
    return client.post(WEBHOOK, data=raw, content_type="application/json", **headers)


@pytest.fixture
def seeded(db):
    """The program must exist or ingest dead-letters — which would mask a 200 and
    make the auth assertions meaningless."""
    from django.core.management import call_command

    call_command("seed_program")


@pytest.fixture
def seal_on(settings, monkeypatch):
    monkeypatch.setenv("ENABLE_ZOHO_WEBHOOK_HMAC", "true")
    settings.ZOHO_WEBHOOK_HMAC_SECRET = SECRET
    settings.ZOHO_WEBHOOK_IP_ALLOWLIST = ""
    from gorefer import flags as flags_mod

    monkeypatch.setattr(flags_mod, "flags", flags_mod.FeatureFlags.from_env())
    import apps.integrations.zoho.webhook as wh

    monkeypatch.setattr(wh, "flags", flags_mod.FeatureFlags.from_env())
    return settings


# --- happy path ------------------------------------------------------------------

@pytest.mark.django_db
def test_a_correctly_sealed_request_is_accepted(seeded, seal_on):
    raw = json.dumps(_payload()).encode()
    resp = _post(Client(), raw, _sealed_headers(raw))
    assert resp.status_code == 200, resp.content
    # The nonce was burnt, so this exact request can never be replayed.
    assert ZohoWebhookNonce.objects.filter(nonce="nonce-1").exists()


# --- forgery: the signature must cover the body ----------------------------------

@pytest.mark.django_db
def test_tampered_body_is_rejected(seal_on):
    """THE attack this exists to stop: sign a real payload, then swap the referrer.

    Under the old static key this succeeded — the key proved nothing about the body,
    so anyone holding it could credit any referrer they liked.
    """
    honest = json.dumps(_payload()).encode()
    headers = _sealed_headers(honest)
    forged = json.dumps(_payload(referrer_client_id="ATTACKER1")).encode()

    resp = _post(Client(), forged, headers)  # honest signature, forged body
    assert resp.status_code == 401


@pytest.mark.django_db
def test_wrong_secret_is_rejected(seal_on):
    raw = json.dumps(_payload()).encode()
    resp = _post(Client(), raw, _sealed_headers(raw, secret="not-the-secret"))
    assert resp.status_code == 401


@pytest.mark.django_db
def test_missing_seal_headers_are_rejected(seal_on):
    raw = json.dumps(_payload()).encode()
    assert _post(Client(), raw, {}).status_code == 401


# --- replay: the nonce is one-time -----------------------------------------------

@pytest.mark.django_db
def test_replay_of_a_byte_identical_request_is_rejected(seeded, seal_on):
    """A captured request, resent unchanged and still INSIDE the freshness window.

    The timestamp check alone cannot catch this — the request is genuinely fresh.
    Only the one-time nonce closes it.
    """
    raw = json.dumps(_payload()).encode()
    headers = _sealed_headers(raw, nonce="nonce-replay")

    first = _post(Client(), raw, headers)
    replay = _post(Client(), raw, headers)  # identical bytes, identical seal

    assert first.status_code == 200
    assert replay.status_code == 401, "a byte-identical replay must not re-apply"
    assert ZohoWebhookNonce.objects.filter(nonce="nonce-replay").count() == 1


# --- freshness -------------------------------------------------------------------

@pytest.mark.django_db
def test_stale_timestamp_is_rejected(seal_on):
    raw = json.dumps(_payload()).encode()
    old = int(time.time()) - 4000  # well beyond the 300s window
    assert _post(Client(), raw, _sealed_headers(raw, ts=old)).status_code == 401


@pytest.mark.django_db
def test_far_future_timestamp_is_rejected(seal_on):
    """Rejected via abs(skew): a forged far-future stamp would otherwise stay
    'fresh' indefinitely and neuter the freshness check entirely."""
    raw = json.dumps(_payload()).encode()
    future = int(time.time()) + 4000
    assert _post(Client(), raw, _sealed_headers(raw, ts=future)).status_code == 401


@pytest.mark.django_db
def test_non_numeric_timestamp_is_rejected(seal_on):
    raw = json.dumps(_payload()).encode()
    headers = _sealed_headers(raw)
    headers["HTTP_X_ZOHO_TIMESTAMP"] = "not-a-number"
    assert _post(Client(), raw, headers).status_code == 401


# --- the seal is not optional when enabled ---------------------------------------

@pytest.mark.django_db
def test_static_key_is_not_a_fallback_when_the_seal_is_on(seal_on):
    """If a leaked static key still worked, the seal would be decoration."""
    seal_on.ZOHO_WEBHOOK_KEY = "leaked-static-key"
    raw = json.dumps(_payload()).encode()
    resp = _post(Client(), raw, {"HTTP_X_ZOHO_WEBHOOK_KEY": "leaked-static-key"})
    assert resp.status_code == 401


@pytest.mark.django_db
def test_unset_secret_fails_closed(seal_on):
    """Flag on + no secret => reject everything. A webhook that authenticates
    everything when misconfigured is worse than one that is simply off."""
    seal_on.ZOHO_WEBHOOK_HMAC_SECRET = ""
    raw = json.dumps(_payload()).encode()
    resp = _post(Client(), raw, _sealed_headers(raw, secret=""))
    assert resp.status_code == 401


# --- IP allowlist applies in BOTH modes ------------------------------------------

@pytest.mark.django_db
def test_ip_allowlist_applies_even_to_a_perfectly_sealed_request(seal_on):
    seal_on.ZOHO_WEBHOOK_IP_ALLOWLIST = "203.0.113.9"
    raw = json.dumps(_payload()).encode()
    resp = _post(Client(), raw, _sealed_headers(raw))  # test client IP = 127.0.0.1
    assert resp.status_code == 401


# --- the interim (flag-off) path is untouched ------------------------------------

@pytest.mark.django_db
def test_flag_off_keeps_the_interim_static_key_path(seeded, settings, monkeypatch):
    """Default mode must be unchanged: the seal ships dark until Zoho's Deluge
    signer is deployed. Flipping it on early would reject every real webhook."""
    monkeypatch.setenv("ENABLE_ZOHO_WEBHOOK_HMAC", "false")
    import apps.integrations.zoho.webhook as wh
    from gorefer import flags as flags_mod

    monkeypatch.setattr(wh, "flags", flags_mod.FeatureFlags.from_env())
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    settings.ZOHO_WEBHOOK_IP_ALLOWLIST = ""

    raw = json.dumps(_payload()).encode()
    ok = _post(Client(), raw, {"HTTP_X_ZOHO_WEBHOOK_KEY": "testkey"})
    bad = _post(Client(), raw, {"HTTP_X_ZOHO_WEBHOOK_KEY": "wrong"})
    assert ok.status_code == 200 and bad.status_code == 401


# --- nonce housekeeping ----------------------------------------------------------

@pytest.mark.django_db
def test_purge_removes_only_nonces_past_the_freshness_window():
    """Old nonces are safe to forget (their timestamp already fails); recent ones
    are NOT — dropping those would re-open the replay window."""
    from datetime import timedelta

    from django.utils import timezone

    fresh = ZohoWebhookNonce.objects.create(nonce="fresh-1")
    old = ZohoWebhookNonce.objects.create(nonce="old-1")
    ZohoWebhookNonce.objects.filter(pk=old.pk).update(
        created_at=timezone.now() - timedelta(seconds=NONCE_RETENTION_SECONDS + 60)
    )

    removed = purge_expired_nonces()

    assert removed == 1
    assert ZohoWebhookNonce.objects.filter(pk=fresh.pk).exists()
    assert not ZohoWebhookNonce.objects.filter(pk=old.pk).exists()


# --- signature construction ------------------------------------------------------

def test_timestamp_and_nonce_are_bound_into_the_signature():
    """They must be SIGNED, not merely sent alongside. Otherwise an attacker keeps a
    valid signature and swaps in a fresh timestamp/nonce to beat both checks."""
    raw = b'{"a":1}'
    base = compute_signature(secret=SECRET, timestamp="1000", nonce="n1", raw_body=raw)
    assert compute_signature(secret=SECRET, timestamp="2000", nonce="n1", raw_body=raw) != base
    assert compute_signature(secret=SECRET, timestamp="1000", nonce="n2", raw_body=raw) != base
    assert compute_signature(secret=SECRET, timestamp="1000", nonce="n1", raw_body=b'{"a":2}') != base
