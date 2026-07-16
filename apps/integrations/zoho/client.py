"""Shared Zoho OAuth + HTTP plumbing for the live adapters (WRITE and READ).

Why this module exists: the live WRITE adapter (`adapter.LiveZohoAdapter`) and the
live READ adapter (`read.LiveZohoReadAdapter`) need the identical three things —
credentials-or-refuse, a refresh-token → access-token exchange, and an HTTP call that
surfaces Zoho's error body rather than a bare 4xx. Duplicating that in two places
means two places to get the DC wrong, two places to fix a token bug, and two chances
for the adapters to drift apart. It lives here once.

Credentials come from env/secret store only (never inline — doc-08 A7, the hardcoded
-JWT lesson from the Zoho Deluge functions). `ZohoCredentials.from_env()` REFUSES to
construct without ZOHO_CLIENT_ID/SECRET/REFRESH_TOKEN so a flag flip against missing
config fails LOUDLY at construction instead of silently degrading to a no-op.

DC note: the PIFS org (`passiveincomesolutions`, 60019670093) lives on the `.in` data
centre, so both the accounts host and the API host default to `.in` and are
overridable per environment via ZOHO_ACCOUNTS_BASE / ZOHO_API_BASE.

stdlib-only (urllib) — deliberately no new dependency for two adapters.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger("gorefer.zoho.client")

HTTP_TIMEOUT_SECONDS = 15


@dataclass
class ZohoCredentials:
    """Zoho OAuth config + endpoint bases. Refuses to exist without real creds."""

    client_id: str
    client_secret: str
    refresh_token: str
    api_base: str = "https://www.zohoapis.in"
    accounts_base: str = "https://accounts.zoho.in"

    @classmethod
    def from_env(cls) -> "ZohoCredentials":
        creds = cls(
            client_id=os.environ.get("ZOHO_CLIENT_ID", ""),
            client_secret=os.environ.get("ZOHO_CLIENT_SECRET", ""),
            refresh_token=os.environ.get("ZOHO_REFRESH_TOKEN", ""),
            api_base=os.environ.get("ZOHO_API_BASE", "https://www.zohoapis.in"),
            accounts_base=os.environ.get("ZOHO_ACCOUNTS_BASE", "https://accounts.zoho.in"),
        )
        if not (creds.client_id and creds.client_secret and creds.refresh_token):
            raise RuntimeError("ZOHO_* credentials not configured — cannot run live.")
        return creds

    @property
    def token_url(self) -> str:
        return f"{self.accounts_base}/oauth/v2/token"


class ZohoHttpClient:
    """Minimal authenticated Zoho REST client (token refresh + GET/POST)."""

    def __init__(self, creds: ZohoCredentials | None = None):
        self.creds = creds or ZohoCredentials.from_env()

    # --- transport ---------------------------------------------------------------

    def _request(self, url: str, *, data: bytes | None, headers: dict, method: str) -> dict:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # Surface Zoho's own error body — "HTTP 400" alone is undiagnosable, and
            # this text is what lands in Lead.zoho_last_error for operator triage.
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Zoho HTTP {exc.code}: {detail}") from exc
        return json.loads(body) if body else {}

    # --- auth --------------------------------------------------------------------

    def access_token(self) -> str:
        payload = urllib.parse.urlencode({
            "refresh_token": self.creds.refresh_token,
            "client_id": self.creds.client_id,
            "client_secret": self.creds.client_secret,
            "grant_type": "refresh_token",
        }).encode()
        data = self._request(
            self.creds.token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        token = data.get("access_token")
        if not token:
            # Zoho returns 200 + {"error": "invalid_code"} on a dead refresh token, so
            # a missing access_token is a real failure even on a 200.
            raise RuntimeError(f"Zoho token refresh returned no access_token: {data}")
        return token

    def _auth_headers(self, extra: dict | None = None) -> dict:
        headers = {"Authorization": f"Zoho-oauthtoken {self.access_token()}"}
        headers.update(extra or {})
        return headers

    # --- verbs -------------------------------------------------------------------

    def post_json(self, path: str, *, body: dict) -> dict:
        return self._request(
            f"{self.creds.api_base}{path}",
            data=json.dumps(body).encode(),
            headers=self._auth_headers({"Content-Type": "application/json"}),
            method="POST",
        )

    def get(self, path: str, *, params: dict | None = None) -> dict:
        url = f"{self.creds.api_base}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        # Zoho returns 204 (empty body) for "search matched nothing" — _request maps
        # that to {} and callers treat it as no-match, not an error.
        return self._request(url, data=None, headers=self._auth_headers(), method="GET")
