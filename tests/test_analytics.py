"""M4 analytics: journey timeline, funnel, rollups (dirty-days), sync-health,
and the never-fabricate-conversions guard."""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.events import vocab
from apps.events.analytics import build_journey_timeline, funnel_counts
from apps.events.models import DailyMetric, DirtyPeriod, Event, MonthlyMetric
from apps.events.rollups import recompute_dirty
from apps.referrals.models import Referral


@pytest.fixture
def demo(db):
    call_command("seed_program")
    call_command("seed_demo")


# --- journey timeline ------------------------------------------------------

def test_journey_timeline_is_ordered_with_source_tags(demo):
    referral = Referral.objects.filter(source="referral_link").first()
    timeline = build_journey_timeline(referral)
    assert len(timeline) > 0
    # ordered by timestamp
    ts = [n["timestamp"] for n in timeline]
    assert ts == sorted(ts)
    # every node has a source tag + label
    for node in timeline:
        assert node["source"]
        assert node["label"]


# --- funnel ----------------------------------------------------------------

def test_funnel_counts_from_events_account_opened_source_only(demo):
    stages = {s["stage"]: s for s in funnel_counts()}
    assert stages["click"]["count"] > 0
    assert stages["landing_viewed"]["count"] > 0
    # account_opened is source-only: it reflects ONLY Zoho-sourced account_opened
    # events (seeded via the ingest path), never derived from clicks/leads.
    assert stages["account_opened"]["source_only"] is True
    zoho_opened = Event.objects.filter(event_type="account_opened", source="zoho").count()
    assert stages["account_opened"]["count"] == zoho_opened


def test_funnel_excludes_bots(demo):
    referral = Referral.objects.filter(source="referral_link").first()
    before = {s["stage"]: s["count"] for s in funnel_counts()}
    Event.objects.create(
        tenant=referral.tenant, event_type=vocab.CLICK, source=vocab.SRC_CLICK,
        referral=referral, is_bot=True, metadata={},
    )
    after = {s["stage"]: s["count"] for s in funnel_counts()}
    assert after["click"] == before["click"]  # bot click not counted



def _staff_client():
    """Analytics is staff-only (see api/analytics.py) — an anonymous client gets 401."""
    from django.contrib.auth import get_user_model

    U = get_user_model()
    u = U.objects.create(username="analytics-tester", is_staff=True, is_active=True)
    u.set_password("x")
    u.save()
    c = Client()
    c.force_login(u)
    return c

def test_funnel_api_labels_unique_as_approximate(demo):
    body = _staff_client().get("/api/analytics/funnel").json()
    assert "Approximate" in body["unique_visitors_note"]
    assert body["unique_visitors_approx"] >= 1


# --- rollups + dirty-days --------------------------------------------------

def test_events_mark_days_dirty_and_rollups_recompute(demo):
    # seed_demo already recomputed; a fresh event dirties the day again.
    referral = Referral.objects.filter(source="referral_link").first()
    Event.objects.create(
        tenant=referral.tenant, event_type=vocab.CLICK, source=vocab.SRC_CLICK,
        referral=referral, is_bot=False, metadata={},
    )
    assert DirtyPeriod.objects.filter(processed_at__isnull=True).exists()
    recompute_dirty()
    assert not DirtyPeriod.objects.filter(processed_at__isnull=True).exists()
    assert DailyMetric.objects.exists()
    assert MonthlyMetric.objects.exists()


def test_rollup_recompute_is_idempotent(demo):
    dm = DailyMetric.objects.first()
    clicks_before = dm.clicks
    # Re-mark + recompute the same day: counts must be stable (recompute-from-raw).
    from apps.events.rollups import mark_dirty
    mark_dirty(tenant=dm.tenant, program=dm.program, on_date=dm.metric_date)
    recompute_dirty()
    dm.refresh_from_db()
    assert dm.clicks == clicks_before


# --- sync-health scaffold --------------------------------------------------

def test_sync_health_shows_no_sync_in_demo(demo):
    body = _staff_client().get("/api/analytics/sync-health").json()
    assert body["zoho_state"] == "no_sync"
    assert body["zoho_last_sync"] is None


# --- NEVER FABRICATE CONVERSIONS ------------------------------------------

def test_zoho_only_events_all_carry_zoho_source(demo):
    # Every Zoho-only event (account_opened / reward / removed) must be tagged
    # source=zoho — i.e. produced ONLY by the Zoho ingest path, never internally.
    zoho_only = Event.objects.filter(event_type__in=list(vocab.ZOHO_ONLY_EVENTS))
    assert zoho_only.exists()  # demo seeds conversions through the ingest path
    assert zoho_only.exclude(source="zoho").count() == 0


def test_conversions_only_from_zoho_source_origin(demo):
    from apps.integrations.models import Conversion
    # Demo conversions exist, but ALL carry source_origin=zoho (mirrored, not made).
    assert Conversion.objects.exists()
    assert Conversion.objects.exclude(source_origin="zoho").count() == 0


# --- access control: read-only is NOT public ------------------------------

def test_analytics_endpoints_refuse_anonymous_callers(demo):
    """Regression: this router had NO auth until 2026-07-26.

    `/api/analytics/*` answered any anonymous caller over the internet — the AP's whole
    funnel (clicks, leads, accounts opened), an enumerable per-journey timeline, and internal
    integration health — while the /admin-panel/ screens showing the same numbers were behind
    login_required + is_staff. The UI was gated; the API feeding it was not.
    """
    anon = Client()
    referral = Referral.objects.filter(source="referral_link").first()
    for path in (
        "/api/analytics/funnel",
        f"/api/analytics/journey/{referral.id}",
        "/api/analytics/sync-health",
    ):
        assert anon.get(path).status_code == 401, f"{path} must not answer anonymous callers"


def test_analytics_endpoints_refuse_a_non_staff_user(demo):
    """is_authenticated is not enough — a logged-in customer must not read AP analytics."""
    from django.contrib.auth import get_user_model

    U = get_user_model()
    u = U.objects.create(username="plain-customer", is_staff=False, is_active=True)
    c = Client()
    c.force_login(u)
    assert c.get("/api/analytics/funnel").status_code == 401


# --- ADR-017 month boundary: IST-midnight conversions must land in the right month ---

def test_conversion_opened_on_the_1st_ist_counts_in_that_month(demo):
    """P0-H: an account opened on the 1st of a month IST must roll up into THAT month.

    `account_opened_at` is stored as IST-midnight-in-UTC — 1 Aug 2026 IST is
    `2026-07-31T18:30Z`. Two independent places can get this wrong:
      1. the range comparison in `_accounts_opened_for_range`, and
      2. `mark_dirty(on_date=conversion.account_opened_at.date())` in the Zoho ingest —
         `.date()` on a UTC-aware datetime yields the UTC date (31 Jul), which would mark
         the WRONG month dirty, so the right month never gets recomputed at all.

    A silent misdating: no error, just a conversion counted in the previous month. None of
    the live conversions currently falls on a 1st, which is why this has never shown up.
    """
    import datetime as dt

    from django.utils import timezone

    from apps.events.rollups import mark_dirty
    from apps.integrations.models import Conversion
    from apps.referrals.models import ReferralProgram

    program = ReferralProgram.objects.first()
    tenant = program.tenant
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    opened_ist = dt.datetime(2026, 8, 1, 0, 0, tzinfo=ist)  # 1 Aug 2026, IST midnight

    conv = Conversion.objects.create(
        tenant=tenant, program=program, opener_zerodha_account_id="MONTHBND1",
        account_opened_at=opened_ist, is_reversed=False,
    )
    # Sanity: it really is stored as the previous UTC day.
    assert conv.account_opened_at.astimezone(dt.timezone.utc).date() == dt.date(2026, 7, 31)
    # ...and the IST calendar date is the 1st.
    assert timezone.localtime(conv.account_opened_at).date() == dt.date(2026, 8, 1)

    # Drive it the way the INGEST does — re-read from the DB first, which is exactly the
    # state the reconciler/backfill paths are in. Before the fix this marked 31 Jul dirty,
    # so August was never recomputed and the conversion vanished from the month it belongs to.
    conv.refresh_from_db()
    mark_dirty(
        tenant=tenant, program=program,
        on_date=timezone.localtime(conv.account_opened_at).date(),
    )
    recompute_dirty()

    aug = MonthlyMetric.objects.filter(
        tenant=tenant, program=program, year=2026, month=8
    ).first()
    jul = MonthlyMetric.objects.filter(
        tenant=tenant, program=program, year=2026, month=7
    ).first()
    assert aug is not None and aug.accounts_opened == 1, (
        "conversion opened 1 Aug IST did not count in August"
    )
    assert (jul.accounts_opened if jul else 0) == 0, (
        "conversion opened 1 Aug IST leaked into July — month-boundary off-by-one"
    )


# --- OQ2b (owner ruling 2026-08-01, option A): unattributed conversions still roll up ---

def test_unattributed_conversion_counts_under_the_program_on_its_true_date(demo):
    """A Zoho conversion that names no referrer (off-platform, referral=None) must
    still count in DailyMetric.accounts_opened for the tenant's program, on its TRUE
    IST account-opening date — never invented attribution, just counted.

    Reproduces the exact shape found live 2026-08-01 (conversion id 15): referral=None,
    account_opened_at at exactly 00:00:00 IST (18:30:00Z the previous day). Before the
    fix, `_apply_upsert` only called `mark_dirty` inside the `if referral is not None`
    branch (via `_emit_conversion_events`), so an unattributed conversion's day was
    NEVER marked dirty and `recompute_dirty()` never touched it — even though
    `_accounts_opened_for_range` itself never filtered by referral. The row was
    silently absent from every DailyMetric/MonthlyMetric row forever.
    """
    import datetime as dt

    from apps.integrations.zoho.ingest import ingest_conversion
    from apps.referrals.models import ReferralProgram

    program = ReferralProgram.objects.first()
    tenant = program.tenant
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    opened_ist = dt.datetime(2026, 7, 29, 0, 0, tzinfo=ist)  # exactly IST midnight

    conv = ingest_conversion(
        tenant=tenant,
        payload={
            "event_id": "oq2b-unattributed-1",
            "opener_zerodha_account_id": "OQ2BNOREF1",
            "referrer_client_id": "",  # Zoho names no referrer — never guess (ADR-013/016)
            "status": "Account Opened",
            "account_opened_at": opened_ist.isoformat(),
        },
    )
    assert conv is not None and conv.referral is None, "conversion must stay referrer-less"
    assert conv.account_opened_at.astimezone(dt.timezone.utc) == dt.datetime(
        2026, 7, 28, 18, 30, tzinfo=dt.timezone.utc
    )

    recompute_dirty()

    day = DailyMetric.objects.filter(
        tenant=tenant, program=program, metric_date=dt.date(2026, 7, 29)
    ).first()
    assert day is not None and day.accounts_opened == 1, (
        "unattributed conversion (referral=None) did not count in its true-date DailyMetric row"
    )


def test_credited_conversion_is_not_double_counted(demo):
    """A normally-credited conversion (referral resolved) must still count exactly
    once — the new referral-less branch in `_apply_upsert` must never also fire for a
    conversion that DID resolve a referral."""
    import datetime as dt

    from apps.integrations.zoho.ingest import ingest_conversion
    from apps.referrals.models import ReferralProgram

    program = ReferralProgram.objects.first()
    tenant = program.tenant
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    opened_ist = dt.datetime(2026, 7, 29, 10, 0, tzinfo=ist)

    conv = ingest_conversion(
        tenant=tenant,
        payload={
            "event_id": "oq2b-credited-1",
            "opener_zerodha_account_id": "OQ2BCREDIT1",
            "referrer_client_id": "RJ4521",
            "status": "Account Opened",
            "account_opened_at": opened_ist.isoformat(),
        },
    )
    assert conv is not None and conv.referral is not None

    recompute_dirty()

    day = DailyMetric.objects.filter(
        tenant=tenant, program=program, metric_date=dt.date(2026, 7, 29)
    ).first()
    assert day is not None and day.accounts_opened == 1, (
        "credited conversion was counted more than once"
    )


def test_click_in_the_early_ist_hours_is_rolled_up_on_its_own_day(demo):
    """The SAME P0-H trap on the EVENT path (the Zoho ingest above was fixed; this
    one was missed) — `apps/events/signals.py` marked the day dirty from the raw
    `.date()` of an aware-UTC `timestamp` instead of its IST calendar date.

    Between 00:00 and 05:30 IST the UTC date is still the PREVIOUS day, so the click
    was filed under day D-1 while `rollups._recompute_day` builds its window in the
    current timezone: the IST window for D-1 ends at 00:00 IST, strictly BEFORE the
    click. The marked day therefore recomputed to 0, and day D — where the click
    actually lives — was never marked dirty at all, so no row was ever written for
    it. The click simply disappeared from the rollups the dashboard reads.

    This is why CI failed only on runs between 18:30 and 00:00 UTC and passed for
    everyone running the suite during the Indian working day. Pinning the timestamp
    into that window makes it deterministic at any wall-clock hour.
    """
    import datetime as dt

    from django.utils import timezone

    from apps.events.models import DirtyPeriod
    from apps.referrals.models import Referral

    referral = Referral.objects.filter(program__isnull=False).first()
    tenant, program = referral.tenant, referral.program

    # 02:00 IST on 2 Aug 2026 == 20:30 UTC on 1 Aug 2026 — inside the failure window.
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    clicked_ist = dt.datetime(2026, 8, 2, 2, 0, tzinfo=ist)

    DirtyPeriod.objects.all().update(processed_at=timezone.now())  # isolate this click
    event = Event.objects.create(
        tenant=tenant, event_type=vocab.CLICK, source=vocab.SRC_CLICK,
        referral=referral, is_bot=False, metadata={},
    )
    # `timestamp` is auto_now_add, so backdate it and re-fire the producer path the
    # way a real early-hours click would have arrived.
    Event.objects.filter(pk=event.pk).update(timestamp=clicked_ist)
    event.refresh_from_db()

    # Sanity: the UTC date and the IST calendar date genuinely disagree here.
    assert event.timestamp.astimezone(dt.timezone.utc).date() == dt.date(2026, 8, 1)
    assert timezone.localtime(event.timestamp).date() == dt.date(2026, 8, 2)

    # Drive the REAL producer — `apps.events.signals._mark_period_dirty` — rather than
    # calling `mark_dirty` ourselves with an already-correct date, which would bypass
    # the very line under test and pass either way.
    from apps.events.signals import _mark_period_dirty

    DirtyPeriod.objects.all().update(processed_at=timezone.now())
    _mark_period_dirty(sender=Event, instance=event, created=True)
    recompute_dirty()

    day = DailyMetric.objects.filter(
        tenant=tenant, program=program, metric_date=dt.date(2026, 8, 2)
    ).first()
    assert day is not None and day.clicks == 1, (
        "a click at 02:00 IST was not rolled up on its own IST day — the dirty day was "
        "filed from the UTC date while the recompute window is built in IST"
    )
