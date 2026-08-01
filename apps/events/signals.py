"""Signals: mark the affected day dirty whenever a funnel event lands (#6/#34).

Keeps rollups eventually-consistent without inline recompute — the day (and its
month) enters the dirty set; a worker recomputes exactly those periods. Only funnel
events with a program-scoped referral dirty a period.
"""
from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from . import vocab
from .models import Event
from .rollups import mark_dirty

_FUNNEL_TYPES = {stage for stage, _ in vocab.FUNNEL_STAGES}


@receiver(post_save, sender=Event)
def _mark_period_dirty(sender, instance: Event, created, **kwargs):
    if not created or instance.event_type not in _FUNNEL_TYPES:
        return
    referral = instance.referral
    if referral is None or referral.program_id is None:
        return
    # LOCAL (IST) date, never `.date()` — same P0-H trap already fixed on the Zoho
    # ingest path. `timestamp` is auto_now_add and comes back as an AWARE UTC value,
    # so `.date()` yields the UTC date, while `rollups._recompute_day` builds its
    # window in the CURRENT timezone (Asia/Kolkata). For any event between 00:00 and
    # 05:30 IST the two disagree: the day is filed under the previous UTC date, and
    # the IST window for that date ends at 00:00 IST — before the event. The rollup
    # is then recomputed over a range the event is not in (written as 0) and the day
    # it truly belongs to is never marked dirty at all, so the count is lost.
    mark_dirty(
        tenant=instance.tenant,
        program=referral.program,
        on_date=timezone.localtime(instance.timestamp).date(),
    )
