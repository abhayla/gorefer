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
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.events.models import SyncHealth
from apps.referrals.models import Referral
from apps.tenants.resolve import get_current_tenant

from . import queries


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
    ctx = {
        "kpis": queries.kpis(tenant),
        "funnel": queries.funnel(tenant),
        "top_referrers": queries.top_referrers(tenant),
        "recent_leads": queries.recent_leads(tenant),
        "sync_health": _sync_health(tenant),
        "confirmed_clicks": queries.confirmed_clicks(tenant),
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
    }
    return render(request, "dashboard/journey.html", ctx)


# Expose whether the dashboard is enabled (feature flag) to urls.
DASHBOARD_ENABLED = getattr(settings, "FEATURE_FLAGS", {}).get("ENABLE_ADMIN_DASHBOARD", True)
