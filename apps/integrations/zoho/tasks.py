"""Background tasks (django-q) for the Zoho WRITE leg — retry + backfill.

Why this exists: the lead is saved locally FIRST (capture-first, 06-API §5.3), and
the Zoho upsert is a mirror. Before this module a Zoho outage logged the failure and
left the lead local-only forever — Ashok would never see it. That is silent data
loss from the operator's point of view, even though nothing was technically dropped.

The flow:
  1. capture_lead() saves locally, then on_commit -> enqueue_upsert(lead_id).
     The form submit NEVER waits on Zoho (also removes Zoho latency from the request).
  2. upsert_lead_task() attempts the upsert:
       success -> synced + zoho_lead_id + zoho_synced_at
       failure -> attempts += 1; pending (retry later) or failed (attempts exhausted)
  3. backfill_unsynced() (scheduled) re-enqueues pending|failed leads with
     attempts < max, oldest first — so anything stranded during an outage lands
     once Zoho recovers.

Idempotency is structural, not bookkeeping: the write is an upsert keyed on the
bare-10-digit mobile, so replaying a task can only ever UPDATE the same Zoho lead —
it can never twin. That is what makes an aggressive retry safe.

Flag-off/demo: get_zoho_adapter() returns the log-only adapter, so the task runs
end-to-end offline with zero network. In sync mode (Q_CLUSTER sync=True, the
dev/CI/demo default) it executes inline.

Guardrail #2: this is the WRITE leg. It NEVER sets account/conversion status —
that comes only from the Zoho inbound webhook.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Max
from django.utils import timezone
from django_q.tasks import async_task

from apps.integrations.zoho.adapter import get_zoho_adapter, gorefer_reference_for

logger = logging.getLogger("gorefer.zoho.tasks")

# Bounded retry: stop re-attempting a lead that keeps failing, so a permanently
# broken record (e.g. a field Zoho rejects) cannot spin forever. It stays `failed`
# and VISIBLE in the admin rather than silently retrying into the void.
MAX_SYNC_ATTEMPTS = 5

# How many stranded leads one sweep re-enqueues. Bounded so a long outage's backlog
# drains steadily instead of stampeding Zoho the moment it recovers.
BACKFILL_BATCH_SIZE = 50


def enqueue_upsert(lead_id: int) -> None:
    """Enqueue the Zoho upsert for one lead (runs inline when Q_CLUSTER sync=True)."""
    async_task("apps.integrations.zoho.tasks.upsert_lead_task", lead_id)


def upsert_lead_task(lead_id: int) -> str:
    """Upsert one lead into Zoho; record sync state. Returns the resulting status.

    Safe to replay: the upsert dedups server-side on the bare-10-digit mobile.
    """
    from apps.referrals.models import Lead

    lead = Lead.objects.filter(id=lead_id, deleted_at__isnull=True).select_related(
        "prospect", "referral"
    ).first()
    if lead is None:
        return "noop"  # deleted/erased (DPDP) between enqueue and run
    if lead.zoho_sync_status == Lead.SYNC_SYNCED:
        return "noop"  # already mirrored — don't re-write on a duplicate enqueue

    prospect, referral = lead.prospect, lead.referral
    adapter = get_zoho_adapter()
    gref = gorefer_reference_for(referral)

    try:
        result = adapter.upsert_lead(
            payload={
                "name": prospect.name,
                "mobile": prospect.mobile,
                "email": prospect.email,
                "city": prospect.city,
                "referred_by": _referrer_client_id(referral),
            },
            gorefer_reference=gref,
        )
    except Exception as exc:
        return _record_failure(lead, exc)

    lead.zoho_sync_status = Lead.SYNC_SYNCED
    lead.zoho_synced_at = timezone.now()
    lead.zoho_last_error = ""
    if result.zoho_lead_id:
        lead.zoho_lead_id = result.zoho_lead_id
    if result.gorefer_reference:
        lead.gorefer_reference = result.gorefer_reference
    lead.save(update_fields=[
        "zoho_sync_status", "zoho_synced_at", "zoho_last_error",
        "zoho_lead_id", "gorefer_reference", "updated_at",
    ])
    logger.info(
        "Zoho sync ok: lead=%s action=%s zoho_lead_id=%s", lead.pk, result.action, result.zoho_lead_id
    )
    return Lead.SYNC_SYNCED


def _record_failure(lead, exc: Exception) -> str:
    """Increment attempts, record the error, and park the lead pending|failed."""
    from apps.referrals.models import Lead

    lead.zoho_sync_attempts += 1
    # Store the error text (truncated) for operator triage. It is an integration
    # error, not PII, and lives on the erasable Lead — never in the event log.
    lead.zoho_last_error = f"{type(exc).__name__}: {exc}"[:500]
    lead.zoho_sync_status = (
        Lead.SYNC_FAILED if lead.zoho_sync_attempts >= MAX_SYNC_ATTEMPTS else Lead.SYNC_PENDING
    )
    lead.save(update_fields=[
        "zoho_sync_attempts", "zoho_last_error", "zoho_sync_status", "updated_at",
    ])
    logger.warning(
        "Zoho sync failed: lead=%s attempt=%s/%s status=%s err=%s",
        lead.pk, lead.zoho_sync_attempts, MAX_SYNC_ATTEMPTS, lead.zoho_sync_status, exc,
    )
    return lead.zoho_sync_status


def backfill_unsynced() -> int:
    """Re-enqueue leads that never reached Zoho. Returns how many were enqueued.

    Scheduled (see `setup_schedules`). Picks pending|failed leads with attempts
    below the cap, OLDEST FIRST so the earliest-stranded lead is worked first, and
    bounded per sweep so a recovered Zoho isn't stampeded. Exhausted leads are left
    alone deliberately — they need a human, and the admin surfaces them.
    """
    from apps.referrals.models import Lead

    stranded = (
        Lead.objects.filter(
            zoho_sync_status__in=[Lead.SYNC_PENDING, Lead.SYNC_FAILED],
            zoho_sync_attempts__lt=MAX_SYNC_ATTEMPTS,
            deleted_at__isnull=True,
        )
        .order_by("created_at")[:BACKFILL_BATCH_SIZE]
    )
    lead_ids = list(stranded.values_list("id", flat=True))
    for lead_id in lead_ids:
        enqueue_upsert(lead_id)
    if lead_ids:
        logger.info("Zoho backfill: re-enqueued %d unsynced lead(s)", len(lead_ids))
    return len(lead_ids)


def _referrer_client_id(referral) -> str:
    identity = getattr(referral, "referral_identity", None)
    return identity.client_id if identity is not None else ""


def sync_referrer_names() -> dict:
    """READ-leg name sync: correct Customer names from Zoho Contacts (scheduled daily).

    The Explorer/leaderboard render names from the Customer table, but before this
    task nothing populated it except referrer login and demo seed — so referrers who
    never logged in showed "— name not on file —" even when Zoho knows them (live
    finding 2026-07-22: 10 of 12 identities nameless while the profile page fetched
    the same names live). Zoho stays the name truth-source: only MATCHED contacts
    with a Full_Name are written, and an unmatched ClientId stays honestly nameless.

    T-130 fix: an EXISTING non-empty Customer name is now CORRECTED when it
    disagrees with Zoho, not left alone. The old "existing non-empty names are
    never overwritten" rule was the exact reason this job silently skipped
    Customer id=2 (client_id DA1707) for its whole life: `seed_demo` had already
    written a non-empty demo name ("Amit Deshpande") into that row, so
    `not customer.first_name` was always False and the row was never touched even
    though live Zoho held the true name (Abhay Kumar) for that ClientId every run.
    Zoho is still the only writer here — GoRefer never fabricates or writes back —
    this just stops GoRefer's OWN stale local value from permanently winning over
    Zoho once it happens to be non-empty.

    Guardrail #2 untouched: reads Contacts only — never writes status/conversions.
    """
    from apps.integrations.zoho.read import get_zoho_read_adapter
    from apps.referrals.models import Customer, ReferralIdentity

    adapter = get_zoho_read_adapter()
    synced, corrected, unmatched, errors = 0, 0, 0, 0
    identities = (
        ReferralIdentity.objects.filter(deleted_at__isnull=True)
        .select_related("partner", "program", "tenant")
    )
    for identity in identities:
        try:
            contact = adapter.fetch_contact_by_client_id(client_id=identity.client_id)
        except Exception:
            errors += 1
            logger.warning("name-sync: Zoho fetch failed for %s", identity.client_id, exc_info=True)
            continue
        if not contact.matched or not (contact.full_name or "").strip():
            unmatched += 1
            continue
        first, _, last = contact.full_name.strip().partition(" ")
        customer, created = Customer.objects.get_or_create(
            tenant=identity.tenant,
            program=identity.program,
            client_id=identity.client_id,
            defaults={"partner": identity.partner, "first_name": first, "last_name": last},
        )
        if not created and (customer.first_name, customer.last_name) != (first, last):
            logger.info(
                "name-sync: correcting drifted name for %s: %r %r -> %r %r",
                identity.client_id, customer.first_name, customer.last_name, first, last,
            )
            customer.first_name, customer.last_name = first, last
            customer.save(update_fields=["first_name", "last_name"])
            corrected += 1
        synced += 1
    result = {"synced": synced, "corrected": corrected, "unmatched": unmatched, "errors": errors}
    logger.info("name-sync done: %s", result)
    return result


def sweep_customer_name_drift(*, tenant=None) -> dict:
    """SWEEP (T-130): read-only report of every Customer row whose GoRefer name
    disagrees with Zoho's `Referrers` module for the same client_id.

    Cross-references the already-synced `apps.campaigns.models.SyncedReferrer`
    table (T-126's hourly `zoho_audience_sync`, sourced from Zoho `Referrers`) —
    no extra Zoho call, so this is cheap enough to run ad hoc or as the first
    thing an operator does after a name-integrity incident. Read-only: it never
    writes. Correction for a flagged row lands on the next
    `zoho_sync_referrer_names` run (fixed under T-130 to overwrite drift).

    Also flags known `seed_demo` client_ids among the mismatches as
    `demo_seed_shadow` — those are the rows most likely to be a demo fixture that
    happens to share a real Zerodha client_id's 6-character shape (the DA1707
    incident this task exists for), so an operator can triage them first.
    """
    from apps.campaigns.models import SyncedReferrer
    from apps.referrals.management.commands.seed_demo import DEMO_CUSTOMERS, DEMO_REFERRERS
    from apps.referrals.models import Customer
    from apps.tenants.resolve import get_bootstrap_tenant

    tenant = tenant or get_bootstrap_tenant()
    demo_ids = {client_id for client_id, *_ in DEMO_REFERRERS} | set(DEMO_CUSTOMERS)

    zoho_names = {
        row.client_id: row.name.strip()
        for row in SyncedReferrer.objects.for_tenant(tenant).filter(active=True)
        if row.name.strip()
    }

    checked = 0
    rows = []
    for customer in Customer.objects.for_tenant(tenant).filter(deleted_at__isnull=True):
        checked += 1
        zoho_name = zoho_names.get(customer.client_id)
        if zoho_name is None:
            continue
        local_name = f"{customer.first_name} {customer.last_name}".strip()
        if local_name.lower() != zoho_name.lower():
            rows.append({
                "client_id": customer.client_id,
                "local_name": local_name,
                "zoho_name": zoho_name,
                "demo_seed_shadow": customer.client_id in demo_ids,
            })
    result = {"checked": checked, "mismatched": len(rows), "rows": rows}
    logger.info(
        "name-drift sweep: checked=%s mismatched=%s", result["checked"], result["mismatched"]
    )
    return result


# --- T-126 (W3): read-only referrer-audience sync ---------------------------------
# Cascade key (CLAUDE.md §6d/§6e): how often the audience actually re-syncs. The
# django-q SCHEDULE polls hourly (see apps.integrations.schedules) — same "poll
# often, gate on config" idiom as wa_engagement_report_daily — so an operator can
# change the cadence from the admin without touching a Schedule row or redeploying.
AUDIENCE_SYNC_FREQUENCY_HOURS_KEY = "zoho_audience_sync_frequency_hours"
AUDIENCE_SYNC_FREQUENCY_HOURS_DEFAULT = 24.0


def sync_referrer_audience(*, tenant=None) -> dict:
    """Fill/update `apps.campaigns.models.SyncedReferrer` from the Zoho `Referrers`
    module — decision ⑫'s READ-ONLY audience source for the messaging-campaign
    engine (T-124/T-125). Zoho stays data-in only: this task NEVER writes to Zoho
    and never touches account/conversion status (guardrail #2) — it only calls the
    read port's `fetch_referrer_audience()`.

    Behavior, in order:
      1. Inert no-op (logged, no port call at all) when `ENABLE_ZOHO_READ` is off —
         deliberately stricter than `get_crm_read_port()`'s usual live/LogOnly swap,
         because writing LogOnly's DEMO fixtures into the real audience table would
         silently corrupt who the engine messages.
      2. Inert no-op when the configured frequency window has not elapsed since the
         last successful sync (tracked via `max(SyncedReferrer.synced_at)` for the
         tenant — no extra state table needed).
      3. Upsert by (tenant, client_id): mobile normalized via `apps.common.phone`,
         `record_created_at` is the drip anchor (decision ⑪).
      4. Any currently-`active` row NOT present in this fetch is marked
         `active=False` (never deleted) — UNLESS the fetch hit its pagination cap
         (`ReferrerAudience.truncated`), in which case deactivation is skipped
         entirely this run (a partial fetch must never look like "referrer gone").
      5. Parity check (plan's verification section): synced-active count vs fetched
         count logged loudly on any mismatch — a silent audience shrink must never
         look like a clean sync.
    """
    from apps.common.phone import normalize_phone
    from apps.config.cascade import resolve
    from apps.config.integration_flags import ENABLE_ZOHO_READ, resolve_flag
    from apps.integrations.ports import get_crm_read_port
    from apps.tenants.resolve import get_bootstrap_tenant

    tenant = tenant or get_bootstrap_tenant()
    tid = getattr(tenant, "id", None)

    if not resolve_flag(ENABLE_ZOHO_READ):
        logger.info("audience-sync: ENABLE_ZOHO_READ off — inert no-op")
        return {"skipped": "ENABLE_ZOHO_READ off"}

    from apps.campaigns.models import SyncedReferrer

    frequency_hours = float(
        resolve(
            AUDIENCE_SYNC_FREQUENCY_HOURS_KEY, tenant_id=tid,
            default=AUDIENCE_SYNC_FREQUENCY_HOURS_DEFAULT,
        )
    )
    now = timezone.now()
    last_synced_at = SyncedReferrer.objects.for_tenant(tenant).aggregate(
        last=Max("synced_at")
    )["last"]
    if last_synced_at is not None and (now - last_synced_at) < timedelta(hours=frequency_hours):
        logger.info(
            "audience-sync: last run %s ago (< %sh window) — skipping",
            now - last_synced_at, frequency_hours,
        )
        return {"skipped": "frequency window not elapsed", "last_synced_at": last_synced_at.isoformat()}

    try:
        audience = get_crm_read_port().fetch_referrer_audience()
    except Exception:
        # Per-run try/except-and-log, matching the sibling read tasks in this module
        # (`sync_referrer_names` catches per-item; this is the whole-call equivalent
        # since there's only one fetch). Without this a Zoho transport blip (now a
        # raised RuntimeError per client.py's URLError/OSError handling) would crash
        # the whole scheduled job instead of degrading to "nothing synced this run".
        logger.warning("audience-sync: Zoho fetch failed", exc_info=True)
        return {"error": "zoho fetch failed"}

    fetched_client_ids: set[str] = set()
    created_n = updated_n = skipped_no_anchor = 0
    for row in audience.rows:
        if row.record_created_at is None:
            # No anchor means the drip ladder has nothing to compute offsets from —
            # skip rather than fabricate a "now" anchor that would misrepresent when
            # the referral record actually happened.
            skipped_no_anchor += 1
            continue
        fetched_client_ids.add(row.client_id)
        _, created = SyncedReferrer.objects.update_or_create(
            tenant=tenant, client_id=row.client_id,
            defaults=dict(
                mobile=normalize_phone(row.mobile), name=row.name, language=row.language,
                record_created_at=row.record_created_at, source="zoho",
                synced_at=now, active=True,
            ),
        )
        created_n += int(created)
        updated_n += int(not created)

    deactivated = 0
    if audience.truncated:
        logger.warning(
            "audience-sync: fetch hit the pagination cap (PARTIAL) — skipping the "
            "deactivation sweep this run so no referrer is wrongly marked gone"
        )
    else:
        deactivated = (
            SyncedReferrer.objects.for_tenant(tenant).filter(active=True)
            .exclude(client_id__in=fetched_client_ids)
            .update(active=False, synced_at=now)
        )

    fetched_count = len(fetched_client_ids)
    active_count = SyncedReferrer.objects.for_tenant(tenant).filter(active=True).count()
    parity_ok = audience.truncated or active_count == fetched_count
    if not parity_ok:
        logger.warning(
            "audience-sync PARITY MISMATCH: synced-active=%d fetched=%d (tenant=%s) — "
            "the audience should never silently shrink relative to what Zoho just returned",
            active_count, fetched_count, tid,
        )

    result = {
        "fetched": fetched_count, "created": created_n, "updated": updated_n,
        "deactivated": deactivated, "skipped_no_anchor": skipped_no_anchor,
        "truncated": audience.truncated, "synced_active_count": active_count,
        "parity_ok": parity_ok,
    }
    logger.info("audience-sync done: %s", result)
    return result
