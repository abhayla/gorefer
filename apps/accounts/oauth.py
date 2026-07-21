"""Google OAuth 2.0 (authorization-code + PKCE) — server-side only (M13 / ADR-027).

Deliberately stdlib-only and WITHOUT any client-side Google SDK: public GoRefer
pages load NO third-party origin (test-enforced). The browser only ever *navigates*
to Google via a 302; tokens are exchanged server-to-server. Claims come from
Google's `userinfo` endpoint over TLS (no local JWT verification needed — we never
trust an unverified id_token, we simply don't parse one).

Config comes from env (`GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`),
surfaced via settings; the secret is never in a repo file. `configured()` gates the
whole door so an unconfigured deploy renders no dead Google button.

HTTP is routed through the module-level `_post_form` / `_get_json` seams so tests
exercise the flow offline (monkeypatched), same pattern as the Wati/Zoho adapters.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger("gorefer.accounts.oauth")

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"

# Session keys (single place, so login views and tests agree).
SESSION_STATE = "google_oauth_state"
SESSION_VERIFIER = "google_oauth_verifier"
SESSION_EMAIL = "google_oauth_email"  # verified email held between callback and bind


class OAuthError(Exception):
    """A failed/denied/forged OAuth exchange (surfaced as a friendly retry)."""


def configured() -> bool:
    return bool(
        getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
        and getattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "")
    )


def _redirect_uri(request) -> str:
    """The registered redirect URI — env override, else derived from the request."""
    configured_uri = getattr(settings, "GOOGLE_OAUTH_REDIRECT_URL", "")
    if configured_uri:
        return configured_uri
    from django.urls import reverse

    return request.build_absolute_uri(reverse("referrer_oauth_callback"))


def build_authorization_redirect(request) -> str:
    """Create state+PKCE, stash them in the session, return the Google auth URL."""
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    request.session[SESSION_STATE] = state
    request.session[SESSION_VERIFIER] = verifier
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": _redirect_uri(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        # We need only identity — no offline access, no refresh token retained.
        "prompt": "select_account",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urllib.parse.urlencode(params)}"


def complete_flow(request, *, code: str, state: str) -> dict:
    """Validate state, exchange the code, return verified userinfo claims.

    Returns at least {"email": ..., "email_verified": bool, "name": ...}.
    Raises OAuthError on any mismatch/denial — callers show a retry, never a 500.
    """
    expected_state = request.session.pop(SESSION_STATE, "")
    verifier = request.session.pop(SESSION_VERIFIER, "")
    if not code or not state or not expected_state or state != expected_state:
        raise OAuthError("OAuth state mismatch — please try signing in again.")

    token = _post_form(
        TOKEN_ENDPOINT,
        {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "code": code,
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": _redirect_uri(request),
        },
    )
    access_token = token.get("access_token")
    if not access_token:
        raise OAuthError("Google did not return an access token.")

    claims = _get_json(USERINFO_ENDPOINT, bearer=access_token)
    email = (claims.get("email") or "").strip().lower()
    if not email or not claims.get("email_verified", False):
        # An unverified Google email must not bind an identity (ADR-027 matches on it).
        raise OAuthError("Google account has no verified email.")
    return {
        "email": email,
        "email_verified": True,
        "name": claims.get("name") or "",
        "sub": claims.get("sub") or "",
    }


# --- HTTP seams (monkeypatched in tests; stdlib in production) --------------------

def _post_form(url: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode("ascii")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — fixed https URL
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — degrade to a retryable login error
        logger.warning("OAuth token exchange failed: %s", type(exc).__name__)
        raise OAuthError("Could not complete Google sign-in — please try again.") from exc


def _get_json(url: str, *, bearer: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — fixed https URL
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("OAuth userinfo fetch failed: %s", type(exc).__name__)
        raise OAuthError("Could not complete Google sign-in — please try again.") from exc
