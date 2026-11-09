"""S2-06 — daily referrals report + super-admin / AP-admin access.

Access tests are mutation-style: each one fails if the shared gate
(apps.tenants.access) is loosened back to a plain `is_staff` check.
"""
import csv
import datetime as dt
import io
import re
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import URLPattern, URLResolver, reverse

from apps.events.models import Event, VisitorPII
from apps.integrations.models import Conversion
from apps.referrals.models import (
    Customer,
    Lead,
    Partner,
    Prospect,
    Referral,
    ReferralIdentity,
    ReferralProgram,
)
from apps.tenants.access import AP_ADMIN, DENIED, SUPER_ADMIN, resolve_role
from apps.tenants.models import StaffTenantBinding, Tenant

IST = ZoneInfo("Asia/Kolkata")
D1, D2, D3 = dt.date(2026, 11, 1), dt.date(2026, 11, 2), dt.date(2026, 11, 3)
RANGE = {"from": "2026-11-01", "to": "2026-11-03"}
PW = "pw12345!"
UA = "Mozilla/5.0 (Linux; Android 14) Chrome/120"


def _at(day, hh, mm=0):
    return dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST)


def _ap(slug, client_id, first, last):
    t = Tenant.objects.create(name=f"AP {slug.upper()}", slug=slug)
    partner = Partner.objects.create(tenant=t, name="Zerodha", code=f"C{slug}")
    program = ReferralProgram.objects.create(tenant=t, partner=partner, name=f"p-{slug}")
    ident = ReferralIdentity.objects.create(tenant=t, partner=partner, program=program, client_id=client_id)
    ref = Referral.objects.create(tenant=t, referral_identity=ident, program=program, source="referral_link")
    Customer.objects.create(tenant=t, program=program, partner=partner, client_id=client_id,
                            first_name=first, last_name=last)
    return t, program, ref


def _event(t, ref, when, *, kind="click", bot=False, channel=None, vid=""):
    e = Event.objects.create(tenant=t, event_type=kind, referral=ref, is_bot=bot, user_agent=UA,
                             visitor_id=vid or None, metadata={"channel": channel} if channel else {})
    Event.objects.filter(pk=e.pk).update(timestamp=when)


def _lead(t, ref, when, name, mobile, zoho_id):
    p = Prospect.objects.create(tenant=t, mobile=mobile, name=name, city="Pune")
    lead = Lead.objects.create(tenant=t, referral=ref, prospect=p, zoho_lead_id=zoho_id)
    Lead.objects.filter(pk=lead.pk).update(created_at=when)


@pytest.fixture
def world(db):
    """Two APs over three IST days. Expected numbers are written next to each row."""
    a, prog_a, ref_a = _ap("a", "RA1001", "Ravi", "Kumar")
    b, prog_b, ref_b = _ap("b", "RB9001", "Bimal", "Shah")
    # AP A
    _event(a, ref_a, _at(D1, 10), channel="WhatsApp", vid="v1")          # D1 click
    VisitorPII.objects.create(tenant=a, visitor_id="v1", city="Nagpur")
    _event(a, ref_a, _at(D1, 23, 30))                                     # D1 click (late IST)
    _event(a, ref_a, _at(D2, 0, 30))                                      # D2 click — UTC date is D1
    _event(a, ref_a, _at(D1, 11), bot=True)                               # bot: excluded
    _event(a, ref_a, _at(D1, 11, 5), kind="landing_viewed")               # D1 landing
    _lead(a, ref_a, _at(D1, 12), "Asha Rao", "919800000001", "ZA1")      # D1 lead
    Conversion.objects.create(tenant=a, program=prog_a, referral=ref_a, referrer_client_id="RA1001",
                              zoho_lead_id="ZA1", opener_zerodha_account_id="OA1",
                              account_opened_at=_at(D3, 11), status="account_opened")  # D3 account
    Conversion.objects.create(tenant=a, program=prog_a, referral=ref_a, referrer_client_id="RA1001",
                              opener_zerodha_account_id="OA2", account_opened_at=_at(D2, 9),
                              is_reversed=True)                           # reversed: excluded
    Conversion.objects.create(tenant=a, program=prog_a, referral=None, referrer_client_id="RA2002",
                              opener_zerodha_account_id="OA3", opener_name="Off Person",
                              account_opened_at=_at(D2, 15))              # D2 off-platform, 0 clicks
    # AP B
    _event(b, ref_b, _at(D1, 9))
    _lead(b, ref_b, _at(D1, 9, 30), "Bina Secret", "919800000002", "ZB1")
    Conversion.objects.create(tenant=b, program=prog_b, referral=ref_b, referrer_client_id="RB9001",
                              opener_zerodha_account_id="OB1", account_opened_at=_at(D2, 10))
    return {"a": a, "b": b}


def _user(username, *, superuser=False, staff=True, tenant=None):
    u = get_user_model().objects.create_user(username=username, password=PW, is_staff=staff,
                                             is_superuser=superuser)
    if tenant is not None:
        StaffTenantBinding.objects.create(user=u, tenant=tenant)
    return u


def _client(user):
    c = Client()
    assert c.login(username=user.username, password=PW)
    return c


def _csv(resp):
    assert resp.status_code == 200 and resp["Content-Type"].startswith("text/csv")
    return list(csv.reader(io.StringIO(resp.content.decode())))


# --- the role resolver -----------------------------------------------------------

def test_resolver_every_role_state(world):
    inactive = Tenant.objects.create(name="Gone", slug="gone", is_active=False)
    assert resolve_role(_user("su", superuser=True)).kind == SUPER_ADMIN
    role = resolve_role(_user("apa", tenant=world["a"]))
    assert role.kind == AP_ADMIN and role.tenant == world["a"]
    # The binding wins even for a superuser (narrower scope).
    assert resolve_role(_user("su-bound", superuser=True, tenant=world["b"])).tenant == world["b"]
    assert resolve_role(_user("norole")).kind == DENIED
    assert resolve_role(_user("dead", superuser=True, tenant=inactive)).kind == DENIED
    assert resolve_role(_user("su-nostaff", superuser=True, staff=False)).kind == DENIED


# --- exact numbers ----------------------------------------------------------------

def test_ap_a_daily_numbers_by_ist_day(world):
    from apps.dashboard.daily import report

    r = report(world["a"], start=D1, end=D3, sort="period", direction="asc")
    got = [(x["period"], x["clicks"], x["landing"], x["leads"], x["accounts"], x["active_referrers"])
           for x in r["rows"]]
    assert got == [(D1, 2, 1, 1, 0, 1), (D2, 1, 0, 0, 1, 1), (D3, 0, 0, 0, 1, 0)]
    t = r["total"]
    assert (t["clicks"], t["landing"], t["leads"], t["accounts"], t["active_referrers"]) == (3, 1, 1, 2, 1)
    assert r["rows"][0]["lead_rate"] == 50.0 and r["rows"][2]["lead_rate"] is None


def test_week_and_month_grouping(world):
    from apps.dashboard.daily import report

    month = report(world["a"], start=D1, end=D3, group="month")["rows"]
    assert [(x["period"], x["clicks"], x["accounts"]) for x in month] == [(dt.date(2026, 11, 1), 3, 2)]
    weeks = report(world["a"], start=D1, end=D3, group="week", direction="asc")["rows"]
    # 1 Nov 2026 is a Sunday: week of Mon 26 Oct holds D1, week of Mon 2 Nov holds D2+D3.
    assert [(x["period"], x["clicks"]) for x in weeks] == [(dt.date(2026, 10, 26), 2),
                                                           (dt.date(2026, 11, 2), 1)]


def test_filters_min_leads_stage_channel(world):
    from apps.dashboard.daily import report

    assert [x["period"] for x in report(world["a"], start=D1, end=D3, min_leads=1)["rows"]] == [D1]
    assert {x["period"] for x in report(world["a"], start=D1, end=D3, stage="account")["rows"]} == {D2, D3}
    wa = report(world["a"], start=D1, end=D3, channel="WhatsApp")["total"]
    assert wa["clicks"] == 1
    off = report(world["a"], start=D1, end=D3, source="zoho_import")["total"]
    assert (off["clicks"], off["accounts"]) == (0, 1)
    by_name = report(world["a"], start=D1, end=D3, referrer="ravi")["total"]
    assert by_name["clicks"] == 3


def test_superuser_sees_both_aps_split(world):
    c = _client(_user("su", superuser=True))
    rows = _csv(c.get("/admin-panel/daily/", {**RANGE, "split": "1", "format": "csv", "dir": "asc"}))
    assert rows[0] == ["Period", "AP", "Clicks", "Landing opens", "Leads", "Accounts opened",
                       "Active referrers", "Lead rate %"]
    body = {(r[0], r[1]): r[2:6] for r in rows[1:-1]}
    assert body[("2026-11-01", "AP A")] == ["2", "1", "1", "0"]
    assert body[("2026-11-01", "AP B")] == ["1", "0", "1", "0"]
    assert body[("2026-11-02", "AP B")] == ["0", "0", "0", "1"]
    assert rows[-1][:7] == ["Total", "", "4", "1", "2", "3", "2"]
    html = c.get("/admin-panel/daily/", RANGE).content.decode()
    assert 'data-test="ap-filter"' in html


# --- scope: an AP admin never sees another AP -------------------------------------

def test_ap_admin_forged_ap_param_sees_only_own_ap(world):
    c = _client(_user("apa", tenant=world["a"]))
    forged = {**RANGE, "ap": str(world["b"].id), "split": "1"}
    page = c.get("/admin-panel/daily/", forged)
    assert page.status_code == 200
    html = page.content.decode()
    assert "AP B" not in html and 'data-test="ap-filter"' not in html and "Split by AP" not in html
    rows = _csv(c.get("/admin-panel/daily/", {**forged, "format": "csv"}))
    assert "AP" not in rows[0]
    assert rows[-1][:6] == ["Total", "3", "1", "1", "2", "1"]  # AP A only
    for day in ("2026-11-01", "2026-11-02"):
        for tab in ("people", "clicks"):
            detail = c.get(f"/admin-panel/daily/{day}/", {**forged, "tab": tab})
            assert detail.status_code == 200
            text = detail.content.decode() + c.get(
                f"/admin-panel/daily/{day}/", {**forged, "tab": tab, "format": "csv"}
            ).content.decode()
            assert "Bina" not in text and "RB9001" not in text and "AP B" not in text


def test_detail_person_on_every_day_they_acted(world):
    c = _client(_user("su", superuser=True))
    d1 = _csv(c.get("/admin-panel/daily/2026-11-01/", {"ap": str(world["a"].id), "format": "csv"}))
    assert d1[0] == ["Time", "AP", "Referrer ID", "Referrer name", "Name", "Mobile", "City", "Source",
                     "What happened", "Furthest stage", "Zoho status"]
    assert d1[1] == ["12:00", "AP A", "RA1001", "Ravi Kumar", "Asha Rao", "919800000001", "Pune",
                     "Referral link", "Lead", "Account opened", "new"]
    d3 = _csv(c.get("/admin-panel/daily/2026-11-03/", {"ap": str(world["a"].id), "format": "csv"}))
    assert [r[4:6] + r[8:9] for r in d3[1:]] == [["Asha Rao", "919800000001", "Account opened"]]
    d2 = _csv(c.get("/admin-panel/daily/2026-11-02/", {"ap": str(world["a"].id), "format": "csv"}))
    assert [(r[2], r[4], r[7]) for r in d2[1:]] == [("RA2002", "Off Person", "Off-platform")]
    clicks = _csv(c.get("/admin-panel/daily/2026-11-01/",
                        {"ap": str(world["a"].id), "tab": "clicks", "format": "csv"}))
    assert [(r[0], r[4], r[5], r[6]) for r in clicks[1:]] == [
        ("10:00", "WhatsApp", "Nagpur", "Mobile"), ("23:30", "Direct", "", "Mobile")]
    # Pre-RDR-6 day: Asha's lead has no lead event with a visitor id -> all clicks + the note.
    html = c.get("/admin-panel/daily/2026-11-01/",
                 {"ap": str(world["a"].id), "tab": "clicks"}).content.decode()
    assert 'data-test="clicks-note"' in html and "Clicks with no form" not in html


def test_lead_submit_stamps_visitor_and_clicks_tab_excludes_it(db, django_capture_on_commit_callbacks):
    """RDR-6 on the real submit path: gr_vid -> lead event visitor_id -> click excluded."""
    import json

    from apps.dashboard.daily import day_detail
    from apps.referrals.views import VISITOR_COOKIE

    t, _prog, ref = _ap("pifs", "RJ4521", "Ravi", "Kumar")
    today = dt.datetime.now(IST).date()
    _event(t, ref, dt.datetime.now(IST) - dt.timedelta(seconds=20), vid="vid-formed")
    _event(t, ref, dt.datetime.now(IST) - dt.timedelta(seconds=10), vid="vid-browsing")
    c = Client()
    c.cookies[VISITOR_COOKIE] = "vid-formed"
    with django_capture_on_commit_callbacks(execute=True):
        resp = c.post("/api/leads/", data=json.dumps({
            "client_id": "RJ4521", "name": "Rahul", "mobile": "9876543210", "consent": True}),
            content_type="application/json")
    assert resp.status_code == 201, resp.content
    ev = Event.objects.get(event_type="lead_captured")
    assert ev.visitor_id == "vid-formed" and "vid-formed" not in json.dumps(ev.metadata)
    if today == dt.datetime.now(IST).date():  # guard the IST-midnight edge
        d = day_detail(t, day=today)
        assert d["clicks_exact"] is True
        assert len(d["clicks"]) == 1  # only vid-browsing: the formed visitor is excluded
        su = _client(_user("su", superuser=True))
        html = su.get(f"/admin-panel/daily/{today}/", {"tab": "clicks"}).content.decode()
        assert "Clicks with no form (1)" in html and 'data-test="clicks-note"' not in html


def test_lead_without_cookie_leaves_visitor_null(db, django_capture_on_commit_callbacks):
    from apps.referrals.lead_service import capture_lead

    t, _prog, ref = _ap("pifs", "RJ4521", "Ravi", "Kumar")
    with django_capture_on_commit_callbacks(execute=True):
        capture_lead(tenant=t, referral=ref, name="N", mobile="9876543210", email="", city="",
                     consent=True)
    assert Event.objects.get(event_type="lead_captured").visitor_id is None


def test_detail_stage_filter_honours_every_offered_stage(world):
    from apps.dashboard.daily import STAGES, day_detail

    a = world["a"]
    got = {s: (len(day_detail(a, day=D1, stage=s)["people"]), len(day_detail(a, day=D1, stage=s)["clicks"]))
           for s, _label in STAGES}
    # D1: Asha (lead, later account) + 2 clicks. "account" keeps Asha (her account is real).
    assert got == {"clicked": (1, 2), "landing": (1, 0), "lead": (1, 0), "account": (1, 0)}


def test_channel_list_covers_every_configured_channel():
    from apps.dashboard.daily import CHANNELS
    from gorefer.flags import SHARE_CHANNEL_LABELS

    assert [v for v, _ in CHANNELS] == list(SHARE_CHANNEL_LABELS.values()) + ["none"]


def test_channel_filter_for_leads_uses_in_period_clicks_only(world):
    from apps.dashboard.daily import report

    # AP A's only WhatsApp click is on D1: a D2-only range must not tag D2's account WhatsApp.
    assert report(world["a"], start=D2, end=D3, channel="WhatsApp")["total"]["accounts"] == 0
    assert report(world["a"], start=D1, end=D1, channel="WhatsApp")["total"]["leads"] == 1


# --- every pre-existing staff surface is super-admin only -------------------------

def _sample(pattern):
    out = re.sub(r"<int:[^>]+>", "1", pattern)
    return re.sub(r"<(?:str:)?[^>]+>", "AB1234", out)


#: Ninja routers that are deliberately NOT staff-authed (public capture, signed webhooks,
#: key-authed server-to-server). Any other router must carry StaffSessionAuth.
_PUBLIC_API_PREFIXES = {"", "/click", "/leads", "/share", "/records-tokens", "/zoho", "/wati",
                        "/callback-request"}
_REPORT_NAMES = {"dashboard_login", "dashboard_logout", "dashboard_daily", "dashboard_daily_detail"}


@pytest.fixture
def all_flags_routed(settings):
    """Mount every flag-gated admin route (verification pages need ENABLE_CUSTOMER_LOGIN)."""
    import importlib

    from django.urls import clear_url_caches

    import apps.dashboard.urls
    import gorefer.urls

    def remount():
        importlib.reload(apps.dashboard.urls)
        importlib.reload(gorefer.urls)
        clear_url_caches()

    old = settings.FEATURE_FLAGS
    settings.FEATURE_FLAGS = {**old, "ENABLE_CUSTOMER_LOGIN": True, "ENABLE_ADMIN_DASHBOARD": True}
    remount()
    yield
    settings.FEATURE_FLAGS = old
    remount()


def _page_urls():
    """Every routed URL under /admin-panel/ from the ROOT urlconf (so a new page is caught)."""
    from django.urls import get_resolver

    def walk(patterns, prefix):
        for p in patterns:
            if isinstance(p, URLResolver):
                yield from walk(p.url_patterns, prefix + str(p.pattern))
            elif isinstance(p, URLPattern):
                full = prefix + str(p.pattern)
                if full.startswith("admin-panel/") and p.name not in _REPORT_NAMES:
                    yield "/" + _sample(full)

    urls = sorted(set(walk(get_resolver().url_patterns, "")))
    # Django admin: one choke point (admin.site.has_permission) — index + our model page.
    return urls + ["/django-admin/", "/django-admin/tenants/stafftenantbinding/"]


def _api_urls():
    from api.router import api
    from apps.common.api_auth import StaffSessionAuth

    out, unauthed = [], []
    for prefix, router in api._routers:
        staff = isinstance(router.auth, StaffSessionAuth)
        if prefix not in _PUBLIC_API_PREFIXES and not staff:
            unauthed.append(prefix)
        for path, pv in router.path_operations.items():
            for op in pv.operations:
                if staff or any(isinstance(a, StaffSessionAuth) for a in (op.auth_callbacks or [])):
                    out.append((op.methods[0], "/api" + prefix + re.sub(r"\{[^}]+\}", "1", path)))
    assert unauthed == [], f"staff-looking Ninja router(s) with no StaffSessionAuth: {unauthed}"
    return out


def test_url_lists_are_not_empty(all_flags_routed):
    urls = _page_urls()
    assert len(urls) >= 15
    assert "/admin-panel/verifications/" in urls and "/admin-panel/campaigns/" in urls
    assert {u for _m, u in _api_urls()} >= {"/api/analytics/funnel", "/api/followups/rules"}


def _refused(c, method, url):
    resp = getattr(c, method.lower())(url)
    if url.startswith("/api/"):
        return resp.status_code in (401, 403)
    return resp.status_code in (302, 403) and (
        resp.status_code == 403 or "login" in resp.headers.get("Location", "")
    )


def test_ap_admin_and_no_role_staff_refused_on_every_existing_surface(world, all_flags_routed):
    inactive = Tenant.objects.create(name="Gone", slug="gone", is_active=False)
    users = [
        _user("apa", tenant=world["a"]),
        _user("su-bound", superuser=True, tenant=world["b"]),
        _user("norole"),
        _user("dead", superuser=True, tenant=inactive),
    ]
    targets = [("GET", u) for u in _page_urls()] + _api_urls()
    leaks = []
    for user in users:
        c = _client(user)
        for method, url in targets:
            if not _refused(c, method, url):
                leaks.append((user.username, method, url))
    assert leaks == []


def test_superuser_still_reaches_existing_pages(world):
    c = _client(_user("su", superuser=True))
    assert c.get("/admin-panel/explorer/").status_code == 200
    assert c.get("/api/analytics/sync-health").status_code == 200
    assert c.get("/django-admin/").status_code == 200


def test_no_role_staff_refused_on_report(world):
    c = _client(_user("norole"))
    assert c.get("/admin-panel/daily/").status_code == 302
    assert c.get("/admin-panel/daily/2026-11-01/", {"format": "csv"}).status_code == 302


def test_ap_admin_login_lands_on_daily_report(world):
    _user("apa", tenant=world["a"])
    resp = Client().post(reverse("dashboard_login"), {"username": "apa", "password": PW})
    assert resp.status_code == 302 and resp.headers["Location"] == reverse("dashboard_daily")
    _user("su", superuser=True)
    resp = Client().post(reverse("dashboard_login"), {"username": "su", "password": PW})
    assert resp.headers["Location"] == reverse("dashboard")


def test_behaviour_literals_resolve_from_the_cascade(world):
    """Rail E-6 spot test: default preset, preset list and page size are cascade keys."""
    from apps.config.cascade import set_tenant
    from apps.dashboard import daily

    a = world["a"]
    assert daily.default_preset(a) == "last7" and daily.page_size(a) == 100
    assert daily.presets(a) == ["today", "last7", "last30", "this_month"]
    set_tenant("daily_report_default_preset", "today", tenant_id=a.id)
    set_tenant("daily_report_page_size", 1, tenant_id=a.id)
    set_tenant("daily_report_presets", ["today", "last30"], tenant_id=a.id)
    assert daily.default_preset(a) == "today" and daily.page_size(a) == 1
    assert daily.presets(a) == ["today", "last30"]
    c = _client(_user("apa", tenant=a))
    html = c.get("/admin-panel/daily/", RANGE).content.decode()
    assert html.count('data-test="daily-row"') == 1 and "Page 1 of 3" in html
