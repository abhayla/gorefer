"""The role-based daily report /admin-panel/report (owner-approved mock-up 2026-11-28).

Pins: each role gets its own format; "View as" can only pick a role the person holds;
a business manager never sees another business (IDs, accounts, messages); WhatsApp
figures belong only to the business that owns the Zoho connection; each role opens on
its own default period; the live view refreshes; every threshold is a cascade key.
"""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from apps.dashboard import role_report as rr
from apps.integrations.models import Conversion
from apps.referrals.models import ReferralProgram
from apps.tenants.models import StaffAccess, Tenant
from apps.tenants.resolve import get_bootstrap_tenant

PW = "pw-for-tests-only"
HUMAN = {"HTTP_USER_AGENT": "Mozilla/5.0 (Android)", "REMOTE_ADDR": "203.0.113.9"}


@pytest.fixture
def world(db, django_capture_on_commit_callbacks):
    call_command("seed_program")
    pifs = get_bootstrap_tenant()
    other = Tenant.objects.create(name="Other AP", slug="other")
    with django_capture_on_commit_callbacks(execute=True):
        Client().get("/zerodha/r/AB1234", **HUMAN)  # a PIFS referrer's first tap, today
    program = ReferralProgram.objects.get(tenant=pifs)
    now = timezone.now()
    Conversion.objects.create(tenant=pifs, program=program, zoho_lead_id="L1",
                              referrer_client_id="AB1234", account_opened_at=now)
    Conversion.objects.create(tenant=other, program=program, zoho_lead_id="L2",
                              referrer_client_id="OT9999", account_opened_at=now)
    return {"pifs": pifs, "other": other}


def _person(email, **roles):
    get_user_model().objects.create_user(username=email, email=email, password=PW, is_staff=True)
    StaffAccess.objects.create(email=email, **roles)
    c = Client()
    assert c.login(username=email, password=PW)
    return c


def test_each_role_gets_its_own_format(world):
    c = _person("all@example.com", is_owner=True, is_admin=True, manager_tenant=world["pifs"])
    owner = c.get("/admin-panel/report?as=owner").content.decode()
    admin = c.get("/admin-panel/report?as=admin").content.decode()
    mgr = c.get("/admin-panel/report?as=manager&range=today").content.decode()
    assert "Platform and growth" in owner and "Where accounts came from" in owner
    assert "Operations" in admin and "WhatsApp messages by business" in admin
    assert "today" in mgr and "Every Kite ID" in mgr
    assert "Every Kite ID" not in owner and "Every Kite ID" not in admin
    assert "Where accounts came from" not in mgr and "Businesses against their usual" not in mgr


def test_manager_never_sees_another_business(world):
    c = _person("m@example.com", manager_tenant=world["pifs"])
    body = c.get("/admin-panel/report?range=today").content.decode()
    assert "AB1234" in body
    assert "OT9999" not in body and "Other AP" not in body
    # asking for a wider role it does not hold falls back to its own
    wider = c.get("/admin-panel/report?as=owner&range=today").content.decode()
    assert "Platform and growth" not in wider and "Other AP" not in wider


def test_owner_sees_every_business(world):
    c = _person("o@example.com", is_owner=True)
    body = c.get("/admin-panel/report").content.decode()
    assert "PIFS" in body or world["pifs"].name in body
    assert "Other AP" in body


def test_whatsapp_figures_belong_only_to_the_zoho_business(world, monkeypatch):
    calls = []
    monkeypatch.setattr(rr, "zoho_queue_summary", lambda tenant, day: calls.append(tenant.slug) or {
        "referral_total": 40, "delivered": 31, "not_delivered": 9, "rate_pct": 77.5, "capped": 2,
        "invalid": 0, "failed": 6, "pending": 1, "other_total": 0, "other_breakdown": {}, "truncated": False})
    period = rr.make_period("yesterday")
    data = rr.build_admin([world["pifs"], world["other"]], period)
    by_name = {m["name"]: m["zoho"] for m in data["messages"]}
    assert by_name[world["pifs"].name]["failed"] == 6
    assert by_name["Other AP"] is None
    assert calls == [world["pifs"].slug]
    assert any("6 messages failed" in t["what"] for t in data["todos"])


def test_default_period_per_role_and_live_refresh(world):
    c = _person("all@example.com", is_owner=True, is_admin=True, manager_tenant=world["pifs"])
    assert "This month" in c.get("/admin-panel/report?as=owner").content.decode()
    mgr = c.get("/admin-panel/report?as=manager").content.decode()
    assert "Yesterday," in mgr and 'hx-trigger="every 60s"' not in mgr
    live = c.get("/admin-panel/report?as=manager&range=today")
    assert 'hx-trigger="every 60s"' in live.content.decode()
    part = c.get("/admin-panel/report?as=manager&range=today&partial=1").content.decode()
    assert part.lstrip().startswith("<div") and "<html" not in part and 'id="report-body"' in part


def test_view_as_is_remembered(world):
    c = _person("all@example.com", is_owner=True, is_admin=True)
    c.get("/admin-panel/report?as=admin")
    assert "Operations" in c.get("/admin-panel/report").content.decode()


def test_manager_to_do_thanks_and_welcomes(world):
    period = rr.make_period("today")
    data = rr.build_manager(world["pifs"], period)
    whats = [t["what"] for t in data["todos"]]
    assert "Thank AB1234" in whats and "Welcome AB1234" in whats
    row = next(r for r in data["ids"] if r["id"] == "AB1234")
    assert (row["accounts"], row["taps"]) == (1, 1)


def test_no_role_is_refused(world):
    get_user_model().objects.create_user(username="x", email="x@example.com", password=PW, is_staff=True)
    c = Client()
    c.login(username="x", password=PW)
    assert c.get("/admin-panel/report").status_code == 302


def test_periods():
    today = rr.ist_today()
    assert rr.make_period("7d").days == 7 and rr.make_period("7d").end == today - timedelta(days=1)
    assert rr.make_period("mtd").start == today.replace(day=1)
    assert rr.make_period("yesterday", picked=(today - timedelta(days=3)).isoformat()).days == 1
    assert rr.make_period("today", picked="not-a-date").key == "today"


def test_thresholds_and_defaults_are_cascade_keys(world):
    """Rail E-6 spot test: report thresholds and default periods resolve from the cascade."""
    from apps.config.cascade import set_tenant

    tid = world["pifs"].id
    assert rr.report_setting("report_todo_max", tid) == 5
    set_tenant("report_todo_max", 1, tenant_id=tid)
    set_tenant("report_default_range_manager", "7d", tenant_id=tid)
    assert rr.report_setting("report_todo_max", tid) == 1
    assert rr.default_range("manager", tid) == "7d"
    assert len(rr.build_manager(world["pifs"], rr.make_period("today"))["todos"]) == 1
