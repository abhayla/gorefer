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


def test_redelivery_is_idempotent_and_marks_no_new_day(program):
    # mark_dirty always inserts (race fix, 2026-11-05), so a same-data re-ingest may add
    # a duplicate row for the SAME day; what must not change is the set of dirty days.
    opened = dt.datetime(2025, 5, 5, 9, 0, tzinfo=IST)
    _ingest(program, event_id="rd-5", account="RDA005", opened=opened)
    days_before = _unprocessed_days(program)
    count_before = DirtyPeriod.objects.count()
    with pytest.raises(DuplicateDelivery):
        _ingest(program, event_id="rd-5", account="RDA005", opened=opened)
    assert DirtyPeriod.objects.count() == count_before  # exact duplicate: rejected, no mark
    _ingest(program, event_id="rd-5b", account="RDA005", opened=opened)
    assert _unprocessed_days(program) == days_before
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
    # 2 pre-existing + 1 mark_dirty + at least 1 ingest mark: every mark inserts its own row.
    assert DirtyPeriod.objects.filter(period_date=day, processed_at__isnull=True).count() >= 4


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


# --- lost dirty-marks: a mark landing mid-recompute must survive (2026-11-05) -----------

def test_mark_arriving_mid_recompute_is_not_closed_uncounted(program, monkeypatch):
    """RED on the get_or_create mark: the mark made after the worker counted the day
    reused the row the worker then closed, so the 2nd conversion was never counted."""
    from apps.events import rollups

    day = dt.date(2025, 9, 9)
    opened = dt.datetime(2025, 9, 9, 10, 0, tzinfo=IST)
    Conversion.objects.create(tenant=program.tenant, program=program,
                              opener_zerodha_account_id="RACE01", account_opened_at=opened)
    mark_dirty(tenant=program.tenant, program=program, on_date=day)

    real = rollups._recompute_day
    fired = []

    def racing(**kw):
        real(**kw)  # the worker has now COUNTED the day (1 conversion)
        if not fired:
            fired.append(1)  # concurrent writer: new conversion + its mark
            Conversion.objects.create(tenant=program.tenant, program=program,
                                      opener_zerodha_account_id="RACE02",
                                      account_opened_at=opened)
            mark_dirty(tenant=program.tenant, program=program, on_date=day)

    monkeypatch.setattr(rollups, "_recompute_day", racing)
    recompute_dirty()
    monkeypatch.setattr(rollups, "_recompute_day", real)
    assert DirtyPeriod.objects.filter(period_date=day, processed_at__isnull=True).count() == 1
    assert DailyMetric.objects.get(program=program, metric_date=day).accounts_opened == 1
    assert recompute_dirty() == 1
    assert DailyMetric.objects.get(program=program, metric_date=day).accounts_opened == 2
    assert not DirtyPeriod.objects.filter(processed_at__isnull=True).exists()


def test_duplicate_rows_are_recomputed_once_and_all_closed(program, monkeypatch):
    from apps.events import rollups

    day = dt.date(2025, 9, 10)
    for _ in range(3):
        mark_dirty(tenant=program.tenant, program=program, on_date=day)
    assert DirtyPeriod.objects.filter(period_date=day, processed_at__isnull=True).count() == 3
    calls = {"day": 0, "month": 0}
    real_d, real_m = rollups._recompute_day, rollups._recompute_month
    monkeypatch.setattr(rollups, "_recompute_day",
                        lambda **kw: calls.__setitem__("day", calls["day"] + 1) or real_d(**kw))
    monkeypatch.setattr(rollups, "_recompute_month",
                        lambda **kw: calls.__setitem__("month", calls["month"] + 1) or real_m(**kw))
    assert recompute_dirty() == 3
    assert calls == {"day": 1, "month": 1}
    assert DirtyPeriod.objects.filter(period_date=day, processed_at__isnull=True).count() == 0
    assert DirtyPeriod.objects.filter(period_date=day, processed_at__isnull=False).count() == 3


def test_limit_closes_only_the_limited_rows(program):
    for i in range(5):
        mark_dirty(tenant=program.tenant, program=program, on_date=dt.date(2025, 10, 1 + i))
    assert recompute_dirty(limit=2) == 2
    assert DirtyPeriod.objects.filter(processed_at__isnull=False).count() == 2
    assert DirtyPeriod.objects.filter(processed_at__isnull=True).count() == 3
    assert set(DirtyPeriod.objects.filter(processed_at__isnull=False)
               .values_list("period_date", flat=True)) == {dt.date(2025, 10, 1), dt.date(2025, 10, 2)}


def test_heal_fixes_a_too_high_day(program):
    from apps.events.rollup_audit import find_drift, heal

    _two_clean_conversions(program)
    ghost = dt.date(2024, 3, 3)
    DailyMetric.objects.create(tenant=program.tenant, program=program, metric_date=ghost,
                               accounts_opened=1)
    drift = find_drift(recompute=False)
    assert len(drift) == 1 and drift[0]["daily_total"] == 3 and drift[0]["conversions"] == 2
    assert heal(drift) == []
    assert DailyMetric.objects.get(program=program, metric_date=ghost).accounts_opened == 0
    assert find_drift(recompute=False) == []


def test_three_alerts_have_distinct_dedupe_keys(program, monkeypatch):
    from apps.common import notify_owner
    from apps.events import rollup_audit

    sent = []
    monkeypatch.setattr(notify_owner, "notify", lambda **kw: sent.append(kw) or {"ok": True})
    today = timezone.localdate().isoformat()
    _two_clean_conversions(program)
    DailyMetric.objects.filter(program=program, metric_date=dt.date(2025, 7, 3)).update(
        accounts_opened=0)
    rollup_audit.scheduled_audit()  # healed
    real_heal = rollup_audit.heal
    monkeypatch.setattr(rollup_audit, "heal", lambda drift: drift)  # heal does nothing
    DailyMetric.objects.filter(program=program, metric_date=dt.date(2025, 7, 3)).update(
        accounts_opened=0)
    rollup_audit.scheduled_audit()  # still drifting
    monkeypatch.setattr(rollup_audit, "heal", real_heal)
    monkeypatch.setattr(rollup_audit, "find_drift",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("x")))
    rollup_audit.scheduled_audit()  # failed
    assert [(k["severity"], k["dedupeKey"]) for k in sent] == [
        ("P2", f"rollup-drift-healed-{today}"),
        ("P1", f"rollup-drift-still-{today}"),
        ("P1", f"rollup-audit-failed-{today}"),
    ]


# --- overlapping runs are serialised (PR #205 review MAJOR) ---------------------------

def _hold_lock_in_other_session():
    """A second, real Postgres session holding the recompute advisory lock."""
    import psycopg2
    from django.db import connection

    from apps.events.rollups import RECOMPUTE_LOCK_KEY

    sd = connection.settings_dict
    other = psycopg2.connect(
        dbname=sd["NAME"], user=sd["USER"], password=sd["PASSWORD"],
        host=sd["HOST"] or "localhost", port=sd["PORT"] or 5432,
    )
    other.autocommit = True
    with other.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(%s)", [RECOMPUTE_LOCK_KEY])
    return other


def test_recompute_skips_without_closing_when_another_run_holds_the_lock(program):
    day = dt.date(2025, 6, 6)
    mark_dirty(tenant=program.tenant, program=program, on_date=day)
    other = _hold_lock_in_other_session()
    try:
        assert recompute_dirty(wait=False) == 0
        assert DirtyPeriod.objects.filter(period_date=day, processed_at__isnull=True).count() == 1
    finally:
        other.close()  # releases the session lock
    assert recompute_dirty(wait=False) == 1
    assert DirtyPeriod.objects.filter(period_date=day, processed_at__isnull=True).count() == 0


def test_dashboard_page_load_never_blocks_on_the_recompute_lock():
    import inspect

    from apps.dashboard import queries

    assert "wait=False" in inspect.getsource(queries)
