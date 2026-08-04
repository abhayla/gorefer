"""Register recurring django-q schedules (idempotent, self-healing). Run once after deploy.

Schedules:
  - the M4 dirty-day rollup recompute (the async infra that landed in M5);
  - the domain-owned nonce/retention/follow-up sweeps below;
  - the vendor (Wati/Zoho) sweeps, contributed by `apps.integrations.schedules.
    INTEGRATION_SCHEDULES` (ADR-047 §3) so this module stays clear of any
    vendor-package import while keeping the registry visible.

In production run `python manage.py qcluster` to execute scheduled jobs; in dev/CI
(Q_CLUSTER sync=True) schedules are inert.

Update mode (ADR-047 §2): a registered `Schedule` row is a public contract — prod's
django_q Schedule table stores the dotted `func` path by name. Previously an existing
name always no-op'd, so a moved/renamed module would leave prod pointing at a dead
path (hourly ImportError, silently). Now: missing row -> create; existing row whose
func/minutes MATCH the map -> no-op; existing row whose func or minutes DIFFER ->
UPDATE in place and log what changed. Unknown rows (not in the map) are left alone —
this command never deletes.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.integrations.schedules import INTEGRATION_SCHEDULES

# name -> (dotted task path, every N minutes)
SCHEDULES = {
    "recompute_rollups": ("apps.events.rollups.recompute_dirty", 5),
    # Daily (1440 min): the DPDP retention sweep — anonymise UNCONVERTED prospect PII past
    # the configured window (CLAUDE.md §4). Daily is the right cadence for a 12-month
    # obligation: hourly would be pointless churn, and anything rarer risks holding PII
    # past the window between runs. A retention policy nobody runs is not a policy — this
    # existed only as prose until 2026-07-27.
    "pii_retention_purge": ("apps.common.privacy.purge_expired_pii", 1440),
    # Hourly (Fable5 H3): every /r/{id} hit mints a ClickNonce; without a purge the
    # click_nonces table grows unbounded under crawling. Only rows past TTL+grace go.
    "click_purge_expired_nonces": ("apps.events.nonces.purge_expired_nonces", 60),
    # Every 5 min (M-FUP-1): sweep due follow-ups over the ScheduledFollowup due-table
    # (the same "recurring sweep over a due-table" idiom as wati_reconcile_pending). Each
    # due row is locked, gated (opt-out / engaged / window), then sent or cancelled/skipped.
    # 5-min granularity is fine for ≥15-min follow-up targets; nothing fires until
    # `followups_enabled` is on (re-checked at fire time).
    "followup_sweep": ("apps.followups.tasks.fire_due_followups", 5),
    # Every 5 min (M-FUP-1): poll Wati for known prospects' recent inbounds and open their
    # 24h windows / start cadences — the reliable window-feed (Wati's inbound webhook is
    # chatbot-suppressed). Bounded to known/watch-listed mobiles; inert until followups_enabled.
    "followup_inbound_poll": ("apps.followups.tasks.poll_inbound_windows", 5),
}


class Command(BaseCommand):
    help = "Idempotently register/update recurring django-q schedules (ADR-047 update mode)."

    def handle(self, *args, **options):
        from django_q.models import Schedule
        from django_q.tasks import schedule

        merged = {**SCHEDULES, **INTEGRATION_SCHEDULES}
        for name, (func, minutes) in merged.items():
            existing = Schedule.objects.filter(name=name).first()
            if existing is None:
                schedule(func, name=name, schedule_type=Schedule.MINUTES, minutes=minutes)
                self.stdout.write(self.style.SUCCESS(f"Scheduled '{name}' every {minutes} minutes."))
                continue
            if existing.func == func and existing.minutes == minutes:
                self.stdout.write(self.style.WARNING(f"Schedule '{name}' already exists — no-op."))
                continue
            old_func, old_minutes = existing.func, existing.minutes
            existing.func = func
            existing.minutes = minutes
            existing.save(update_fields=["func", "minutes"])
            self.stdout.write(self.style.SUCCESS(
                f"Updated '{name}': func {old_func!r} -> {func!r}, "
                f"minutes {old_minutes!r} -> {minutes!r}."
            ))
