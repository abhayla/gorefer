"""Every Zoho conversion write marks its open-date rollup day dirty (hardening, 2026-11-05).

The rollup counts `accounts_opened` from Conversion rows by ONE predicate
(`rollups._accounts_opened_for_range`): the conversion's own `program`, not reversed,
`account_opened_at` inside the IST day — whatever the stage, whatever the referral.
Before this fix the ingest marked the day dirty under a DIFFERENT predicate:

  * attributed branch: only when stage == account_opened, and under `referral.program`;
  * unattributed branch: only when stage == account_opened;
  * update path: never the OLD open date when Zoho moved it;
  * reversal: only when the conversion had a referral.

Any conversion outside that predicate would be counted by a full recompute but never by
the dirty-day worker. These are logic gaps shown by the tests below; the one observed
prod drift (2026-11-04) is unexplained and is NOT attributed to them.

These tests drive the REAL ingest (`apps.integrations.zoho.ingest.ingest_conversion`).
"""
from __future__ import annotations

import datetime as dt

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.events.models import DirtyPeriod, MonthlyMetric
from apps.events.rollups import recompute_dirty
from apps.integrations.models import Conversion
from apps.integrations.zoho.ingest import DuplicateDelivery, ingest_conversion
from apps.referrals.models import Referral, ReferralIdentity, ReferralProgram

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


@pytest.fixture
def program(db):
    call_command("seed_program")
    return ReferralProgram.objects.order_by("id").first()


def _ingest(program, *, event_id, account, opened, referrer="RJ4521", status="Account Opened",
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
    return ingest_conversion(tenant=program.tenant, payload=payload)


def _unprocessed_days(program):
    return set(
        DirtyPeriod.objects.filter(program=program, processed_at__isnull=True)
        .values_list("period_date", flat=True)
    )


def _settle():
    DirtyPeriod.objects.all().update(processed_at=timezone.now())


# --- the skip conditions (each RED on main before the fix) ------------------------

def test_attributed_non_terminal_stage_marks_open_day(program):
    """Zoho Contacts send `Account_Status` as the status. A mapped non-terminal value
    (e.g. 'Contacted') with an open date is still counted by the rollup, so its day
    must be dirtied — before the fix only stage == account_opened dirtied it."""
    conv = _ingest(program, event_id="rd-1", account="RDA001",
                   opened=dt.datetime(2025, 4, 30, 0, 0, tzinfo=IST), status="Contacted")
    assert conv.referral is not None and conv.status == "contacted"
    assert dt.date(2025, 4, 30) in _unprocessed_days(program)


def test_attributed_referral_in_another_program_marks_the_conversions_program(program):
    """The referrer identity lookup is not program-scoped, so the resolved referral can
    belong to a different program than the conversion (`_active_program`). The rollup
    counts by `conversion.program`; the old mark used `referral.program`."""
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
    # Same data under a new event id: still one unprocessed row for the day.
    _ingest(program, event_id="rd-5b", account="RDA005", opened=opened)
    assert DirtyPeriod.objects.count() == before
    assert Conversion.objects.filter(opener_zerodha_account_id="RDA005").count() == 1


def test_mark_during_recompute_is_not_absorbed(program, monkeypatch):
    """A conversion landing while the worker is recomputing its day must leave a fresh
    unprocessed row — not be swallowed by the in-flight row the worker then closes."""
    from apps.events import rollups

    day = dt.date(2025, 9, 9)
    rollups.mark_dirty(tenant=program.tenant, program=program, on_date=day)
    real = rollups._accounts_opened_for_range
    fired = {"n": 0}

    def counting_then_ingest(**kw):
        n = real(**kw)
        if not fired["n"]:
            fired["n"] = 1
            _ingest(program, event_id="rd-6", account="RDA006",
                    opened=dt.datetime(2025, 9, 9, 10, 0, tzinfo=IST))
        return n

    monkeypatch.setattr(rollups, "_accounts_opened_for_range", counting_then_ingest)
    recompute_dirty()
    monkeypatch.setattr(rollups, "_accounts_opened_for_range", real)
    assert day in _unprocessed_days(program)
    recompute_dirty()
    month = MonthlyMetric.objects.get(program=program, year=2025, month=9)
    assert month.accounts_opened == 1


# --- detection: rollup total vs live conversions -----------------------------------

def test_check_rollup_conversions_flags_drift_and_passes_when_clean(program):
    import io

    from apps.events.rollup_audit import find_drift

    _ingest(program, event_id="rd-7a", account="RDA007", status="Contacted",
            opened=dt.datetime(2025, 4, 30, 0, 0, tzinfo=IST))
    _ingest(program, event_id="rd-7b", account="RDA008",
            opened=dt.datetime(2025, 7, 3, 0, 0, tzinfo=IST))
    recompute_dirty()
    assert find_drift() == []
    ok_out = io.StringIO()
    call_command("check_rollup_conversions", stdout=ok_out)  # exit 0
    assert ok_out.getvalue().startswith("OK")

    # A conversion written with no dirty mark (the class) is caught.
    Conversion.objects.create(
        tenant=program.tenant, program=program, opener_zerodha_account_id="RDA009",
        account_opened_at=dt.datetime(2024, 1, 2, 0, 0, tzinfo=IST),
    )
    drift = find_drift(recompute=False)
    assert len(drift) == 1 and drift[0]["conversions"] == 3 and drift[0]["monthly_total"] == 2
    out = io.StringIO()
    with pytest.raises(SystemExit) as exc:
        call_command("check_rollup_conversions", "--no-recompute", stdout=out)
    assert exc.value.code == 1
    assert "conversions=3" in out.getvalue()

    # The daily schedule alerts the owner through the Notifier on the same drift.
    from apps.common import notify_owner
    from apps.events import rollup_audit

    sent = []
    monkeypatch_notify = lambda **kw: sent.append(kw) or {"ok": True}  # noqa: E731
    original = notify_owner.notify
    notify_owner.notify = monkeypatch_notify
    try:
        out = rollup_audit.scheduled_audit()
    finally:
        notify_owner.notify = original
    assert out["drift"] and len(sent) == 1
    assert sent[0]["project"] == "gorefer" and "conversions=3" in sent[0]["body"]


def test_rollup_conversion_audit_is_scheduled_daily():
    from apps.events.management.commands.setup_schedules import SCHEDULES

    assert SCHEDULES["rollup_conversion_audit"] == ("apps.events.rollup_audit.scheduled_audit", 1440)
