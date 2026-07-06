"""Signals: mark the affected day dirty whenever a funnel event lands (#6/#34).

Keeps rollups eventually-consistent without inline recompute — the day (and its
month) enters the dirty set; a worker recomputes exactly those periods. Only funnel
events with a program-scoped referral dirty a period.
"""
from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

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
    mark_dirty(tenant=instance.tenant, program=referral.program, on_date=instance.timestamp.date())
