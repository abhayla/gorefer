"""GET /admin-panel/report — the role-based daily report (owner-approved mock-up 2026-11-28).

Same address every day. "View as" picks one of the roles the signed-in person holds
(validated server-side against their grants, remembered in the session); the period
defaults per role and can be any earlier day. While "Today" is shown, the page refreshes
its content every minute (HTMX, `?partial=1`).
"""

from __future__ import annotations

from django.shortcuts import render

from apps.tenants.access import ADMIN, MANAGER, OWNER, any_role_required, resolve_grants
from apps.tenants.models import Tenant

from . import role_report as rr

SESSION_VIEW_AS = "report_view_as"


@any_role_required
def report(request):
    grants = resolve_grants(request.user)
    choices = rr.role_choices(grants)
    keys = [c["key"] for c in choices]
    wanted = request.GET.get("as") or request.session.get(SESSION_VIEW_AS) or keys[0]
    role = wanted if wanted in keys else keys[0]
    request.session[SESSION_VIEW_AS] = role
    grant = next(c["grant"] for c in choices if c["key"] == role)

    if role == MANAGER:
        tenants = [grant.tenant]
    else:
        tenants = list(Tenant.objects.filter(is_active=True).order_by("name"))
    tid = tenants[0].id if role == MANAGER else None
    range_key = request.GET.get("range") or rr.default_range(role, tid)
    period = rr.make_period(range_key if range_key in rr.RANGES else "yesterday", request.GET.get("date", ""))

    if role == OWNER:
        data, title, scope = rr.build_owner(tenants, period), "Platform and growth", "All businesses"
    elif role == ADMIN:
        data, title, scope = rr.build_admin(tenants, period), "Operations", "All businesses"
    else:
        data = rr.build_manager(grant.tenant, period)
        title, scope = f"{grant.tenant.name} today", grant.tenant.name

    ctx = {
        "role": role,
        "roles": choices,
        "title": title,
        "scope": scope,
        "data": data,
        "period": period,
        "ranges": [(k, rr.RANGE_LABELS[k]) for k in rr.RANGES],
        "is_live": period.key == "today",
        "links_filter": request.GET.get("links", "opening"),
        "search": (request.GET.get("q") or "").strip().upper(),
        "nav_active": "report",
    }
    if ctx["search"] and role == MANAGER:
        data["ids"] = [r for r in data["ids"] if ctx["search"] in r["id"]]
    template = "dashboard/report_body.html" if request.GET.get("partial") == "1" else "dashboard/report.html"
    return render(request, template, ctx)
