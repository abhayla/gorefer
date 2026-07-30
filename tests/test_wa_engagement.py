"""T-032 — daily WA engagement report job.

Fixture-driven: the two inbound `getMessages` samples below are the REAL captured
payload shapes quoted verbatim in T-031's merged report (reports/wa-engagement/2026-07-30.md,
§(b) "Parser-reality note") — `text="Refer & Earn"` and `text="Talk to advisor"`, both with
`buttonReply: null, interactive: null` (a tapped quick-reply button arrives as plain text in
this tenant, not a structured object).
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.config.cascade import set_tenant
from apps.events import vocab
from apps.events.models import Event
from apps.followups.models import FollowupRule, ScheduledFollowup
from apps.integrations.wati import engagement
from apps.tenants.resolve import get_bootstrap_tenant

# --- Real captured payload samples (T-031 Appendix, quoted verbatim) ------------

REPLIED_MESSAGES_1 = [
    {"eventType": "message", "owner": False, "type": "text", "text": "Refer & Earn",
     "buttonReply": None, "interactive": None, "created": "2026-07-29T10:00:00Z"},
]
REPLIED_MESSAGES_2 = [
    {"eventType": "message", "owner": False, "type": "text", "text": "Talk to advisor",
     "buttonReply": None, "interactive": None, "created": "2026-07-29T11:00:00Z"},
    {"eventType": "message", "owner": False, "type": "text", "text": "RJ4521",
     "buttonReply": None, "interactive": None, "created": "2026-07-29T11:05:00Z"},
    {"eventType": "message", "owner": False, "type": "text", "text": "hi there",
     "buttonReply": None, "interactive": None, "created": "2026-07-29T11:06:00Z"},
]
TEMPLATES_FIXTURE = [
    {"name": "gorefer_zerodha_hin_2026_07_10_v2", "category": "MARKETING",
     "buttons": [{"type": "quick_reply", "parameter": {"text": "Refer & Earn"}}]},
    {"name": "gorefer_zerodha_reopen_en", "category": "UTILITY",
     "buttons": [{"type": "quick_reply", "parameter": {"text": "Talk to advisor"}}]},
]
BROADCASTS_FIXTURE = [
    {"id": "b1", "template_name": "gorefer_zerodha_hin_2026_07_10_v2", "category": "MARKETING",
     "total_sent": 1, "total_delivered": 1, "total_read": 1, "total_replied": 1, "total_failed": 0,
     "whatsapp_number": "919876500001", "failed_meta_codes": []},
    {"id": "b2", "template_name": "gorefer_zerodha_reopen_en", "category": "UTILITY",
     "total_sent": 0, "total_delivered": 1, "total_read": 1, "total_replied": 1, "total_failed": 0,
     "whatsapp_number": "919876500002", "failed_meta_codes": []},
    {"id": "b3", "template_name": "gorefer_zerodha_eng_leads_2026_07_10", "category": "MARKETING",
     "total_sent": 0, "total_delivered": 0, "total_read": 0, "total_replied": 0, "total_failed": 1,
     "whatsapp_number": "919876500003", "failed_meta_codes": [131049]},
]


def _pull():
    return engagement.EngagementPull(
        degraded=False,
        broadcasts=BROADCASTS_FIXTURE,
        templates=TEMPLATES_FIXTURE,
        responder_messages={
            "919876500001": REPLIED_MESSAGES_1,
            "919876500002": REPLIED_MESSAGES_2,
        },
    )


# --- Config defaults -------------------------------------------------------------

@pytest.fixture
def tenant(db):
    call_command("seed_program")
    return get_bootstrap_tenant()


def test_config_defaults(tenant):
    assert engagement.report_enabled(tenant.id) is False
    assert engagement.report_hour_ist(tenant.id) == 21
    assert engagement.lookback_days(tenant.id) == 7
    assert engagement.report_dir(tenant.id) == "var/reports/wa-engagement"


def test_config_overridable_via_cascade(tenant):
    set_tenant(engagement.REPORT_ENABLED_KEY, True, tenant_id=tenant.id)
    set_tenant(engagement.LOOKBACK_DAYS_KEY, 3, tenant_id=tenant.id)
    assert engagement.report_enabled(tenant.id) is True
    assert engagement.lookback_days(tenant.id) == 3


# --- Schedule registration --------------------------------------------------------

def test_wa_engagement_schedule_registered():
    from apps.events.management.commands.setup_schedules import SCHEDULES

    assert SCHEDULES["wa_engagement_report_daily"] == (
        "apps.integrations.wati.engagement.run_scheduled_report", 60,
    )


@pytest.mark.django_db
def test_setup_schedules_creates_the_row():
    from django_q.models import Schedule

    call_command("setup_schedules")
    assert Schedule.objects.filter(name="wa_engagement_report_daily").exists()


@pytest.mark.django_db
def test_run_scheduled_report_skips_outside_configured_hour(tenant, monkeypatch, tmp_path):
    set_tenant(engagement.REPORT_ENABLED_KEY, True, tenant_id=tenant.id)
    set_tenant(engagement.REPORT_DIR_KEY, str(tmp_path), tenant_id=tenant.id)
    set_tenant(engagement.REPORT_HOUR_IST_KEY, 21, tenant_id=tenant.id)
    monkeypatch.delenv("NOTIFIER_URL", raising=False)

    # 10:00 UTC = 15:30 IST — not the configured hour 21.
    off_hour = datetime(2026, 7, 30, 10, 0, tzinfo=dt_timezone.utc)
    result = engagement.run_scheduled_report(now_utc=off_hour)
    assert result[tenant.slug]["skipped"] is True
    assert "not the configured hour" in result[tenant.slug]["reason"]


@pytest.mark.django_db
def test_run_scheduled_report_runs_during_configured_hour(tenant, monkeypatch, tmp_path):
    set_tenant(engagement.REPORT_ENABLED_KEY, True, tenant_id=tenant.id)
    set_tenant(engagement.REPORT_DIR_KEY, str(tmp_path), tenant_id=tenant.id)
    set_tenant(engagement.REPORT_HOUR_IST_KEY, 21, tenant_id=tenant.id)
    monkeypatch.delenv("WATI_API_ENDPOINT", raising=False)
    monkeypatch.delenv("WATI_BASE_URL", raising=False)
    monkeypatch.delenv("WATI_API_TOKEN", raising=False)
    monkeypatch.delenv("NOTIFIER_URL", raising=False)

    # 15:30 UTC = 21:00 IST — the configured hour.
    on_hour = datetime(2026, 7, 30, 15, 30, tzinfo=dt_timezone.utc)
    result = engagement.run_scheduled_report(now_utc=on_hour)
    assert result[tenant.slug]["skipped"] is False


# --- Metric computation (fixture-driven) -----------------------------------------

def test_sends_by_category():
    by_cat = engagement._sends_by_category(BROADCASTS_FIXTURE)
    assert by_cat["MARKETING"]["sends"] == 2
    assert by_cat["MARKETING"]["failed"] == 1
    assert by_cat["UTILITY"]["delivered"] == 1


def test_failure_codes():
    codes = engagement._failure_codes(BROADCASTS_FIXTURE)
    assert codes == {131049: 1}


def test_responder_breakdown_classifies_real_samples():
    result = engagement._responder_breakdown(_pull())
    assert result["responders"] == 2
    assert result["modes"]["quick_reply_button"] == 2  # "Refer & Earn" + "Talk to advisor"
    assert result["modes"]["keyword_trigger"] == 1     # "RJ4521"
    assert result["modes"]["free_text"] == 1            # "hi there"


def test_classify_response_mode_case_insensitive():
    labels = {"refer & earn"}
    assert engagement.classify_response_mode("Refer & Earn", labels) == "quick_reply_button"
    assert engagement.classify_response_mode("RJ4521", set()) == "keyword_trigger"
    assert engagement.classify_response_mode("hello there", set()) == "free_text"


@pytest.mark.django_db
def test_goref_side_events_counted_in_window(tenant):
    now = timezone.now()
    Event.objects.create(tenant=tenant, event_type=vocab.CLICK, source="test", timestamp=now)
    Event.objects.create(tenant=tenant, event_type=vocab.SHARE_INTENT, source="test", timestamp=now)
    counts = engagement._goref_side_events(tenant, now - timedelta(hours=1), now + timedelta(hours=1))
    assert counts == {"share_intent": 1, "click": 1, "share_clicked": 0}


@pytest.mark.django_db
def test_session_windows_opened_counts_distinct_opens(tenant):
    rule = FollowupRule.objects.create(
        tenant=tenant, step_key="nudge", offset_minutes=15, channel=FollowupRule.CHANNEL_SESSION,
        body_en="hi", body_hi="", enabled=True, only_if_window_open=True, stop_on_reply=True, order=100,
    )
    now = timezone.now()
    ScheduledFollowup.objects.create(
        tenant=tenant, rule=rule, mobile="919876500009", fire_at=now, window_opened_at=now,
        dedupe_key="k1",
    )
    counts = engagement._session_windows_opened(tenant, now - timedelta(hours=1), now + timedelta(hours=1))
    assert counts["distinct_windows_opened"] == 1


@pytest.mark.django_db
def test_compute_report_shape(tenant, monkeypatch):
    monkeypatch.setattr(engagement, "get_engagement_reader", lambda: _FakeReader())
    now = timezone.now()
    report = engagement.compute_report(tenant, now_utc=now, lookback=7)
    assert report["degraded"] is False
    assert "trailing_24h" in report
    assert "trailing_7d" in report
    assert report["trailing_24h"]["total_sends"] == 3


class _FakeReader:
    kind = "fake"

    def pull(self, *, window_start, window_end):
        return _pull()


# --- Markdown + digest ------------------------------------------------------------

@pytest.mark.django_db
def test_render_markdown_and_digest_shape(tenant, monkeypatch):
    monkeypatch.setattr(engagement, "get_engagement_reader", lambda: _FakeReader())
    now = timezone.now()
    report = engagement.compute_report(tenant, now_utc=now, lookback=7)
    md = engagement.render_markdown(report, lookback=7)
    assert "WhatsApp Engagement Report" in md
    assert "MARKETING" in md

    digest = engagement.build_digest(report, lookback=7, report_path="/tmp/x.md")
    assert digest["project"] == "gorefer"
    assert digest["dedupeKey"].startswith("wa-engagement-")
    assert len(digest["body"]) < 900
    assert digest["title"]


def test_degraded_markdown_says_no_live_data():
    report = {
        "generated_at": "2026-07-30T12:00:00+00:00", "reader_kind": "log_only", "tenant": "pifs",
        "degraded": True,
        "trailing_24h": _empty_metrics(),
        "trailing_7d": _empty_metrics(),
    }
    md = engagement.render_markdown(report, lookback=7)
    assert "NO LIVE DATA" in md


def _empty_metrics():
    return {
        "window_start": "2026-07-29T00:00:00+00:00", "window_end": "2026-07-30T00:00:00+00:00",
        "degraded": True, "by_category": {}, "by_template": {}, "failure_codes": {}, "total_sends": 0,
        "responders": {
            "responders": 0, "modes": {"quick_reply_button": 0, "keyword_trigger": 0, "free_text": 0},
        },
        "goref_events": {"share_intent": 0, "click": 0, "share_clicked": 0},
        "session_windows": {"distinct_windows_opened": 0},
    }


# --- No-op / degraded modes -------------------------------------------------------

@pytest.mark.django_db
def test_run_report_for_tenant_is_noop_when_disabled(tenant):
    result = engagement.run_report_for_tenant(tenant)
    assert result["skipped"] is True


@pytest.mark.django_db
def test_run_report_for_tenant_degrades_gracefully_without_creds(tenant, monkeypatch, tmp_path):
    monkeypatch.delenv("WATI_API_ENDPOINT", raising=False)
    monkeypatch.delenv("WATI_BASE_URL", raising=False)
    monkeypatch.delenv("WATI_API_TOKEN", raising=False)
    monkeypatch.delenv("NOTIFIER_URL", raising=False)
    set_tenant(engagement.REPORT_ENABLED_KEY, True, tenant_id=tenant.id)
    set_tenant(engagement.REPORT_DIR_KEY, str(tmp_path), tenant_id=tenant.id)

    result = engagement.run_report_for_tenant(tenant)

    assert result["skipped"] is False
    assert result["report"]["degraded"] is True
    with open(result["report_path"], encoding="utf-8") as fh:
        content = fh.read()
    assert "NO LIVE DATA" in content
    # Digest send fails cleanly (no NOTIFIER_URL) — report job still succeeds.
    assert result["digest_result"]["ok"] is False


def test_get_engagement_reader_is_log_only_without_creds(monkeypatch):
    monkeypatch.delenv("WATI_API_ENDPOINT", raising=False)
    monkeypatch.delenv("WATI_BASE_URL", raising=False)
    monkeypatch.delenv("WATI_API_TOKEN", raising=False)
    reader = engagement.get_engagement_reader()
    assert reader.kind == "log_only"
    pull = reader.pull(window_start=timezone.now() - timedelta(days=1), window_end=timezone.now())
    assert pull.degraded is True
    assert pull.broadcasts == []


def test_get_engagement_reader_is_live_with_creds(monkeypatch):
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/105355")
    monkeypatch.setenv("WATI_API_TOKEN", "test-token")
    reader = engagement.get_engagement_reader()
    assert reader.kind == "live"


# --- FIX 1: v3 host has NO tenant path, v1 keeps it (T-033) -----------------------

def test_live_reader_derives_v3_base_without_tenant_path(monkeypatch):
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/105355")
    monkeypatch.setenv("WATI_API_TOKEN", "test-token")
    reader = engagement.LiveEngagementReader()
    assert reader.base_url == "https://live-mt-server.wati.io/105355"
    assert reader.v3_base_url == "https://live-mt-server.wati.io"


def test_live_reader_pull_calls_v3_broadcasts_on_bare_host(monkeypatch):
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/105355")
    monkeypatch.setenv("WATI_API_TOKEN", "test-token")
    urls_called = []

    def fake_transport(method, url, headers, body):
        urls_called.append(url)
        if "/getMessageTemplates" in url:
            return 200, json.dumps({"messages": []})
        if "/api/ext/v3/broadcasts" in url:
            return 200, json.dumps({"items": []})
        return 200, json.dumps({})

    reader = engagement.LiveEngagementReader(transport=fake_transport)
    now = timezone.now()
    reader.pull(window_start=now - timedelta(days=1), window_end=now)

    v3_calls = [u for u in urls_called if "/api/ext/v3/broadcasts" in u]
    assert v3_calls, "expected a v3 broadcasts call"
    assert all(u.startswith("https://live-mt-server.wati.io/api/ext/v3/broadcasts") for u in v3_calls)
    v1_calls = [u for u in urls_called if "/getMessageTemplates" in u]
    assert all(u.startswith("https://live-mt-server.wati.io/105355/api/v1/") for u in v1_calls)


# --- FIX 2: a non-200 pull marks degraded=True, never a silent zero (T-033) -------

def test_live_reader_404_on_broadcasts_marks_degraded(monkeypatch):
    monkeypatch.setenv("WATI_API_ENDPOINT", "https://live-mt-server.wati.io/105355")
    monkeypatch.setenv("WATI_API_TOKEN", "test-token")

    def fake_transport(method, url, headers, body):
        if "/getMessageTemplates" in url:
            return 200, json.dumps({"messages": []})
        if "/api/ext/v3/broadcasts" in url:
            return 404, ""
        return 200, json.dumps({})

    reader = engagement.LiveEngagementReader(transport=fake_transport)
    now = timezone.now()
    pull = reader.pull(window_start=now - timedelta(days=1), window_end=now)

    assert pull.degraded is True
    assert pull.broadcasts == []


@pytest.mark.django_db
def test_degraded_pull_yields_no_live_data_digest_title(tenant, monkeypatch, tmp_path):
    class _Degraded404Reader:
        kind = "live"

        def pull(self, *, window_start, window_end):
            return engagement.EngagementPull(degraded=True)

    monkeypatch.setattr(engagement, "get_engagement_reader", lambda: _Degraded404Reader())
    monkeypatch.delenv("NOTIFIER_URL", raising=False)
    set_tenant(engagement.REPORT_ENABLED_KEY, True, tenant_id=tenant.id)
    set_tenant(engagement.REPORT_DIR_KEY, str(tmp_path), tenant_id=tenant.id)

    result = engagement.run_report_for_tenant(tenant)
    assert result["report"]["degraded"] is True
    digest = engagement.build_digest(result["report"], lookback=7, report_path=result["report_path"])
    assert "NO LIVE DATA" in digest["title"]


# --- FIX 3: the management command lives under the installed app (T-033) ---------

@pytest.mark.django_db
def test_wa_engagement_report_command_is_discoverable(monkeypatch, tenant, tmp_path):
    monkeypatch.delenv("WATI_API_ENDPOINT", raising=False)
    monkeypatch.delenv("WATI_BASE_URL", raising=False)
    monkeypatch.delenv("WATI_API_TOKEN", raising=False)
    monkeypatch.delenv("NOTIFIER_URL", raising=False)
    set_tenant(engagement.REPORT_ENABLED_KEY, True, tenant_id=tenant.id)
    set_tenant(engagement.REPORT_DIR_KEY, str(tmp_path), tenant_id=tenant.id)

    out = io.StringIO()
    call_command("wa_engagement_report", "--json", stdout=out)
    payload = json.loads(out.getvalue())
    assert payload[tenant.slug]["skipped"] is False


# --- notify_owner ------------------------------------------------------------------

def test_notify_owner_fails_cleanly_without_url(monkeypatch):
    from apps.common.notify_owner import notify

    monkeypatch.delenv("NOTIFIER_URL", raising=False)
    result = notify(project="gorefer", severity="info", title="t", body="b")
    assert result["ok"] is False


def test_notify_owner_never_raises_on_transport_error(monkeypatch):
    from apps.common.notify_owner import notify

    monkeypatch.setenv("NOTIFIER_URL", "http://127.0.0.1:1")  # nothing listens here
    result = notify(project="gorefer", severity="info", title="t", body="b", dedupeKey="k")
    assert result["ok"] is False
