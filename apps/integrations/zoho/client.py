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
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger("gorefer.zoho.client")

HTTP_TIMEOUT_SECONDS = 15

# Process-wide access-token cache keyed by refresh token: {refresh_token: (token, expiry_epoch)}
# (Fable5 M9). In-process only; each gunicorn worker keeps its own — still cuts token
# grants from once-per-call to roughly once-per-hour-per-worker, which is what avoids
# the refresh throttle. Cleared implicitly on process restart.
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}

# One lock per refresh token, so two concurrent cache-miss callers (e.g. two gunicorn
# threads both hitting a cold/expired cache at once) mint exactly ONE grant instead of
# both racing Zoho's refresh-token endpoint — which throttles grants per window (M9's
# whole reason for caching in the first place). `_TOKEN_LOCKS_GUARD` only protects
# creating a new per-key Lock, never the mint itself.
_TOKEN_LOCKS: dict[str, threading.Lock] = {}
_TOKEN_LOCKS_GUARD = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _TOKEN_LOCKS_GUARD:
        return _TOKEN_LOCKS.setdefault(key, threading.Lock())


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

    def _request(
        self, url: str, *, data: bytes | None, headers: dict, method: str, _retried: bool = False
    ) -> dict:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # Surface Zoho's own error body — "HTTP 400" alone is undiagnosable, and
            # this text is what lands in Lead.zoho_last_error for operator triage.
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 401 and not _retried and "Authorization" in headers:
                # Self-heal (M7 pt 7): a revoked/stale cached token 401s once — mint a
                # fresh one (bypassing the process cache, invalidating it for every
                # other caller too) and retry the SAME request exactly once before
                # giving up. Without this a revoked token bricks all Zoho sync for up
                # to an hour (the cache's own TTL) even though `force_refresh` existed
                # for exactly this — no call site ever used it until now. Guarded by
                # `"Authorization" in headers` so the OAuth token exchange itself
                # (which carries no Authorization header) can never recurse into this.
                logger.warning("Zoho HTTP 401 — retrying once with a force-refreshed token")
                fresh_token = self.access_token(force_refresh=True)
                retried_headers = {**headers, "Authorization": f"Zoho-oauthtoken {fresh_token}"}
                return self._request(
                    url, data=data, headers=retried_headers, method=method, _retried=True
                )
            raise RuntimeError(f"Zoho HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, OSError) as exc:
            # Connection refused / DNS / timeout — a transport failure, not a crash.
            # Mirrors wati/adapter.py's URLError/OSError handling, but Zoho callers
            # expect `_request` to raise (unlike Wati's synthetic-599-return shape),
            # so this raises the same clean RuntimeError shape as the HTTPError branch
            # above rather than returning a sentinel.
            logger.warning("Zoho transport error: %s", exc.__class__.__name__)
            raise RuntimeError(f"Zoho transport error: {exc.__class__.__name__}: {exc}") from exc
        return json.loads(body) if body else {}

    # --- auth --------------------------------------------------------------------

    def access_token(self, *, force_refresh: bool = False) -> str:
        """Return a valid access token, minting a new one only when needed (Fable5 M9).

        Previously EVERY Zoho API call re-minted a token (two HTTP round trips per call),
        and Zoho throttles refresh-token grants per window — profile-page enrichment
        (several reads per view) plus write traffic could hit that throttle and surface
        as spurious sync failures. We cache the token PROCESS-WIDE keyed by refresh
        token, until shortly before its `expires_in`, and refresh on demand (or on a
        401, via force_refresh)."""
        import time

        key = self.creds.refresh_token
        now = time.time()
        if not force_refresh:
            cached = _TOKEN_CACHE.get(key)
            if cached and cached[1] > now:
                return cached[0]

        # Guard the whole check-then-refresh-then-cache sequence per refresh-token so
        # concurrent cache-miss callers (M7 pt 33) mint exactly ONE grant — the second
        # caller blocks here, then re-checks the cache the first caller just filled
        # instead of racing it to Zoho's (throttled) refresh endpoint.
        with _lock_for(key):
            if not force_refresh:
                cached = _TOKEN_CACHE.get(key)
                if cached and cached[1] > now:
                    return cached[0]

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
            # Cache until 60s before expiry (default 3600s if Zoho omits expires_in).
            try:
                ttl = int(data.get("expires_in", 3600))
            except (TypeError, ValueError):
                ttl = 3600
            _TOKEN_CACHE[key] = (token, now + max(0, ttl - 60))
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
