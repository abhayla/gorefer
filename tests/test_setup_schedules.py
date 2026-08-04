"""setup_schedules — ADR-047 §2/§3: registry merge + update-mode.

Covers the three cases the update mode must handle for an existing name whose row
diverges from the map (missing / matching / diverging), plus that the merged
SCHEDULES | INTEGRATION_SCHEDULES map contains exactly the domain + boundary
entries with no overlap.
"""
from __future__ import annotations

import pytest
from django.core.management import call_command
from django_q.models import Schedule

from apps.events.management.commands.setup_schedules import SCHEDULES
from apps.integrations.schedules import INTEGRATION_SCHEDULES


def test_registry_merge_has_no_name_overlap():
    assert set(SCHEDULES) & set(INTEGRATION_SCHEDULES) == set()


@pytest.mark.django_db
def test_creates_missing_schedule_rows():
    call_command("setup_schedules")
    merged = {**SCHEDULES, **INTEGRATION_SCHEDULES}
    assert Schedule.objects.count() == len(merged)
    for name, (func, minutes) in merged.items():
        row = Schedule.objects.get(name=name)
        assert row.func == func
        assert row.minutes == minutes


@pytest.mark.django_db
def test_unchanged_row_is_a_noop():
    name, (func, minutes) = next(iter(SCHEDULES.items()))
    Schedule.objects.create(
        name=name, func=func, schedule_type=Schedule.MINUTES, minutes=minutes,
    )
    row_id_before = Schedule.objects.get(name=name).id

    call_command("setup_schedules")

    row = Schedule.objects.get(name=name)
    assert row.id == row_id_before
    assert row.func == func
    assert row.minutes == minutes


@pytest.mark.django_db
def test_diverging_func_is_updated_in_place():
    """A moved module must not leave prod's Schedule row pointing at a dead path."""
    name, (func, minutes) = next(iter(INTEGRATION_SCHEDULES.items()))
    stale_func = "apps.integrations.zoho.old_module.dead_path"
    Schedule.objects.create(
        name=name, func=stale_func, schedule_type=Schedule.MINUTES, minutes=minutes,
    )
    row_id_before = Schedule.objects.get(name=name).id

    call_command("setup_schedules")

    row = Schedule.objects.get(name=name)
    assert row.id == row_id_before  # updated in place, not deleted+recreated
    assert row.func == func
    assert row.minutes == minutes


@pytest.mark.django_db
def test_diverging_minutes_is_updated_in_place():
    name, (func, minutes) = next(iter(SCHEDULES.items()))
    Schedule.objects.create(
        name=name, func=func, schedule_type=Schedule.MINUTES, minutes=minutes + 999,
    )

    call_command("setup_schedules")

    row = Schedule.objects.get(name=name)
    assert row.func == func
    assert row.minutes == minutes


@pytest.mark.django_db
def test_unknown_row_is_never_deleted():
    Schedule.objects.create(
        name="some_other_unrelated_schedule", func="apps.foo.bar",
        schedule_type=Schedule.MINUTES, minutes=30,
    )

    call_command("setup_schedules")

    assert Schedule.objects.filter(name="some_other_unrelated_schedule").exists()
