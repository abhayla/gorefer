"""Session auth for the staff-scoped Ninja routers — with CSRF enforced.

Why a class and not a plain callable: a Ninja `Router(auth=<callable>)` authenticates
the session cookie but performs **no CSRF check**, because every django-ninja view is
`csrf_exempt` at the Django middleware level (ninja/operation.py) and cookie-CSRF is
handled by the auth object instead. A plain callable therefore left the staff CRUD
surface open to classic cross-site request forgery: a malicious page could make a
logged-in staff member's browser POST/PATCH/DELETE `/api/followups/*` with their
cookie riding along.

`ninja.security.APIKeyCookie` (which `SessionAuth` subclasses) runs `check_csrf`
before authenticating, so subclassing it fixes that for the cookie-authed routers
ONLY — the token/HMAC-authed webhook routers (`/api/wati/*`, `/api/zoho/*`) and the
public capture endpoints (`/api/leads`, `/api/click`, `/api/share`) carry no cookie
auth and stay CSRF-exempt by design, exactly as their server-to-server callers need.

Semantics are identical to the `require_staff` callable this replaces: authenticated
AND `is_staff`. Ninja's own `SessionAuthIsStaff` also admits superusers who are not
staff, which would be a widening, so we keep our own narrow check.
"""
from __future__ import annotations

from typing import Any, Optional

from django.http import HttpRequest
from ninja.security import SessionAuth


class StaffSessionAuth(SessionAuth):
    """Allow only an authenticated staff user; CSRF-checked on unsafe methods."""

    def authenticate(self, request: HttpRequest, key: Optional[str]) -> Optional[Any]:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_staff:
            return user
        return None


#: Shared instance — one staff-auth mechanism across every staff-scoped router.
staff_session_auth = StaffSessionAuth()
