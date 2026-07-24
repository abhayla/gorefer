"""Configure an AP's follow-up cadence (idempotent).

Default = the owner's spec: a SESSION nudge **every 3 hours through the 24h window**
(so +3h, +6h, … +21h — the +24h boundary is excluded because the window closes then).
Quiet hours (23:00–06:00 IST, no sends) are enforced by the send gate at fire time, not
by the schedule here, so a step that lands at night is deferred to 06:00 IST automatically.

This seeds `FollowupRule` rows only — it deliberately does NOT flip `followups_enabled`
(that go-live switch stays a separate, explicit operator action).

    python manage.py seed_followup_cadence
    python manage.py seed_followup_cadence --interval-hours 3 --horizon-hours 24 --tenant pifs
    python manage.py seed_followup_cadence --stop-on-reply false   # keep firing after a reply (test mode)
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.followups.models import FollowupRule
from apps.tenants.models import Tenant

DEFAULT_BODY_EN = (
    "Hi! Just checking in on your Zerodha account opening — reply here if you'd like a hand "
    "completing it, and we'll help you finish in a couple of minutes."
)


def _as_bool(raw) -> bool:
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


class Command(BaseCommand):
    help = "Idempotently seed an AP's follow-up cadence (default: every 3h through 24h, session)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="pifs", help="Tenant slug (default: pifs).")
        parser.add_argument("--interval-hours", type=int, default=3)
        parser.add_argument("--horizon-hours", type=int, default=24)
        parser.add_argument("--stop-on-reply", default="true",
                            help="Cancel remaining steps once the contact replies (default true).")
        parser.add_argument("--body-en", default=DEFAULT_BODY_EN)

    def handle(self, *args, **opts):
        tenant = Tenant.objects.filter(slug=opts["tenant"]).first()
        if tenant is None:
            raise CommandError(f"No tenant with slug '{opts['tenant']}'. Run seed_program first.")

        interval = opts["interval_hours"]
        horizon = opts["horizon_hours"]
        if interval <= 0 or horizon <= 0:
            raise CommandError("--interval-hours and --horizon-hours must be positive.")

        stop_on_reply = _as_bool(opts["stop_on_reply"])
        # Steps strictly INSIDE the window: interval, 2*interval, … < horizon.
        hours = list(range(interval, horizon, interval))
        if not hours:
            raise CommandError("No steps fit — interval must be smaller than horizon.")

        created = updated = 0
        for order, h in enumerate(hours, start=1):
            _, was_created = FollowupRule.objects.update_or_create(
                tenant=tenant,
                step_key=f"nudge_{h}h",
                defaults=dict(
                    offset_minutes=h * 60,
                    channel=FollowupRule.CHANNEL_SESSION,
                    template_name="",
                    body_en=opts["body_en"],
                    body_hi="",
                    enabled=True,
                    only_if_window_open=True,   # session-only; no out-of-window template fallback
                    stop_on_reply=stop_on_reply,
                    order=order,
                ),
            )
            created += was_created
            updated += (not was_created)

        self.stdout.write(self.style.SUCCESS(
            f"Cadence for '{tenant.slug}': {len(hours)} steps every {interval}h through {horizon}h "
            f"({created} created, {updated} updated) — session, stop_on_reply={stop_on_reply}."
        ))
        self.stdout.write(
            "Quiet hours 23:00–06:00 IST are enforced at send time (deferred to 06:00 IST). "
            "This did NOT enable sending — set `followups_enabled` true for the tenant to go live."
        )
