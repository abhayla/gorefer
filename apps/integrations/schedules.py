"""Boundary schedule fragment (ADR-047 §3) — the vendor half of the schedule registry.

`setup_schedules` aggregates this dict with its own domain entries. Living here (a
pure-data dict of dotted paths, no vendor module imports) keeps
`apps/events/management/commands/setup_schedules.py` clear of `apps.integrations.
wati|zoho` references without hiding the registry: the paths below are strings, so
this module never actually imports `wati`/`zoho` code.

Paths + minutes are byte-identical to what `setup_schedules.SCHEDULES` held before
this move (ADR-047 §1 move-freeze) — a Schedule row pointing at one of these names
must resolve to the same dotted path it did previously.
"""
from __future__ import annotations

# name -> (dotted task path, every N minutes)
INTEGRATION_SCHEDULES = {
    # Every 10 min: frequent enough that a recovered Zoho drains the backlog promptly,
    # sparse enough that a long outage doesn't hammer it. Each sweep is bounded.
    "zoho_backfill_unsynced": ("apps.integrations.zoho.tasks.backfill_unsynced", 10),
    "zoho_reconcile_conversions": ("apps.integrations.zoho.reconcile.reconcile_conversions", 15),
    # Hourly: burnt wax-seal nonces past the freshness window are dead weight (a nonce
    # that old already fails the timestamp check), so purging them can't enable a
    # replay — it just stops the table growing forever.
    "zoho_purge_expired_nonces": ("apps.integrations.zoho.waxseal.purge_expired_nonces", 60),
    # Every 15 min (Fable5 H4): re-poll WATI notifications stranded at ACCEPTED so a
    # delivery that wasn't terminal at first read gets finalized (or expired), not left
    # 'accepted' forever — otherwise the funnel silently under-reports delivery.
    "wati_reconcile_pending": ("apps.integrations.wati.tasks.reconcile_pending_deliveries", 15),
    # Daily: fill Customer names from Zoho Contacts (READ leg) so the Explorer and
    # leaderboard show real referrer names instead of "name not on file" for anyone
    # Zoho knows. Unmatched ClientIds stay honestly nameless; never overwrites.
    "zoho_sync_referrer_names": ("apps.integrations.zoho.tasks.sync_referrer_names", 1440),
    # Hourly (60 min, T-032): the WA engagement report task fires every hour but only
    # does real work during a tenant's configured `wa_engagement_report_hour_ist` —
    # the minute-interval scheduler can't express "once daily at hour H" directly, so
    # the hour gate lives inside run_scheduled_report (same "poll often, gate on
    # config" idiom as followup_sweep gating on quiet hours). Inert per-tenant until
    # `wa_engagement_report_enabled` is on (re-checked at fire time).
    "wa_engagement_report_daily": ("apps.integrations.wati.engagement.run_scheduled_report", 60),
}
