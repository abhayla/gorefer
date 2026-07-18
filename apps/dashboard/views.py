"""Admin dashboard / explorer / journey detail views (M7).

Internal, behind the M1 env-bootstrap admin login (staff-only). Renders in demo
mode from seeded data. Reads headline counts from M4 rollups + read models. No raw
Zerodha URL / partner code in any response (#3). PII (mobile) masked for display.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from apps.referrals.models import Referral
from apps.referrals.validators import InvalidClientId, validate_client_id
from apps.tenants.resolve import get_current_tenant

from . import preferences_service, profile, queries


def _staff_required(view):
    """Gate a view behind login + is_staff (admin-only, Sprint 1)."""
    return login_required(
        user_passes_test(lambda u: u.is_staff, login_url="dashboard_login")(view),
        login_url="dashboard_login",
    )


class DashboardLoginView(LoginView):
    """Admin login with a per-IP failed-attempt lockout (Fable5 H3).

    The stock LoginView allows unlimited password guesses. We count consecutive
    failures per client IP in the DB cache; past RATELIMIT_LOGIN_MAX within the window
    the form is refused (locked) until the window elapses. A successful login clears
    the counter. Disabled under DEBUG (RATELIMIT_ENABLED off) so dev/CI isn't locked.
    """

    template_name = "dashboard/login.html"
    redirect_authenticated_user = True

    def _lock_key(self):
        from apps.common.ratelimit import client_ip

        return f"login-fail:{client_ip(self.request)}"

    def _is_locked(self) -> bool:
        from django.core.cache import cache

        if not getattr(settings, "RATELIMIT_ENABLED", False):
            return False
        return (cache.get(self._lock_key()) or 0) >= settings.RATELIMIT_LOGIN_MAX

    def post(self, request, *args, **kwargs):
        from django.shortcuts import render

        if self._is_locked():
            form = self.get_form()
            form.add_error(None, "Too many failed attempts. Try again later.")
            return render(request, self.template_name, {"form": form}, status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        from django.core.cache import cache

        cache.delete(self._lock_key())  # reset on success
        return super().form_valid(form)

    def form_invalid(self, form):
        from django.core.cache import cache

        if getattr(settings, "RATELIMIT_ENABLED", False):
            key = self._lock_key()
            try:
                if cache.add(key, 1, timeout=settings.RATELIMIT_LOGIN_WINDOW) is False:
                    cache.incr(key)
            except ValueError:
                cache.add(key, 1, timeout=settings.RATELIMIT_LOGIN_WINDOW)
        return super().form_invalid(form)


def _sync_health(tenant):
    """Topbar status indicators — FLAG-DRIVEN (green = switched ON, red = OFF).

    Two states only, reflecting the integration flags the admin controls in Settings;
    NOT activity-based (a green light does not wait for a real sync/send). Zoho is ON
    when WRITE or READ is on; WATI is ON when send is on. (Abhay 2026-07-18.)
    """
    from apps.config.integration_flags import (
        ENABLE_WATI_SEND,
        ENABLE_ZOHO_READ,
        ENABLE_ZOHO_WRITE,
        resolve_flag,
    )

    from .health import worker_health

    tid = getattr(tenant, "id", None)
    zoho_on = resolve_flag(ENABLE_ZOHO_WRITE, tenant_id=tid) or resolve_flag(ENABLE_ZOHO_READ, tenant_id=tid)
    wati_on = resolve_flag(ENABLE_WATI_SEND, tenant_id=tid)
    # Worker liveness is ACTIVITY-based (a heartbeat), unlike the flag-driven Zoho/WATI
    # lights — a dead qcluster silently stops every scheduled sweep, so it must show.
    return {"zoho_on": zoho_on, "wati_on": wati_on, "worker": worker_health()}


@_staff_required
@require_GET
def dashboard(request):
    tenant = get_current_tenant(request)
    # Recompute dirty rollups on view so KPI + funnel + leaderboard read one
    # consistent, fresh snapshot (OBS-1); expose its "counts as of" timestamp.
    counts_as_of = queries.refresh_and_freshness(tenant)
    ctx = {
        "kpis": queries.kpis(tenant),
        "funnel": queries.funnel(tenant),
        "top_referrers": queries.top_referrers(tenant),
        "recent_leads": queries.recent_leads(tenant),
        "sync_health": _sync_health(tenant),
        "confirmed_clicks": queries.confirmed_clicks(tenant),
        "counts_as_of": counts_as_of,
        "nav_active": "dashboard",
    }
    return render(request, "dashboard/dashboard.html", ctx)


@_staff_required
@require_GET
def explorer(request):
    tenant = get_current_tenant(request)
    source = request.GET.get("source", "")
    status = request.GET.get("status", "")
    search = request.GET.get("q", "")
    ctx = {
        "rows": queries.explorer_rows(tenant, source=source, status=status, search=search),
        "filter_source": source,
        "filter_status": status,
        "search": search,
        "sync_health": _sync_health(tenant),
        "sources": ["referral_link", "partner_direct", "zoho_import"],
        "nav_active": "explorer",
    }
    return render(request, "dashboard/explorer.html", ctx)


@_staff_required
@require_GET
def journey(request, referral_id: int):
    tenant = get_current_tenant(request)
    referral = Referral.objects.filter(id=referral_id, tenant=tenant).select_related(
        "referral_identity"
    ).first()
    if referral is None:
        raise Http404("journey not found")
    detail = queries.journey_detail(referral)
    identity = referral.referral_identity
    ctx = {
        "referral": referral,
        "client_id": identity.client_id if identity else "",
        "source": referral.source,
        "timeline": detail["timeline"],
        "conversion": detail["conversion"],
        "sync_health": _sync_health(tenant),
        "nav_active": "explorer",
    }
    return render(request, "dashboard/journey.html", ctx)


@_staff_required
@require_GET
def referrer_search(request):
    """Referral Profile entry: search a referrer by client_id / name → profile.

    An exact client_id match jumps straight to the profile; otherwise show matching
    referrers (by client_id prefix or known Zoho/Customer name) to pick from.
    """
    tenant = get_current_tenant(request)
    q = (request.GET.get("q") or "").strip()
    result = None
    matches = []
    if q:
        # Exact, valid client_id with a footprint → go straight in.
        try:
            cid = validate_client_id(q)
        except InvalidClientId:
            cid = None
        if cid and profile.profile_exists(tenant, cid):
            return redirect("dashboard_referrer", client_id=cid)
        matches = profile.search_referrers(tenant, q)
        result = "empty" if not matches else "matches"
    ctx = {
        "q": q,
        "result": result,
        "matches": matches,
        "sync_health": _sync_health(tenant),
        "nav_active": "referrer",
    }
    return render(request, "dashboard/referrer_search.html", ctx)


@_staff_required
@require_GET
def referrer_profile(request, client_id: str):
    """User Referral Screen / "Referral Profile" (M9). Admin-only.

    Everything referred by one Zerodha client id: Zoho-enriched top band + KPI rings,
    per-partner link cards (real enabled partners only), a Clicks tab (GoRefer's own
    captured signals), and a Referred-People tab (Zoho READ).
    """
    tenant = get_current_tenant(request)
    try:
        cid = validate_client_id(client_id)
    except InvalidClientId:
        raise Http404("invalid client id")
    if not profile.profile_exists(tenant, cid):
        raise Http404("no referral profile for this client id")

    band = profile.top_band(tenant, cid)
    ctx = {
        "client_id": cid,
        "band": band,
        "ring_fractions": profile.ring_fractions(band["aggregates"]),
        "cards": profile.per_link_cards(tenant, cid),
        "clicks": profile.clicks_rows(tenant, cid),
        "people": profile.referred_people(tenant, cid),
        "config": profile.PROFILE_CONFIG,
        "sync_health": _sync_health(tenant),
        "nav_active": "referrer",
    }
    return render(request, "dashboard/referrer_profile.html", ctx)


@_staff_required
@require_http_methods(["GET", "POST"])
def preferences(request):
    """GET/POST /admin-panel/preferences — the per-tenant Preferences screen (Q-M-PREF).

    Admin-only, tenant-scoped. GET renders the current tenant config; POST persists
    each control to the USER/tenant tier of the cascade (ADR-022, ADR-034). LANDING_MODE
    is set HERE, not via a backend override; the ADR-032 `direct`-needs-live-/d/{slug}
    coupling is enforced at this screen.
    """
    tenant = get_current_tenant(request)
    notices: list[str] = []
    saved = False
    if request.method == "POST":
        notices = preferences_service.save_preferences(tenant, request.POST, user=request.user)
        saved = True
    ctx = preferences_service.current_view(tenant)
    ctx.update(
        {
            "sync_health": _sync_health(tenant),
            "nav_active": "preferences",
            "notices": notices,
            "saved": saved,
        }
    )
    return render(request, "dashboard/preferences.html", ctx)


@_staff_required
@require_http_methods(["POST"])
def preferences_partnership(request):
    """HTMX: add / activate / deactivate a partnership, then re-render the list.

    These rows drive /d/{slug} composition (ADR-031). After any change we re-render
    the partnerships partial (which includes the disclosure-status callout) so the
    screen reflects the new live-disclosure state immediately.
    """
    tenant = get_current_tenant(request)
    action = request.POST.get("action", "")
    error = None
    try:
        if action == "add":
            preferences_service.add_partnership(
                tenant,
                name=request.POST.get("name", ""),
                regulator=request.POST.get("regulator", ""),
                user=request.user,
            )
        elif action in {"activate", "deactivate"}:
            preferences_service.set_partnership_active(
                tenant,
                program_id=int(request.POST.get("program_id") or 0),
                active=(action == "activate"),
                user=request.user,
            )
        else:
            error = "Unknown action."
    except preferences_service.PreferencesError as exc:
        error = str(exc)
    except (TypeError, ValueError):
        error = "Invalid partnership request."
    ctx = preferences_service.current_view(tenant)
    ctx["partnership_error"] = error
    return render(request, "dashboard/partials/partnerships.html", ctx)


# Expose whether the dashboard is enabled (feature flag) to urls.
DASHBOARD_ENABLED = getattr(settings, "FEATURE_FLAGS", {}).get("ENABLE_ADMIN_DASHBOARD", True)
