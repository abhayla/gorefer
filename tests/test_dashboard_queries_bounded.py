"""T-046: proves apps/dashboard/queries.py explorer_rows / top_referrers issue a
BOUNDED, constant number of queries regardless of how many referrals exist — no
per-row N+1. Uses django.test.utils.CaptureQueriesContext directly against the
seeded program (no admin-panel HTTP layer, so this is immune to unrelated view-level
query changes)."""
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.dashboard import queries
from apps.events.models import Event
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
