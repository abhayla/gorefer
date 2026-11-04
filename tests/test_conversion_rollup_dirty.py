"""Conversion rollup marking + the accounts_opened drift audit (2026-11-05).

The rollup counts `accounts_opened` from Conversion rows by ONE predicate
(`rollups._accounts_opened_for_range`): the conversion's own `program`, not reversed,
`account_opened_at` inside the IST day — whatever the stage, whatever the referral.
The ingest used to mark the day dirty under a narrower predicate (attributed: only
stage == account_opened and under `referral.program`; never the OLD day when the open
date moved; a reversal only with a referral). These are logic gaps shown by the tests
below; the one observed prod drift (2026-11-04) is unexplained and NOT attributed to them.

Marks now run ON COMMIT. These are `db` tests (never committing), so ingest calls run
inside `apply_rollup_marks()` (conftest), which executes only the captured marks.
"""
from __future__ import annotations

import datetime as dt
import io

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.events.models import DailyMetric, DirtyPeriod
from apps.events.rollups import mark_dirty, mark_dirty_ids, recompute_dirty
from apps.integrations.models import Conversion
from apps.integrations.zoho.ingest import DuplicateDelivery, ingest_conversion
from apps.referrals.models import Referral, ReferralIdentity, ReferralProgram

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
_MARKS = {}


@pytest.fixture(autouse=True)
def _marks(apply_rollup_marks):
    _MARKS["cm"] = apply_rollup_marks
    yield
    _MARKS.clear()


@pytest.fixture
def program(db):
    call_command("seed_program")
    return ReferralProgram.objects.order_by("id").first()


def _payload(*, event_id, account, opened, referrer="RJ4521", status="Account Opened",
             reversed_=False):
    payload = {
        "event_id": event_id,
        "opener_zerodha_account_id": account,
        "referrer_client_id": referrer,
        "status": status,
        "account_opened_at": opened.isoformat() if opened else "",
    }
    if reversed_:
        payload["reversed"] = True
    return payload


def _ingest(program, **kw):
    with _MARKS["cm"]():
        return ingest_conversion(tenant=program.tenant, payload=_payload(**kw))


def _unprocessed_days(program):
    return set(
        DirtyPeriod.objects.filter(program=program, processed_at__isnull=True)
        .values_list("period_date", flat=True)
    )


def _settle():
    DirtyPeriod.objects.all().update(processed_at=timezone.now())


# --- marking gaps (each RED on main before the fix) ---------------------------------

def test_attributed_non_terminal_stage_marks_open_day(program):
    conv = _ingest(program, event_id="rd-1", account="RDA001",
                   opened=dt.datetime(2025, 4, 30, 0, 0, tzinfo=IST), status="Contacted")
    assert conv.referral is not None and conv.status == "contacted"
    assert dt.date(2025, 4, 30) in _unprocessed_days(program)


def test_attributed_referral_in_another_program_marks_the_conversions_program(program):
    """The referrer identity lookup is not program-scoped, so the resolved referral can
    belong to a different program than the conversion. The rollup counts by
    `conversion.program`; the old mark used `referral.program`."""
    other = ReferralProgram.objects.create(
        tenant=program.tenant, partner=program.partner, name="Other program",
        status="active", url_prefix="otherprog",
    )
    identity = ReferralIdentity.objects.create(
        tenant=program.tenant, partner=program.partner, program=other,
        client_id="OTH123", id_source="native", status="active",
    )
    Referral.objects.create(tenant=program.tenant, referral_identity=identity, program=other,
                            source="zoho_import", status="opened")
    conv = _ingest(program, event_id="rd-2", account="RDA002",
                   opened=dt.datetime(2025, 6, 19, 0, 0, tzinfo=IST), referrer="OTH123")
    assert conv.program_id == program.id and conv.referral.program_id == other.id
    assert dt.date(2025, 6, 19) in _unprocessed_days(program)


def test_open_date_change_marks_old_and_new_day(program):
    _ingest(program, event_id="rd-3a", account="RDA003",
            opened=dt.datetime(2025, 7, 3, 0, 0, tzinfo=IST))
    _settle()
    _ingest(program, event_id="rd-3b", account="RDA003",
            opened=dt.datetime(2025, 8, 1, 0, 0, tzinfo=IST))
    assert {dt.date(2025, 7, 3), dt.date(2025, 8, 1)} <= _unprocessed_days(program)


def test_unattributed_reversal_marks_open_day(program):
    _ingest(program, event_id="rd-4a", account="RDA004", referrer="",
            opened=dt.datetime(2023, 10, 15, 0, 0, tzinfo=IST))
    _settle()
    _ingest(program, event_id="rd-4b", account="RDA004", referrer="",
            opened=dt.datetime(2023, 10, 15, 0, 0, tzinfo=IST), reversed_=True)
    assert dt.date(2023, 10, 15) in _unprocessed_days(program)


def test_redelivery_is_idempotent_and_adds_no_rows(program):
    opened = dt.datetime(2025, 5, 5, 9, 0, tzinfo=IST)
    _ingest(program, event_id="rd-5", account="RDA005", opened=opened)
    before = DirtyPeriod.objects.count()
    with pytest.raises(DuplicateDelivery):
        _ingest(program, event_id="rd-5", account="RDA005", opened=opened)
    _ingest(program, event_id="rd-5b", account="RDA005", opened=opened)
    assert DirtyPeriod.objects.count() == before
    assert Conversion.objects.filter(opener_zerodha_account_id="RDA005").count() == 1


# --- MAJOR 1: the mark runs only after the ingest commits ----------------------------

def test_mark_is_deferred_until_commit(program, django_capture_on_commit_callbacks):
    day = dt.date(2025, 3, 3)
    with django_capture_on_commit_callbacks() as callbacks:
        ingest_conversion(tenant=program.tenant, payload=_payload(
            event_id="rd-oc", account="RDAOC1", opened=dt.datetime(2025, 3, 3, 0, 0, tzinfo=IST)))
        # Inside the (uncommitted) transaction: no DirtyPeriod for the day yet.
        assert day not in _unprocessed_days(program)
    assert day not in _unprocessed_days(program)
    marks = [cb for cb in callbacks if getattr(cb, "func", None) is mark_dirty_ids]
    assert marks, "the ingest registered no on-commit rollup mark"
    for cb in marks:  # what the commit runs
        cb()
    assert day in _unprocessed_days(program)


# --- MINOR: duplicate unprocessed rows never fail a mark / an ingest -----------------

def test_duplicate_unprocessed_rows_do_not_fail_mark_or_ingest(program):
    day = dt.date(2025, 2, 2)
    for _ in range(2):
        DirtyPeriod.objects.create(tenant=program.tenant, program=program, period_date=day)
    mark_dirty(tenant=program.tenant, program=program, on_date=day)  # no raise
    conv = _ingest(program, event_id="rd-dup", account="RDADUP",
                   opened=dt.datetime(2025, 2, 2, 0, 0, tzinfo=IST))
    assert conv is not None
    assert DirtyPeriod.objects.filter(period_date=day, processed_at__isnull=True).count() == 2


# --- recompute keeps main's retry behaviour ------------------------------------------

def test_recompute_failure_leaves_the_row_for_retry(program, monkeypatch):
    from apps.events import rollups

    day = dt.date(2025, 1, 1)
    mark_dirty(tenant=program.tenant, program=program, on_date=day)

    def boom(**kw):
        raise RuntimeError("killed mid-recompute")

    monkeypatch.setattr(rollups, "_recompute_month", boom)
    with pytest.raises(RuntimeError):
        recompute_dirty()
    assert day in _unprocessed_days(program)


# --- detection + self-heal -------------------------------------------------------------

def _two_clean_conversions(program):
    _ingest(program, event_id="rd-7a", account="RDA007", status="Contacted",
            opened=dt.datetime(2025, 4, 30, 0, 0, tzinfo=IST))
    _ingest(program, event_id="rd-7b", account="RDA008",
            opened=dt.datetime(2025, 7, 3, 0, 0, tzinfo=IST))
    recompute_dirty()


def test_check_command_ok_then_detects_and_heals_drift(program):
    from apps.events.rollup_audit import find_drift

    _two_clean_conversions(program)
    assert find_drift() == []
    ok = io.StringIO()
    call_command("check_rollup_conversions", stdout=ok)
    assert ok.getvalue().startswith("OK")

    # Drift 1: a Conversion written with no dirty mark.
    Conversion.objects.create(
        tenant=program.tenant, program=program, opener_zerodha_account_id="RDA009",
        account_opened_at=dt.datetime(2024, 1, 2, 0, 0, tzinfo=IST),
    )
    drift = find_drift(recompute=False)
    assert len(drift) == 1 and drift[0]["conversions"] == 3 and drift[0]["monthly_total"] == 2

    report = io.StringIO()
    with pytest.raises(SystemExit) as exc:
        call_command("check_rollup_conversions", "--no-heal", stdout=report)
    assert exc.value.code == 1 and "conversions=3" in report.getvalue()
    assert "not healed" in report.getvalue()

    healed = io.StringIO()
    with pytest.raises(SystemExit):
        call_command("check_rollup_conversions", stdout=healed)
    assert "HEALED" in healed.getvalue()
    assert find_drift(recompute=False) == []


def test_scheduled_audit_heals_an_edited_daily_metric_and_alerts_p2(program, monkeypatch):
    from apps.common import notify_owner
    from apps.events import rollup_audit

    _two_clean_conversions(program)
    DailyMetric.objects.filter(program=program, metric_date=dt.date(2025, 7, 3)).update(
        accounts_opened=0)
    sent = []
    monkeypatch.setattr(notify_owner, "notify", lambda **kw: sent.append(kw) or {"ok": True})

    out = rollup_audit.scheduled_audit()
    assert out["before"][0]["daily_total"] == 1 and out["before"][0]["conversions"] == 2
    assert out["healed"] is True and out["after"] == []
    assert len(sent) == 1 and sent[0]["severity"] == "P2"
    assert "daily_total=1" in sent[0]["body"] and "all tenants/programs match" in sent[0]["body"]
    assert rollup_audit.find_drift(recompute=False) == []


def test_scheduled_audit_never_raises_and_alerts_p1_on_failure(program, monkeypatch):
    from apps.common import notify_owner
    from apps.events import rollup_audit

    def broken(**kw):
        raise RuntimeError("db gone")

    monkeypatch.setattr(rollup_audit, "find_drift", broken)
    sent = []
    monkeypatch.setattr(notify_owner, "notify", lambda **kw: sent.append(kw) or {"ok": True})
    out = rollup_audit.scheduled_audit()
    assert out == {"error": "RuntimeError"}
    assert sent and sent[0]["severity"] == "P1" and "audit failed: RuntimeError" in sent[0]["title"]


def test_rollup_conversion_audit_is_scheduled_daily():
    from apps.events.management.commands.setup_schedules import SCHEDULES

    assert SCHEDULES["rollup_conversion_audit"] == ("apps.events.rollup_audit.scheduled_audit", 1440)
