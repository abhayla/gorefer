"""Fable5 H2 — webhook caller-IP is resolved spoof-resistantly, and an empty IP
allowlist is refused in prod when WEBHOOK_REQUIRE_IP_ALLOWLIST is on.

The bug: taking the FIRST X-Forwarded-For entry (`xff[0]`) as the caller IP lets an
attacker prepend a trusted IP (`X-Forwarded-For: <zoho-ip>, <attacker>`) and sail
through the allowlist. nginx APPENDS the real peer, so only an entry counted from the
END (a hop our own proxies wrote) is trustworthy.
"""
from __future__ import annotations

import json

import pytest
from django.core.management import call_command
from django.test import Client

from apps.common.netaddr import trusted_client_ip

WEBHOOK = "/api/zoho/status-webhook"


class _Req:
    def __init__(self, xff=None, remote="127.0.0.1"):
        self.META = {"REMOTE_ADDR": remote}
        if xff is not None:
            self.META["HTTP_X_FORWARDED_FOR"] = xff


# --- trusted_client_ip resolution -----------------------------------------

def test_spoofed_leftmost_xff_is_not_trusted(settings):
    """With 1 trusted hop, a client that PREPENDS a fake IP cannot make us read it —
    we take the last entry (what our proxy appended), not xff[0]."""
    settings.TRUSTED_PROXY_HOPS = 1
    # Attacker sends "1.2.3.4" hoping to be seen as 1.2.3.4; our nginx appended 9.9.9.9.
    req = _Req(xff="1.2.3.4, 9.9.9.9", remote="127.0.0.1")
    assert trusted_client_ip(req) == "9.9.9.9"


def test_two_trusted_hops_reads_second_from_end(settings):
    """Cloudflare -> nginx (2 hops): the real client is the 2nd-from-end entry."""
    settings.TRUSTED_PROXY_HOPS = 2
    # xff = "<spoof>, <real-client>, <cloudflare>"; nginx appends CF, CF appended client.
    req = _Req(xff="6.6.6.6, 203.0.113.7, 172.16.0.1", remote="127.0.0.1")
    assert trusted_client_ip(req) == "203.0.113.7"


def test_short_xff_falls_back_to_remote_addr(settings):
    """XFF shorter than the trusted-hop count => don't trust a partial chain."""
    settings.TRUSTED_PROXY_HOPS = 2
    req = _Req(xff="203.0.113.7", remote="10.0.0.9")
    assert trusted_client_ip(req) == "10.0.0.9"


def test_zero_hops_uses_remote_addr(settings):
    settings.TRUSTED_PROXY_HOPS = 0
    req = _Req(xff="1.2.3.4, 9.9.9.9", remote="10.0.0.9")
    assert trusted_client_ip(req) == "10.0.0.9"


# --- allowlist enforcement uses the trusted IP ----------------------------

@pytest.mark.django_db
def test_allowlist_bypass_via_spoofed_xff_is_blocked(settings):
    """The allowlist contains a Zoho IP; an attacker from 127.0.0.1 who prepends that
    IP into XFF must still be rejected (we read the appended peer, not the spoof)."""
    call_command("seed_program")
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    settings.ZOHO_WEBHOOK_IP_ALLOWLIST = "198.51.100.5"  # the real Zoho IP
    settings.TRUSTED_PROXY_HOPS = 1
    raw = json.dumps({"event_id": "e1", "opener_zerodha_account_id": "ZA1"}).encode()
    # Attacker spoofs the allowlisted IP as xff[0]; test client's REMOTE_ADDR=127.0.0.1
    # is appended as the real peer (1 hop) -> not in allowlist -> 401.
    resp = Client().post(
        WEBHOOK, data=raw, content_type="application/json",
        HTTP_X_ZOHO_WEBHOOK_KEY="testkey",
        HTTP_X_FORWARDED_FOR="198.51.100.5, 127.0.0.1",
    )
    assert resp.status_code == 401


# --- empty-allowlist prod refusal (opt-in) --------------------------------

@pytest.mark.django_db
def test_empty_allowlist_refused_in_prod_when_required(settings):
    """DEBUG=false + WEBHOOK_REQUIRE_IP_ALLOWLIST=true + empty allowlist => reject,
    even with a correct static key (closes the 'empty = allow-any' hole)."""
    call_command("seed_program")
    settings.DEBUG = False
    settings.WEBHOOK_REQUIRE_IP_ALLOWLIST = True
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    settings.ZOHO_WEBHOOK_IP_ALLOWLIST = ""
    raw = json.dumps({"event_id": "e2", "opener_zerodha_account_id": "ZA2"}).encode()
    resp = Client().post(
        WEBHOOK, data=raw, content_type="application/json",
        HTTP_X_ZOHO_WEBHOOK_KEY="testkey",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_empty_allowlist_allowed_in_interim_posture(settings):
    """Default (WEBHOOK_REQUIRE_IP_ALLOWLIST off): the interim R2 static-key-only path
    still works with an empty allowlist, so this hardening does NOT break prod today."""
    call_command("seed_program")
    settings.DEBUG = False
    settings.WEBHOOK_REQUIRE_IP_ALLOWLIST = False
    settings.ZOHO_WEBHOOK_KEY = "testkey"
    settings.ZOHO_WEBHOOK_IP_ALLOWLIST = ""
    raw = json.dumps({"event_id": "e3", "opener_zerodha_account_id": "ZA3"}).encode()
    resp = Client().post(
        WEBHOOK, data=raw, content_type="application/json",
        HTTP_X_ZOHO_WEBHOOK_KEY="testkey",
    )
    assert resp.status_code == 200
