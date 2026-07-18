"""Fable5 residual — background-worker (qcluster) liveness indicator.

A dead django-q worker silently stops the Zoho retry/backfill, rollup recompute, WATI
reconcile and nonce purges. worker_health() surfaces that so it's visible, not silent.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.dashboard.health import WORKER_STALE_AFTER, worker_health


def test_sync_mode_reports_unknown(settings):
    """Inline/sync mode (dev/CI): no separate worker exists → 'unknown', never a false red."""
    settings.Q_CLUSTER = {**settings.Q_CLUSTER, "sync": True}
    h = worker_health()
    assert h["state"] == "unknown"


@pytest.mark.django_db
def test_healthy_when_a_recent_task_completed(settings):
    settings.Q_CLUSTER = {**settings.Q_CLUSTER, "sync": False}
    from django_q.models import Success

    Success.objects.create(
        name="t", func="x", started=timezone.now(), stopped=timezone.now(), success=True,
    )
    h = worker_health()
    assert h["state"] == "healthy"
    assert h["last_run"] is not None


@pytest.mark.django_db
def test_stale_when_last_run_is_old(settings):
    settings.Q_CLUSTER = {**settings.Q_CLUSTER, "sync": False}
    from django_q.models import Success

    old = timezone.now() - (WORKER_STALE_AFTER + timedelta(minutes=5))
    Success.objects.create(name="t", func="x", started=old, stopped=old, success=True)
    h = worker_health()
    assert h["state"] == "stale"
    assert "worker may be down" in h["detail"]


@pytest.mark.django_db
def test_stale_when_a_schedule_is_overdue(settings):
    """A schedule whose next_run is far in the past = the worker isn't advancing it."""
    settings.Q_CLUSTER = {**settings.Q_CLUSTER, "sync": False}
    from django_q.models import Schedule, Success

    # A recent success alone would say healthy; an overdue schedule overrides to stale.
    Success.objects.create(
        name="t", func="x", started=timezone.now(), stopped=timezone.now(), success=True,
    )
    Schedule.objects.create(
        name="rollups", func="apps.events.rollups.recompute_dirty",
        schedule_type=Schedule.MINUTES, minutes=5,
        next_run=timezone.now() - (WORKER_STALE_AFTER + timedelta(minutes=30)),
    )
    h = worker_health()
    assert h["state"] == "stale"


@pytest.mark.django_db
def test_never_raises(settings, monkeypatch):
    """A health probe must not 500 the dashboard even if the query layer explodes."""
    settings.Q_CLUSTER = {**settings.Q_CLUSTER, "sync": False}
    # Patch Success (imported locally inside worker_health) so its .objects.order_by
    # raises; the helper must swallow it and report 'unknown', never propagate.
    import django_q.models as qm

    class _S:
        class objects:
            @staticmethod
            def order_by(*a, **k):
                raise RuntimeError("db down")

    monkeypatch.setattr(qm, "Success", _S)
    assert worker_health()["state"] == "unknown"
