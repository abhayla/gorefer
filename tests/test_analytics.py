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


def test_funnel_api_labels_unique_as_approximate(demo):
    body = Client().get("/api/analytics/funnel").json()
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
    body = Client().get("/api/analytics/sync-health").json()
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
