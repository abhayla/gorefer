"""Staff sign-in with Google (owner decision 2026-11-28).

Who may sign in is the owner-managed access list (`apps.tenants.models.StaffAccess`);
Google only proves the email. A verified Google email that is not on the list is
refused, even though Google signed the person in. The password login stays as it is.

The flow reuses the referrer Google sign-in (`apps.accounts.oauth`, server-side PKCE,
stdlib only) and its already-registered callback URL, so no new redirect URI has to
be added in Google Cloud. `start()` marks the session as a staff sign-in; the shared
callback hands such a session to `complete()` here and never to the referrer path.
"""
from __future__ import annotations

import logging

from django.contrib.auth import get_user_model, login
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts import oauth
from apps.tenants.access import resolve_grants

logger = logging.getLogger("gorefer.dashboard.staff_auth")

#: Session flag set by `start()`; the shared Google callback routes on it.
SESSION_PURPOSE = "google_oauth_purpose"
PURPOSE_STAFF = "staff"

NOT_ON_LIST = "This Google account doesn't have access. Ask the owner to add it."


def available() -> bool:
    """Google sign-in is configured AND its shared callback route is mounted (it lives
    with the referrer login, ENABLE_CUSTOMER_LOGIN). Otherwise no button (no dead UI)."""
    from django.urls import NoReverseMatch

    if not oauth.configured():
        return False
    try:
        reverse("referrer_oauth_callback")
    except NoReverseMatch:
        return False
    return True


def start(request):
    request.session[SESSION_PURPOSE] = PURPOSE_STAFF
    return redirect(oauth.build_authorization_redirect(request))


def is_staff_flow(request) -> bool:
    return request.session.get(SESSION_PURPOSE) == PURPOSE_STAFF


def _login_page(request, error: str, status: int = 400):
    from django.contrib.auth.forms import AuthenticationForm

    return render(request, "dashboard/login.html", {
        "form": AuthenticationForm(request), "google_error": error,
        "google_available": available(), "signed_in_non_staff": False,
    }, status=status)


def complete(request):
    """The shared callback, for a staff session. Signs in only listed emails."""
    request.session.pop(SESSION_PURPOSE, None)
    if request.GET.get("error"):
        return _login_page(request, "Google sign-in was cancelled.")
    try:
        claims = oauth.complete_flow(
            request, code=request.GET.get("code", ""), state=request.GET.get("state", "")
        )
    except oauth.OAuthError as exc:
        return _login_page(request, str(exc))

    from apps.tenants.models import StaffAccess

    email = claims["email"]
    if not StaffAccess.objects.filter(email=email, revoked_at__isnull=True).exists():
        logger.info("staff Google sign-in refused: not on the access list")
        return _login_page(request, NOT_ON_LIST, status=403)

    user_model = get_user_model()
    user = user_model.objects.filter(email__iexact=email, is_staff=True).order_by("id").first()
    if user is None:
        user = user_model(username=email[:150], email=email, is_staff=True, is_active=True)
        user.set_unusable_password()  # Google-only: no password exists to guess
        user.save()
    if not resolve_grants(user):  # e.g. a grant whose only business is inactive
        return _login_page(request, NOT_ON_LIST, status=403)
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect(reverse("dashboard_report"))
