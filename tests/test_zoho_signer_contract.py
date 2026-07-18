"""Contract test: the Zoho-side Deluge signer produces a seal GoRefer accepts.

This simulates EXACTLY what review/Zoho-Signer-Steps.md tells Abhay to paste into
Zoho — same signed material (timestamp.nonce.rawbody), same headers, same lowercase-hex
HMAC-SHA256 — and drives it through the real endpoint with the seal ON, proving the
signer and verifier agree byte-for-byte BEFORE anything is pasted or any flag flipped.

If this test passes, a correctly-configured Deluge signer will authenticate; if the
signer drifts from this contract, this test is where it's caught.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from django.core.management import call_command
from django.test import Client

WEBHOOK = "/api/zoho/status-webhook"
SECRET = "contract-test-secret-value-do-not-use-in-prod"


def _deluge_equivalent_sign(*, secret: str, timestamp: str, nonce: str, body_str: str) -> str:
    """Mirror of the Deluge one-liner:
        data = timestamp + "." + nonce + "." + bodyString
        sig  = zoho.encryption.hmacsha256(secret, data, "hex")   # lowercase hex
    """
    data = f"{timestamp}.{nonce}.{body_str}"
    return hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()


@pytest.fixture
def seal_on(settings, monkeypatch, db):
    monkeypatch.setenv("ENABLE_ZOHO_WEBHOOK_HMAC", "true")
    import apps.integrations.zoho.webhook as wh
    from gorefer import flags as flags_mod

    monkeypatch.setattr(wh, "flags", flags_mod.FeatureFlags.from_env())
    settings.ZOHO_WEBHOOK_HMAC_SECRET = SECRET
    settings.ZOHO_WEBHOOK_IP_ALLOWLIST = ""  # isolate the seal; IP tested elsewhere
    call_command("seed_program")
    return settings


def test_deluge_signed_request_is_accepted(seal_on):
    """A request signed the way the Deluge signer signs it authenticates + ingests."""
    body_str = json.dumps({
        "event_id": "evt-contract-1",
        "opener_zerodha_account_id": "ZA-CONTRACT-1",
        "referrer_client_id": "RJ4521",
        "status": "account opened",
        "account_opened_at": "2026-07-18",
    })
    ts = str(int(time.time()))
    nonce = "contract-nonce-1"
    sig = _deluge_equivalent_sign(secret=SECRET, timestamp=ts, nonce=nonce, body_str=body_str)

    resp = Client().post(
        WEBHOOK, data=body_str, content_type="application/json",
        HTTP_X_ZOHO_SIGNATURE=sig, HTTP_X_ZOHO_TIMESTAMP=ts, HTTP_X_ZOHO_NONCE=nonce,
    )
    assert resp.status_code == 200, resp.content


def test_the_exact_signed_bytes_must_be_sent(seal_on):
    """If the signer signs one string but the body sent differs by even one byte
    (e.g. a re-serialization reordered keys / changed spacing), the seal MUST reject —
    this is why the steps tell Abhay to POST the SAME string variable that was signed."""
    signed = '{"event_id":"e","status":"account opened"}'
    sent_different = '{"status":"account opened","event_id":"e"}'  # same data, reordered
    ts = str(int(time.time()))
    nonce = "contract-nonce-2"
    sig = _deluge_equivalent_sign(secret=SECRET, timestamp=ts, nonce=nonce, body_str=signed)

    resp = Client().post(
        WEBHOOK, data=sent_different, content_type="application/json",
        HTTP_X_ZOHO_SIGNATURE=sig, HTTP_X_ZOHO_TIMESTAMP=ts, HTTP_X_ZOHO_NONCE=nonce,
    )
    assert resp.status_code == 401  # byte mismatch -> rejected (as designed)


def test_wrong_secret_from_signer_is_rejected(seal_on):
    body_str = '{"event_id":"e","status":"account opened"}'
    ts = str(int(time.time()))
    nonce = "contract-nonce-3"
    sig = _deluge_equivalent_sign(secret="WRONG-SECRET", timestamp=ts, nonce=nonce, body_str=body_str)
    resp = Client().post(
        WEBHOOK, data=body_str, content_type="application/json",
        HTTP_X_ZOHO_SIGNATURE=sig, HTTP_X_ZOHO_TIMESTAMP=ts, HTTP_X_ZOHO_NONCE=nonce,
    )
    assert resp.status_code == 401


def test_signer_replay_is_rejected(seal_on):
    """Re-POSTing the identical signed request (same nonce) is a replay → 401 on 2nd."""
    body_str = '{"event_id":"e-replay","status":"account opened"}'
    ts = str(int(time.time()))
    nonce = "contract-nonce-replay"
    sig = _deluge_equivalent_sign(secret=SECRET, timestamp=ts, nonce=nonce, body_str=body_str)
    kw = dict(
        data=body_str, content_type="application/json",
        HTTP_X_ZOHO_SIGNATURE=sig, HTTP_X_ZOHO_TIMESTAMP=ts, HTTP_X_ZOHO_NONCE=nonce,
    )
    first = Client().post(WEBHOOK, **kw)
    second = Client().post(WEBHOOK, **kw)
    assert first.status_code == 200
    assert second.status_code == 401  # nonce already burned
