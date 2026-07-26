"""Follow-up engine background tasks (django-q).

  - enqueue_followups(): on chat-open, insert one ScheduledFollowup per enabled rule step.
  - fire_due_followups(): the recurring sweep (registered in setup_schedules as
    `followup_sweep`, every 5 min). Selects due SCHEDULED rows, LOCKS each, runs the gate
    (services.evaluate_gate), and sends via the Wati adapter. Mirrors
    `apps.integrations.wati.tasks.reconcile_pending_deliveries` exactly — a recurring sweep
    over a due-table, the idiom the whole engine is built on.

In sync/demo mode (Q_CLUSTER sync=True, ENABLE_WATI_SEND=false) this runs inline against
the log-only adapter, so the whole flow is testable offline. Nothing sends until
`followups_enabled` is True for the tenant — checked at enqueue AND re-checked at fire time,
so a flag flipped OFF after scheduling cancels pending rows instead of sending them.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.events import vocab
from apps.events.models import Event
from apps.integrations.wati import status as st
from apps.integrations.wati.adapter import get_wati_adapter

from . import services
from .models import FollowupRule, ScheduledFollowup

logger = logging.getLogger("gorefer.followups.tasks")


def enqueue_followups(
    tenant_id: int,
    mobile: str,
    *,
    opened_at=None,
    prospect_id: int | None = None,
    source_event: str = "wati_inbound",
    pref_lang: str = "en",
) -> dict:
    """Insert one ScheduledFollowup per enabled rule at chat-open. Idempotent per window.

    dedupe_key = tenant|mobile|step|window-open — so a repeated enqueue for the SAME open
    creates nothing new (get_or_create on the unique key). Refuses when the flag is off or
    the contact is opted out.
    """
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        return {"created": 0, "reason": "no tenant"}
    if not services.followups_enabled(tenant_id):
        return {"created": 0, "reason": "disabled"}
    if services.is_opted_out(tenant, mobile):
        return {"created": 0, "reason": "opted_out"}

    opened_at = opened_at or timezone.now()
    rules = FollowupRule.objects.filter(tenant=tenant, enabled=True).order_by("order", "id")
    created = 0
    for rule in rules:
        fire_at = opened_at + timedelta(minutes=rule.offset_minutes)
        dkey = f"{tenant_id}|{mobile}|{rule.step_key}|{opened_at.isoformat()}"
        _, was_created = ScheduledFollowup.objects.get_or_create(
            dedupe_key=dkey,
            defaults=dict(
                tenant=tenant,
                rule=rule,
                prospect_id=prospect_id,
                mobile=mobile,
                pref_lang=pref_lang,
                fire_at=fire_at,
                window_opened_at=opened_at,
                status=ScheduledFollowup.STATUS_SCHEDULED,
                source_event=source_event,
            ),
        )
        if was_created:
            created += 1
    return {"created": created}


def fire_due_followups(limit: int = 200) -> dict:
    """Sweep due SCHEDULED follow-ups: lock each, run the gate, send/cancel/skip.

    Row-locked (select_for_update) per row so a concurrent CRUD edit can't race a send.
    Returns a per-outcome tally.
    """
    now = timezone.now()
    due_ids = list(
        ScheduledFollowup.objects.filter(
            status=ScheduledFollowup.STATUS_SCHEDULED, fire_at__lte=now
        )
        .order_by("fire_at")
        .values_list("id", flat=True)[:limit]
    )
    counts = {"sent": 0, "cancelled": 0, "skipped": 0, "failed": 0, "held": 0, "referrer_nudged": 0}
    for sid in due_ids:
        try:
            with transaction.atomic():
                # Lock ONLY this row (of=("self",)) — never the FollowupRule it points at,
                # so locking a due row can't block a rule edit.
                sf = (
                    ScheduledFollowup.objects.select_for_update(of=("self",))
                    .get(pk=sid)
                )
                if sf.status != ScheduledFollowup.STATUS_SCHEDULED:
                    continue  # already handled by a concurrent sweep / cancelled by CRUD
                decision, reason = services.evaluate_gate(sf, now)
                _apply(sf, decision, reason, now, counts)
        except Exception:
            # One bad row must never sink the whole sweep — log and move on.
            logger.warning("followup fire failed for id=%s", sid, exc_info=True)
    return counts


def _apply(sf: ScheduledFollowup, decision: str, reason: str, now, counts: dict) -> None:
    if decision == services.DEC_CANCEL:
        sf.status = ScheduledFollowup.STATUS_CANCELLED
        sf.reason = reason
        sf.save(update_fields=["status", "reason", "updated_at"])
        counts["cancelled"] += 1
        return
    if decision == services.DEC_SKIP:
        sf.status = ScheduledFollowup.STATUS_SKIPPED
        sf.reason = reason
        sf.save(update_fields=["status", "reason", "updated_at"])
        counts["skipped"] += 1
        return
    if decision == services.DEC_HOLD:
        # DON'T send now (quiet hours or min-gap); defer and stay SCHEDULED so a later
        # sweep sends it. compute_defer picks the earliest instant that is BOTH outside
        # quiet hours AND ≥ MIN_GAP after this contact's last send — so night steps can
        # never collapse into a same-minute burst.
        sf.fire_at = services.compute_defer(now, sf.tenant, sf.mobile, sf.tenant_id)
        sf.reason = reason
        sf.save(update_fields=["fire_at", "reason", "updated_at"])
        counts["held"] += 1
        return

    rule = sf.rule

    # doc 15 — resolve WHO this is before sending: role, language (from the existing
    # referrer_language rule), and the referral link to embed.
    from apps.referrals.recipient_identity import (
        ROLE_REFERRER,
        nudge_link_for,
        resolve_recipient,
    )

    identity = resolve_recipient(sf.tenant, sf.mobile)
    if identity.role == ROLE_REFERRER:
        # A referrer whose OWN mobile is in the cadence must never get the prospect's
        # "your account is still pending" copy (wrong audience). The referrer-oriented
        # nudge (doc 15 §6.1) is fired the other way — off an idle PROSPECT's cadence — below.
        sf.status = ScheduledFollowup.STATUS_SKIPPED
        sf.reason = "referrer recipient — prospect nudge suppressed"
        sf.save(update_fields=["status", "reason", "updated_at"])
        counts["skipped"] += 1
        return

    lang = identity.lang or sf.pref_lang

    adapter = get_wati_adapter()
    if decision == services.DEC_SEND_SESSION:
        message = services.body_for(rule, lang)
        if "{link}" in message:
            message = message.replace("{link}", nudge_link_for(identity, tenant_id=sf.tenant_id))
        result = adapter.send_session_text(to=sf.mobile, message=message)
    else:  # DEC_SEND_TEMPLATE
        result = adapter.send_template(
            to=sf.mobile, template=rule.template_name, params={"role": "prospect"}
        )

    if result.accepted:
        sf.status = ScheduledFollowup.STATUS_SENT
        sf.sent_at = now
        sf.reason = reason
        counts["sent"] += 1
        _emit_funnel_event(sf, decision)
        # doc 15 §6.1 — at the configured step, ALSO nudge this idle prospect's referrer
        # (if we know their phone) so they can push their friend personally. Flag-gated.
        _maybe_referrer_nudge(sf, identity, counts)
    elif result.raw_status == st.STATUS_BLOCKED:
        # Fail-closed allowlist blocked it — a suppression, not a delivery failure.
        sf.status = ScheduledFollowup.STATUS_SKIPPED
        sf.reason = "recipient not in Wati allowlist (fail-closed)"
        counts["skipped"] += 1
    else:
        # Accepted != delivered elsewhere; here 'not accepted' is a real send failure.
        sf.status = ScheduledFollowup.STATUS_FAILED
        sf.reason = "send not accepted"
        counts["failed"] += 1
    sf.save(update_fields=["status", "sent_at", "reason", "updated_at"])


def poll_inbound_windows(limit: int = 50) -> dict:
    """Poll Wati for known prospects' recent inbounds → open windows / start cadences.

    The reliable window-feed trigger (Wati's inbound webhook is chatbot-suppressed and its
    real-time conversation-list API isn't exposed). Because a follow-up can only be SENT to a
    prospect whose mobile we already know, the candidate set is bounded and knowable:
      - a per-AP config watch-list (`followup_poll_watch_mobiles`, comma-separated), plus
      - recent Prospect mobiles (last 3 days).
    For each, read the newest customer-inbound time (adapter.get_latest_inbound_at, the
    confirmed real-time getMessages endpoint); if it's newer than what we've recorded, call
    record_inbound → stamp the window + (on a fresh 24h open) enqueue the cadence. Runs on the
    `followup_inbound_poll` schedule. Inert unless `followups_enabled` (record_inbound re-checks).
    """
    from datetime import timedelta

    from apps.common.phone import normalize_phone
    from apps.config.cascade import resolve
    from apps.integrations.wati.webhook import record_inbound
    from apps.referrals.models import Prospect
    from apps.tenants.models import Tenant

    from .models import FollowupWindow

    counts = {"checked": 0, "opened": 0, "enqueued": 0}
    for tenant in Tenant.objects.filter(is_active=True):
        if not services.followups_enabled(tenant.id):
            continue
        adapter = get_wati_adapter()
        mobiles: set[str] = set()
        try:
            raw = resolve("followup_poll_watch_mobiles", tenant_id=tenant.id, default="")
        except Exception:
            raw = ""
        for m in str(raw or "").split(","):
            n = normalize_phone(m)
            if n:
                mobiles.add(n)
        cutoff = timezone.now() - timedelta(days=3)
        for m in (
            Prospect.objects.filter(tenant=tenant, created_at__gte=cutoff, deleted_at__isnull=True)
            .values_list("mobile", flat=True)[:limit]
        ):
            n = normalize_phone(m)
            if n:
                mobiles.add(n)

        for mobile in list(mobiles)[:limit]:
            counts["checked"] += 1
            try:
                latest = adapter.get_latest_inbound_at(mobile)
            except Exception:
                logger.warning("poll: get_latest_inbound_at failed", exc_info=True)
                continue
            if latest is None:
                continue
            win = FollowupWindow.objects.filter(tenant=tenant, mobile=mobile).first()
            if win is not None and win.last_inbound_at is not None and latest <= win.last_inbound_at:
                continue  # already recorded this inbound — nothing new
            res = record_inbound(tenant, mobile, latest)
            if res.get("opened_fresh"):
                counts["opened"] += 1
            counts["enqueued"] += res.get("enqueued", 0)
    return counts


def _emit_funnel_event(sf: ScheduledFollowup, decision: str) -> None:
    """Emit a PII-free funnel event so a follow-up send is observable (Constitution §5).

    Deliberately carries NO mobile/name — the immutable event log never holds PII (#16).
    """
    try:
        Event.objects.create(
            tenant=sf.tenant,
            event_type=vocab.NOTIFICATION,
            source=vocab.SRC_WATI,
            user_type="system",
            metadata={"kind": "followup", "step": sf.rule.step_key, "decision": decision},
        )
    except Exception:
        logger.warning("followup funnel event emit failed", exc_info=True)


def _maybe_referrer_nudge(sf: ScheduledFollowup, identity, counts: dict) -> None:
    """doc 15 §6.1 — nudge an idle prospect's referrer so they can push their friend directly.

    Fires ONLY when: the flag is on, this is the configured step, and GoRefer KNOWS the
    referrer's phone (a Customer row — never guess). Template send (the referrer's own 24h
    window is usually closed). One nudge per idle prospect (implicit: it rides a single
    cadence step). Fully wrapped — a referrer-nudge failure must never sink the prospect
    send that already succeeded.
    """
    from apps.config.cascade import resolve
    from apps.referrals.models import Customer
    from apps.referrals.recipient_identity import nudge_link_for, prospect_descriptor

    tid = sf.tenant_id
    try:
        on = resolve("followup_referrer_nudge_on", tenant_id=tid, default=False)
        if not (on is True or str(on).strip().lower() in {"1", "true", "yes", "on"}):
            return
        step = str(resolve("followup_referrer_nudge_step", tenant_id=tid, default="nudge_12h")).strip()
        if sf.rule.step_key != step:
            return
        if not identity.referrer_mobile or not identity.referrer_client_id:
            return  # never guess a referrer's phone

        cust = (
            Customer.objects.filter(
                tenant=sf.tenant, client_id=identity.referrer_client_id, deleted_at__isnull=True
            )
            .exclude(mobile="")
            .first()
        )
        ref_name = (f"{cust.first_name} {cust.last_name}".strip() if cust else "") or "there"
        descr = prospect_descriptor(sf.tenant, sf.mobile)
        lang = identity.lang or "en"

        # The link comes from `nudge_link_for` — the ONE canonical builder — never from the
        # template body. The body used to hardcode `gorefer.in/r/{{3}}?s=wa`, i.e. the legacy
        # M11 query form, while the canonical form is the channel PATH `/r/wa/{client_id}`
        # (B1 / Q-M-CHANNELPATH). `?s=` exists only because a WhatsApp URL *button* requires
        # its variable LAST so nothing can follow it — a constraint that does not apply to a
        # message BODY. Passing the whole link as one variable means a template can never
        # again disagree with the builder about URL shape.
        link = nudge_link_for(identity, tenant_id=tid)
        if not link:
            # link_mode="none" — the operator has switched embedded links off. A nudge whose
            # entire point is "share your link again" is meaningless without one, and a blank
            # template variable is rejected by Meta, so skip rather than send something broken.
            return

        tmpl = str(
            resolve(
                f"followup_referrer_nudge_template_{lang}",
                tenant_id=tid,
                default=f"gorefer_referrer_prospect_pending_{lang}_2026_07_26_v5",
            )
        ).strip()

        adapter = get_wati_adapter()
        result = adapter.send_template(
            to=identity.referrer_mobile,
            template=tmpl,
            params={
                "template_params": [
                    {"name": "name", "value": ref_name},
                    {"name": "prospect", "value": descr},
                    # position 3 is the FULL link (v5+), not a bare client_id (v3/v4)
                    {"name": "link", "value": link},
                ]
            },
        )
        if result.accepted:
            counts["referrer_nudged"] = counts.get("referrer_nudged", 0) + 1
            try:
                Event.objects.create(
                    tenant=sf.tenant,
                    event_type=vocab.NOTIFICATION,
                    source=vocab.SRC_WATI,
                    user_type="system",
                    metadata={"kind": "referrer_nudge", "step": sf.rule.step_key},
                )
            except Exception:
                logger.warning("referrer-nudge funnel event emit failed", exc_info=True)
    except Exception:
        logger.warning("referrer-nudge failed for sf=%s", getattr(sf, "pk", None), exc_info=True)
