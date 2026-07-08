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
from django.views.decorators.http import require_GET

from apps.events.models import SyncHealth
from apps.referrals.models import Referral
from apps.referrals.validators import InvalidClientId, validate_client_id
from apps.tenants.resolve import get_current_tenant

from . import profile, queries


def _staff_required(view):
    """Gate a view behind login + is_staff (admin-only, Sprint 1)."""
    return login_required(
        user_passes_test(lambda u: u.is_staff, login_url="dashboard_login")(view),
        login_url="dashboard_login",
    )


class DashboardLoginView(LoginView):
    template_name = "dashboard/login.html"
    redirect_authenticated_user = True


def _sync_health(tenant):
    row = SyncHealth.objects.filter(tenant=tenant).order_by("-updated_at").first()
    if row is None:
        return {"zoho_state": "no_sync", "zoho_last_sync": None, "wati_state": "no_sync"}
    return {
        "zoho_state": row.zoho_state,
        "zoho_last_sync": row.last_successful_zoho_sync_at,
        "wati_state": row.wati_state,
    }


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


# Expose whether the dashboard is enabled (feature flag) to urls.
DASHBOARD_ENABLED = getattr(settings, "FEATURE_FLAGS", {}).get("ENABLE_ADMIN_DASHBOARD", True)
