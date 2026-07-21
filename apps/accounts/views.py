"""Referrer self-service login (M13): OAuth-primary + OTP-fallback + Path B.

Every URL here is mounted ONLY when ENABLE_CUSTOMER_LOGIN is on (root urls —
no dead UI, Constitution §4). Inside, the OTP door additionally honours
ENABLE_OTP_LOGIN and the Google door renders only when OAuth is configured.

Hard rules enforced here (tested):
  - the OTP request accepts ONLY a Client ID — any submitted phone field is
    rejected outright (ADR-035: the recipient is resolved on-file, never typed);
  - a referrer session renders only its OWN bound client_id (own-record scoping);
  - responses never carry a partner code or raw Zerodha URL (guardrail #3);
  - Google is reached only via a 302 — no third-party resource on any page.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import logout as auth_logout
from django.core.cache import cache
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.otp.recipient import resolve_onfile_recipient
from apps.otp.service import OtpError, OtpRateLimited, OtpService
from apps.referrals.validators import InvalidClientId, validate_client_id
from apps.tenants.resolve import get_current_tenant
from gorefer.flags import flags

from . import oauth, onfile, selfview, service

logger = logging.getLogger("gorefer.accounts.views")


# --- helpers ----------------------------------------------------------------------

def _otp_enabled() -> bool:
    return bool(flags.ENABLE_OTP_LOGIN)


def _doors():
    return {"oauth_available": oauth.configured(), "otp_available": _otp_enabled()}


def _rate_limited(request, bucket: str) -> bool:
    """Per-IP counter on the shared DB cache (same shape as the admin login lockout)."""
    if not getattr(settings, "RATELIMIT_ENABLED", False):
        return False
    from apps.common.ratelimit import client_ip

    key = f"referrer-login:{bucket}:{client_ip(request)}"
    try:
        if cache.add(key, 1, timeout=settings.RATELIMIT_LOGIN_WINDOW) is False:
            count = cache.incr(key)
        else:
            count = 1
    except ValueError:
        cache.add(key, 1, timeout=settings.RATELIMIT_LOGIN_WINDOW)
        count = 1
    return count > settings.RATELIMIT_LOGIN_MAX


def _referrer_required(view):
    """Gate a view behind an ACTIVE referrer session (redirect to referrer login)."""

    def wrapped(request, *args, **kwargs):
        account = service.account_for_request(request)
        if account is None:
            return redirect("referrer_login")
        request.referrer_account = account
        return view(request, *args, **kwargs)

    wrapped.__name__ = view.__name__
    return wrapped


def _clean_client_id(raw: str) -> str | None:
    try:
        return validate_client_id((raw or "").strip())
    except InvalidClientId:
        return None


def _mask_recipient(recipient: str) -> str:
    """Show only the last 3 digits — enough for 'yes that's my number', no more."""
    return f"•••••• {recipient[-3:]}" if len(recipient) >= 3 else "••••••"


# --- entry ------------------------------------------------------------------------

@require_GET
def login_entry(request):
    if service.account_for_request(request) is not None:
        return redirect("my_referrals")
    return render(request, "accounts/login.html", {**_doors()})


@require_GET
def my_logout(request):
    auth_logout(request)
    return redirect("home")


# --- OTP door (Path A — ADR-035) --------------------------------------------------

@require_POST
def otp_request(request):
    if not _otp_enabled():
        raise Http404()
    # ADR-035 hard rule: the recipient is NEVER user-supplied. A phone/mobile field
    # in this POST means someone is trying exactly the attack Path A forbids.
    if request.POST.get("mobile") or request.POST.get("phone") or request.POST.get("recipient"):
        return render(
            request, "accounts/login.html",
            {
                **_doors(),
                "otp_error": "Only your Client ID is needed — the code goes to the number already on file.",
            },
            status=400,
        )
    if _rate_limited(request, "otp"):
        return render(
            request, "accounts/login.html",
            {**_doors(), "otp_error": "Too many attempts. Please try again later."},
            status=429,
        )
    cid = _clean_client_id(request.POST.get("client_id", ""))
    if cid is None:
        return render(
            request, "accounts/login.html",
            {**_doors(), "otp_error": "That doesn't look like a valid Zerodha Client ID."},
            status=400,
        )
    tenant = get_current_tenant(request)
    recipient = resolve_onfile_recipient(tenant, cid)
    if not recipient:
        # Unknown referrer — no on-file channel. Never guess; offer Path B.
        return redirect(f"{_url('referrer_pathb')}?client_id={cid}")

    otp = OtpService(tenant, recipient_resolver=lambda i: resolve_onfile_recipient(tenant, i))
    try:
        result = otp.issue(cid, purpose="login")
    except OtpRateLimited as exc:
        return render(
            request, "accounts/login.html", {**_doors(), "otp_error": str(exc)}, status=429
        )
    except OtpError:
        logger.warning("OTP issue failed for client_id=%s", cid, exc_info=True)
        return render(
            request, "accounts/login.html",
            {**_doors(), "otp_error": "Could not send the code. Please try again."},
            status=502,
        )
    if not result.delivered:
        return render(
            request, "accounts/login.html",
            {
                **_doors(),
                "otp_error": "We couldn't deliver a code to your on-file number. "
                             "You can verify ownership instead.",
                "pathb_offer_client_id": cid,
            },
            status=502,
        )
    return render(
        request, "accounts/otp_verify.html",
        {"client_id": cid, "recipient_masked": _mask_recipient(recipient)},
    )


@require_POST
def otp_verify(request):
    if not _otp_enabled():
        raise Http404()
    if _rate_limited(request, "otp-verify"):
        return render(
            request, "accounts/login.html",
            {**_doors(), "otp_error": "Too many attempts. Please try again later."},
            status=429,
        )
    cid = _clean_client_id(request.POST.get("client_id", ""))
    code = (request.POST.get("code") or "").strip()
    if cid is None:
        return redirect("referrer_login")
    tenant = get_current_tenant(request)
    otp = OtpService(tenant, recipient_resolver=lambda i: resolve_onfile_recipient(tenant, i))
    result = otp.verify(cid, code)
    if not result.ok:
        messages = {
            "expired": "That code has expired — request a new one.",
            "exhausted": "Too many wrong attempts — request a new code.",
            "no_code": "No active code — request a new one.",
            "wrong": "That code is not correct.",
        }
        return render(
            request, "accounts/otp_verify.html",
            {
                "client_id": cid,
                "recipient_masked": "",
                "error": messages.get(result.reason, "Verification failed."),
                "verify_failed_reason": result.reason,
            },
            status=400,
        )
    # Ownership proven against the on-file channel — bind (tenant, client_id) + login.
    account = service.get_or_create_account(
        tenant, cid,
        bound_via=service.ReferrerAccount.BOUND_VIA_OTP,
        mobile=resolve_onfile_recipient(tenant, cid),
    )
    service.login_account(request, account)
    return redirect("my_referrals")


# --- Google OAuth door (primary — ADR-027) ----------------------------------------

@require_GET
def oauth_start(request):
    if not oauth.configured():
        raise Http404()
    return redirect(oauth.build_authorization_redirect(request))


@require_GET
def oauth_callback(request):
    if not oauth.configured():
        raise Http404()
    if request.GET.get("error"):
        return render(
            request, "accounts/login.html",
            {**_doors(), "oauth_error": "Google sign-in was cancelled."},
        )
    try:
        claims = oauth.complete_flow(
            request, code=request.GET.get("code", ""), state=request.GET.get("state", "")
        )
    except oauth.OAuthError as exc:
        return render(request, "accounts/login.html", {**_doors(), "oauth_error": str(exc)}, status=400)

    tenant = get_current_tenant(request)
    from .models import ReferrerAccount

    account = ReferrerAccount.objects.filter(
        tenant=tenant, google_email=claims["email"], status=ReferrerAccount.STATUS_ACTIVE
    ).first()
    if account is not None:
        service.login_account(request, account)
        return redirect("my_referrals")
    # First login: hold the VERIFIED email server-side and ask for the bind details.
    request.session[oauth.SESSION_EMAIL] = claims["email"]
    return redirect("referrer_oauth_bind")


@require_http_methods(["GET", "POST"])
def oauth_bind(request):
    email = request.session.get(oauth.SESSION_EMAIL, "")
    if not email:
        return redirect("referrer_login")
    if request.method == "GET":
        return render(request, "accounts/bind.html", {"google_email": email})

    if _rate_limited(request, "bind"):
        return render(
            request, "accounts/bind.html",
            {"google_email": email, "error": "Too many attempts. Please try again later."},
            status=429,
        )
    cid = _clean_client_id(request.POST.get("client_id", ""))
    entered_mobile = (request.POST.get("mobile") or "").strip()
    if cid is None:
        return render(
            request, "accounts/bind.html",
            {"google_email": email, "error": "That doesn't look like a valid Zerodha Client ID."},
            status=400,
        )
    tenant = get_current_tenant(request)
    record = onfile.resolve_onfile(tenant, cid)
    if onfile.auto_bind_matches(record, google_email=email, entered_mobile=entered_mobile):
        account = service.get_or_create_account(
            tenant, cid,
            bound_via=service.ReferrerAccount.BOUND_VIA_OAUTH_AUTO,
            google_email=email,
            mobile=record.mobile,
        )
        request.session.pop(oauth.SESSION_EMAIL, None)
        service.login_account(request, account)
        return redirect("my_referrals")
    # ADR-027: mismatch → pending verification, admin queue. Never a silent bind.
    service.submit_oauth_mismatch_request(
        tenant, client_id=cid, google_email=email, mobile_entered=entered_mobile
    )
    request.session.pop(oauth.SESSION_EMAIL, None)
    return render(request, "accounts/pending.html", {"client_id": cid})


# --- Path B (evidence — ADR-035) --------------------------------------------------

@require_http_methods(["GET", "POST"])
def path_b(request):
    prefill = _clean_client_id(request.GET.get("client_id", "")) or ""
    if request.method == "GET":
        return render(request, "accounts/pathb.html", {"client_id": prefill})

    if _rate_limited(request, "pathb"):
        return render(
            request, "accounts/pathb.html",
            {"client_id": prefill, "error": "Too many attempts. Please try again later."},
            status=429,
        )
    cid = _clean_client_id(request.POST.get("client_id", ""))
    name = (request.POST.get("registered_name") or "").strip()
    mobile = (request.POST.get("mobile") or "").strip()
    upload = request.FILES.get("evidence")
    error = None
    if cid is None:
        error = "That doesn't look like a valid Zerodha Client ID."
    elif not name:
        error = "Your registered name (as shown in the Zerodha console) is required."
    elif upload is None:
        error = "The console screenshot is required."
    if error:
        return render(
            request, "accounts/pathb.html",
            {"client_id": cid or prefill, "registered_name": name, "error": error},
            status=400,
        )
    tenant = get_current_tenant(request)
    try:
        service.submit_evidence_request(
            tenant,
            client_id=cid,
            registered_name=name,
            mobile_entered=mobile,
            evidence_bytes=upload.read(service.EVIDENCE_MAX_BYTES + 1),
            content_type=upload.content_type or "",
        )
    except service.VerificationError as exc:
        return render(
            request, "accounts/pathb.html",
            {"client_id": cid, "registered_name": name, "error": str(exc)},
            status=400,
        )
    return render(request, "accounts/pending.html", {"client_id": cid})


# --- My Referrals (ADR-026 self view) ---------------------------------------------

@require_GET
@_referrer_required
def my_referrals(request):
    account = request.referrer_account
    tenant = get_current_tenant(request)
    # Own-record scoping is STRUCTURAL: the client_id comes from the bound account,
    # never from the URL — there is no parameter to tamper with.
    ctx = selfview.my_referrals_ctx(tenant, account.client_id)
    return render(request, "dashboard/referrer_profile.html", ctx)


def _url(name: str) -> str:
    from django.urls import reverse

    return reverse(name)
