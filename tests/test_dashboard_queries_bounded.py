"""T-046: proves apps/dashboard/queries.py explorer_rows / top_referrers issue a
BOUNDED, constant number of queries regardless of how many referrals exist — no
per-row N+1. Uses django.test.utils.CaptureQueriesContext directly against the
seeded program (no admin-panel HTTP layer, so this is immune to unrelated view-level
query changes)."""
import datetime as dt

from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.dashboard import queries
from apps.events.models import DirtyPeriod, Event
from apps.referrals.models import Referral, ReferralIdentity, ReferralProgram


def _seed_referrals(n: int, *, prefix: str):
    """Create N referrals, each with a click + landing_viewed event, under the
    seeded program. Mirrors real explorer/leaderboard traffic shape."""
    program = ReferralProgram.objects.get()
    for i in range(n):
        client_id = f"{prefix}{i:04d}"
        identity = ReferralIdentity.objects.create(
            tenant=program.tenant, program=program, partner=program.partner,
            client_id=client_id, status="active",
        )
        ref = Referral.objects.create(
            tenant=program.tenant, program=program, referral_identity=identity,
            source="referral_link", status="opened",
        )
        Event.objects.create(tenant=program.tenant, referral=ref, event_type="click", is_bot=False)
        Event.objects.create(
            tenant=program.tenant, referral=ref, event_type="landing_viewed", is_bot=False
        )
    return program.tenant


def test_explorer_rows_query_count_bounded(db):
    call_command("seed_program")
    tenant = ReferralProgram.objects.get().tenant

    _seed_referrals(5, prefix="QB5")
    with CaptureQueriesContext(connection) as ctx_small:
        rows_small = queries.explorer_rows(tenant)  # default page size (100) covers 5 rows
    small_count = len(ctx_small.captured_queries)
    assert len(rows_small) == 5

    _seed_referrals(45, prefix="QB50")  # 5 + 45 = 50 total referrals now on this tenant
    with CaptureQueriesContext(connection) as ctx_big:
        rows_big = queries.explorer_rows(tenant)  # default page size (100) covers 50 rows
    big_count = len(ctx_big.captured_queries)
    assert len(rows_big) == 50

    assert small_count <= 15, f"explorer_rows issued {small_count} queries for 5 referrals"
    assert big_count <= 15, f"explorer_rows issued {big_count} queries for 50 referrals"
    assert big_count == small_count, (
        f"explorer_rows query count grew with row count ({small_count} -> {big_count}) — "
        "an N+1 regression"
    )


def test_explorer_row_count_query_count_bounded(db):
    call_command("seed_program")
    tenant = ReferralProgram.objects.get().tenant

    _seed_referrals(5, prefix="QC5")
    with CaptureQueriesContext(connection) as ctx_small:
        total_small = queries.explorer_row_count(tenant)
    small_count = len(ctx_small.captured_queries)
    assert total_small == 5

    _seed_referrals(45, prefix="QC50")  # 5 + 45 = 50 total
    with CaptureQueriesContext(connection) as ctx_big:
        total_big = queries.explorer_row_count(tenant)
    big_count = len(ctx_big.captured_queries)
    assert total_big == 50

    assert small_count <= 5
    assert big_count <= 5
    assert big_count == small_count


def test_top_referrers_query_count_bounded(db):
    call_command("seed_program")
    tenant = ReferralProgram.objects.get().tenant

    _seed_referrals(5, prefix="TR5")
    with CaptureQueriesContext(connection) as ctx_small:
        rows_small = queries.top_referrers(tenant, limit=10)
    small_count = len(ctx_small.captured_queries)
    assert len(rows_small) == 5

    _seed_referrals(45, prefix="TR50")  # 5 + 45 = 50 total referrals now on this tenant
    with CaptureQueriesContext(connection) as ctx_big:
        rows_big = queries.top_referrers(tenant, limit=10)
    big_count = len(ctx_big.captured_queries)
    assert len(rows_big) == 10  # leaderboard limit applies

    assert small_count <= 10, f"top_referrers issued {small_count} queries for 5 referrals"
    assert big_count <= 10, f"top_referrers issued {big_count} queries for 50 referrals"
    assert big_count == small_count, (
        f"top_referrers query count grew with row count ({small_count} -> {big_count}) — "
        "an N+1 regression"
    )


# --------------------------------------------------------------------- T-161 pt 21


def test_refresh_and_freshness_recompute_is_bounded_at_a_50_day_backlog(db, monkeypatch):
    """A page-load must cost the SAME recompute work regardless of how large the
    dirty backlog has grown — DASHBOARD_RECOMPUTE_LIMIT bounds it, and the leftover
    backlog is reported via `dirty_backlog_remains` rather than silently vanishing
    from view. A smaller limit is monkeypatched in so a 50-day seeded backlog can
    prove the bound holds without forcing an unrealistically low production default.
    """
    call_command("seed_program")
    tenant = ReferralProgram.objects.get().tenant
    program = ReferralProgram.objects.get()

    monkeypatch.setattr(queries, "DASHBOARD_RECOMPUTE_LIMIT", 10)

    base = dt.date(2020, 1, 1)  # isolated past dates no fixture touches
    for i in range(50):
        DirtyPeriod.objects.create(
            tenant=tenant, program=program, period_date=base + dt.timedelta(days=i)
        )

    queries.refresh_and_freshness(tenant)

    processed = DirtyPeriod.objects.filter(
        tenant=tenant, period_date__gte=base, processed_at__isnull=False
    ).count()
    assert processed == 10, (
        f"one page-load recomputed {processed} dirty periods, expected exactly "
        "the bound (10)"
    )
    assert queries.dirty_backlog_remains(tenant) is True, (
        "50 dirty periods with only 10 processed must still report a remaining backlog"
    )

    # Finish the backlog off (further page-loads, or the scheduled job) and the note
    # must clear.
    for _ in range(4):
        queries.refresh_and_freshness(tenant)
    assert queries.dirty_backlog_remains(tenant) is False


# --------------------------------------------------------------------- T-161 pt 22


def test_profile_clicks_rows_query_count_bounded_at_1000_clicks(db):
    """A single referrer's Clicks tab must cost the SAME query shape whether they
    have 20 clicks or 1000 — clicks_rows pages server-side and bounds its
    outcome-window scan to the page's own time span (T-161 pt 22)."""
    from apps.dashboard import profile

    call_command("seed_program")
    program = ReferralProgram.objects.get()
    tenant = program.tenant
    client_id = "CLK1000"
    identity = ReferralIdentity.objects.create(
        tenant=tenant, program=program, partner=program.partner,
        client_id=client_id, status="active",
    )
    referral = Referral.objects.create(
        tenant=tenant, program=program, referral_identity=identity,
        source="referral_link", status="opened",
    )

    base = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    small_n = 20
    for i in range(small_n):
        Event.objects.create(
            tenant=tenant, referral=referral, event_type="click", is_bot=False,
            timestamp=base + dt.timedelta(minutes=i),
        )
    with CaptureQueriesContext(connection) as ctx_small:
        rows_small = profile.clicks_rows(tenant, client_id, page=1)
    small_count = len(ctx_small.captured_queries)
    assert len(rows_small) == small_n

    big_n = 1000
    for i in range(small_n, big_n):
        Event.objects.create(
            tenant=tenant, referral=referral, event_type="click", is_bot=False,
            timestamp=base + dt.timedelta(minutes=i),
        )
    with CaptureQueriesContext(connection) as ctx_big:
        rows_big = profile.clicks_rows(tenant, client_id, page=1)
    big_count = len(ctx_big.captured_queries)
    # default page size (500) covers both the 20-click and 1000-click case's first page
    assert len(rows_big) == min(big_n, profile.clicks_page_size(tenant))

    assert small_count <= 10, f"clicks_rows issued {small_count} queries for {small_n} clicks"
    assert big_count <= 10, f"clicks_rows issued {big_count} queries for {big_n} clicks"
    assert big_count == small_count, (
        f"clicks_rows query count grew with click-history size ({small_count} -> {big_count}) — "
        "an N+1/unbounded-scan regression"
    )
