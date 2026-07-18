"""The shared Zoho OAuth/HTTP client (apps/integrations/zoho/client.py).

Extracted so the live WRITE and live READ adapters share one credentials-or-refuse
path, one token refresh, and one error-surfacing rule. These tests pin the parts that
would otherwise be duplicated (and drift) across the two adapters.
"""
from __future__ import annotations

import io
import urllib.error
from unittest import mock

import pytest

from apps.integrations.zoho import client as zoho_client
from apps.integrations.zoho.client import ZohoCredentials, ZohoHttpClient


@pytest.fixture(autouse=True)
def _clear_token_cache():
    # The access-token cache (M9) is process-wide; isolate tests from each other.
    zoho_client._TOKEN_CACHE.clear()
    yield
    zoho_client._TOKEN_CACHE.clear()


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("ZOHO_CLIENT_ID", "cid")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "secret")
    monkeypatch.setenv("ZOHO_REFRESH_TOKEN", "rtok")


def test_credentials_refuse_without_env(monkeypatch):
    """Fail loud, never silently live — the whole point of the flag gate."""
    for var in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        ZohoCredentials.from_env()


def test_credentials_default_to_the_in_data_centre(creds, monkeypatch):
    """PIFS org lives on the .in DC — a .com default would 401 confusingly."""
    monkeypatch.delenv("ZOHO_API_BASE", raising=False)
    monkeypatch.delenv("ZOHO_ACCOUNTS_BASE", raising=False)
    c = ZohoCredentials.from_env()
    assert c.api_base == "https://www.zohoapis.in"
    assert c.token_url == "https://accounts.zoho.in/oauth/v2/token"


def test_api_base_is_overridable_per_environment(creds, monkeypatch):
    """So a sandbox/other-DC can be pointed at without a code change."""
    monkeypatch.setenv("ZOHO_API_BASE", "https://sandbox.zohoapis.in")
    assert ZohoCredentials.from_env().api_base == "https://sandbox.zohoapis.in"


def test_token_refresh_raises_when_zoho_returns_no_access_token(creds):
    """Zoho answers HTTP 200 + {"error": ...} on a dead refresh token, so a 200 is
    NOT proof of auth. Missing access_token must raise, not return None."""
    client = ZohoHttpClient()
    with mock.patch.object(client, "_request", return_value={"error": "invalid_code"}):
        with pytest.raises(RuntimeError, match="no access_token"):
            client.access_token()


def test_access_token_is_cached_across_calls(creds):
    """Fable5 M9: a token is minted ONCE and reused within its expiry, not re-minted
    per API call (which would hit Zoho's refresh throttle)."""
    client = ZohoHttpClient()
    calls = {"n": 0}

    def fake_request(*a, **k):
        calls["n"] += 1
        return {"access_token": "tok-123", "expires_in": 3600}

    with mock.patch.object(client, "_request", side_effect=fake_request):
        t1 = client.access_token()
        t2 = client.access_token()
        t3 = client.access_token()
    assert t1 == t2 == t3 == "tok-123"
    assert calls["n"] == 1, "token should be minted once and cached, not per-call"


def test_access_token_force_refresh_remints(creds):
    """force_refresh (e.g. on a 401) bypasses the cache and mints a fresh token."""
    client = ZohoHttpClient()
    calls = {"n": 0}

    def fake_request(*a, **k):
        calls["n"] += 1
        return {"access_token": f"tok-{calls['n']}", "expires_in": 3600}

    with mock.patch.object(client, "_request", side_effect=fake_request):
        client.access_token()
        client.access_token(force_refresh=True)
    assert calls["n"] == 2


def test_http_error_surfaces_zohos_body_not_a_bare_status(creds):
    """'HTTP 400' alone is undiagnosable; this text lands in Lead.zoho_last_error."""
    client = ZohoHttpClient()
    err = urllib.error.HTTPError(
        url="https://www.zohoapis.in/crm/v8/Leads/upsert",
        code=400,
        msg="Bad Request",
        hdrs=None,
        fp=io.BytesIO(b'{"code":"INVALID_DATA","message":"invalid field"}'),
    )
    with mock.patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(RuntimeError, match="INVALID_DATA"):
            client.get("/crm/v8/Leads/search")


def test_get_sends_the_bearer_token_and_encodes_params(creds):
    client = ZohoHttpClient()
    seen = {}

    def fake_request(url, *, data, headers, method):
        seen.update(url=url, headers=headers, method=method)
        return {"data": []}

    with mock.patch.object(client, "access_token", return_value="tok"), \
            mock.patch.object(client, "_request", side_effect=fake_request):
        client.get("/crm/v8/Contacts/search", params={"criteria": "(ClientId:equals:RJ4521)"})

    assert seen["method"] == "GET"
    assert seen["headers"]["Authorization"] == "Zoho-oauthtoken tok"
    assert "criteria=%28ClientId%3Aequals%3ARJ4521%29" in seen["url"]


def test_empty_body_is_a_no_match_not_a_crash(creds):
    """Zoho returns 204/empty for 'search matched nothing' — must map to {}."""
    client = ZohoHttpClient()
    resp = mock.MagicMock()
    resp.read.return_value = b""
    resp.__enter__.return_value = resp
    with mock.patch.object(client, "access_token", return_value="tok"), \
            mock.patch("urllib.request.urlopen", return_value=resp):
        assert client.get("/crm/v8/Contacts/search") == {}
