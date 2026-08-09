"""Records-link operator send (T-057) — core of the `send_records_links` command.

Sends the approved UTILITY `[Referral Records]` WhatsApp template to an explicit list
of referrer client_ids. Mirrors the accepted -> terminal-status discipline
`wati/tasks.py` already established (doc-08 A3): a submit is recorded ACCEPTED, then
the SAME messaging port is asked for the terminal status before a send counts as
delivered — never HTTP-200-as-success.

Mobile is resolved LIVE from the vendor-neutral CRM READ port (ClientId -> Mobile) —
never from GoRefer's own Customer record — because this command exists specifically to
reach referrers GoRefer itself may hold no phone for. Token/name/record_date reuse the
SAME internal helper the mint API (`api/records_tokens.py`) already uses
(`resolve_link_details`), so a link handed out here can never disagree with one minted
through that endpoint, and this module never HTTP-calls its own mint API.

Dry-run (the default) runs every gate — cap, dedupe, opt-out, mobile resolution — and
stops short of only the adapter call + the writes that record a real send, so the
preview is an honest prediction of what `--send` would do.
"""
from __future__ import annotations

import logging

from django.utils import timezone

from api.records_tokens import resolve_link_details
from apps.common.masking import mask_mobile
from apps.common.phone import normalize_phone
from apps.config.cascade import resolve as resolve_config
from apps.config.preferences import (
    RECORDS_LINK_SEND_MAX_PER_RUN,
    RECORDS_LINK_SEND_MAX_PER_RUN_DEFAULT,
    RECORDS_LINK_SEND_MIN_GAP_DAYS,
    RECORDS_LINK_SEND_MIN_GAP_DAYS_DEFAULT,
    RECORDS_LINK_TEMPLATE_EN,
    RECORDS_LINK_TEMPLATE_EN_DEFAULT,
)
from apps.events import vocab
from apps.events.models import Event
from apps.integrations import delivery_status as ds
from apps.integrations.models import Notification
from apps.integrations.ports import get_crm_read_port, get_messaging_port
from apps.integrations.wati import status as wati_status
from apps.referrals.validators import InvalidClientId, validate_client_id
from apps.tenants.resolve import get_current_tenant

logger = logging.getLogger("gorefer.integrations.records_link_send")

#: `Event.metadata["kind"]` tag for this send family — the dedupe query keys on it.
EVENT_KIND = "records_link"

OUTCOME_SENT = "sent"
OUTCOME_WOULD_SEND = "would_send"
OUTCOME_SKIPPED = "skipped"
OUTCOME_FAILED = "failed"


class SendRefused(RuntimeError):
    """Raised when `--send` is requested but the gating flags are not both on."""


def _template_name(tenant_id: int | None) -> str:
    value = str(
        resolve_config(
            RECORDS_LINK_TEMPLATE_EN, tenant_id=tenant_id, default=RECORDS_LINK_TEMPLATE_EN_DEFAULT
        )
    ).strip()
    return value or RECORDS_LINK_TEMPLATE_EN_DEFAULT


def _max_per_run(tenant_id: int | None) -> int:
    try:
        cap = int(
            resolve_config(
                RECORDS_LINK_SEND_MAX_PER_RUN, tenant_id=tenant_id,
                default=RECORDS_LINK_SEND_MAX_PER_RUN_DEFAULT,
            )
        )
    except (TypeError, ValueError):
        return RECORDS_LINK_SEND_MAX_PER_RUN_DEFAULT
    return cap if cap > 0 else RECORDS_LINK_SEND_MAX_PER_RUN_DEFAULT


def _min_gap_days(tenant_id: int | None) -> int:
    try:
        days = int(
            resolve_config(
                RECORDS_LINK_SEND_MIN_GAP_DAYS, tenant_id=tenant_id,
                default=RECORDS_LINK_SEND_MIN_GAP_DAYS_DEFAULT,
            )
        )
    except (TypeError, ValueError):
        return RECORDS_LINK_SEND_MIN_GAP_DAYS_DEFAULT
    return days if days >= 0 else RECORDS_LINK_SEND_MIN_GAP_DAYS_DEFAULT


def _recently_sent(tenant, client_id: str, tenant_id: int | None) -> bool:
    """True when a records-link send event for this client_id landed within the gap."""
    cutoff = timezone.now() - timezone.timedelta(days=_min_gap_days(tenant_id))
    return Event.objects.for_tenant(tenant).filter(
        event_type=vocab.NOTIFICATION,
        source=vocab.SRC_WATI,
        metadata__kind=EVENT_KIND,
        metadata__client_id=client_id,
        timestamp__gte=cutoff,
    ).exists()


def _emit_event(tenant, client_id: str, template: str, outcome: str) -> None:
    """PII-free, TOKEN-free funnel event (T-051 precedent: the token never enters the
    immutable event log). client_id is not PII — it is already public (CLAUDE.md §4)."""
    try:
        Event.objects.create(
            tenant=tenant,
            event_type=vocab.NOTIFICATION,
            source=vocab.SRC_WATI,
            user_type="system",
            metadata={"kind": EVENT_KIND, "client_id": client_id, "template": template, "outcome": outcome},
        )
    except Exception:
        logger.warning("records-link funnel event emit failed for client_id=%s", client_id, exc_info=True)


def _item(client_id: str, *, mobile: str = "", template: str, record_date: str = "",
          outcome: str, reason: str = "") -> dict:
    return {
        "client_id": client_id,
        "mobile": mobile,
        "template": template,
        "record_date": record_date,
        "outcome": outcome,
        "reason": reason,
    }


def _process_one(*, tenant, tenant_id, raw_client_id: str, template: str, dry_run: bool,
                 cap: int, dispatched_so_far: int, crm_read, messaging) -> dict:
    try:
        client_id = validate_client_id((raw_client_id or "").strip())
    except InvalidClientId as exc:
        return _item((raw_client_id or "")[:64], template=template, outcome=OUTCOME_SKIPPED,
                     reason=f"invalid client_id: {exc}")

    if dispatched_so_far >= cap:
        return _item(client_id, template=template, outcome=OUTCOME_SKIPPED,
                     reason=f"per-run cap reached ({cap})")

    if _recently_sent(tenant, client_id, tenant_id):
        return _item(client_id, template=template, outcome=OUTCOME_SKIPPED,
                     reason="records link already sent within the min-gap window")

    details = resolve_link_details(tenant, client_id)
    if details.get("error"):
        return _item(client_id, template=template, outcome=OUTCOME_SKIPPED, reason=details["error"])
    record_date = details.get("record_date", "")
    name = details.get("name") or "there"
    token = details.get("token") or ""

    contact = crm_read.fetch_contact_by_client_id(client_id=client_id)
    mobile = normalize_phone(getattr(contact, "mobile", None))
    if not mobile:
        return _item(client_id, template=template, record_date=record_date, outcome=OUTCOME_SKIPPED,
                     reason="no mobile on file (CRM read)")
    masked = mask_mobile(mobile)

    from apps.followups.services import is_opted_out  # local import: avoid app-loading cycles

    if is_opted_out(tenant, mobile):
        return _item(client_id, mobile=masked, template=template, record_date=record_date,
                     outcome=OUTCOME_SKIPPED, reason="recipient opted out")

    if dry_run:
        return _item(client_id, mobile=masked, template=template, record_date=record_date,
                     outcome=OUTCOME_WOULD_SEND)

    return _send_and_record(
        tenant=tenant, client_id=client_id, mobile=mobile, masked=masked, template=template,
        record_date=record_date, name=name, token=token, messaging=messaging,
    )


def _send_and_record(*, tenant, client_id: str, mobile: str, masked: str, template: str,
                     record_date: str, name: str, token: str, messaging) -> dict:
    idem = f"records_link:{template}:{client_id}:{timezone.now().isoformat()}"
    n = Notification.objects.create(
        tenant=tenant,
        recipient_role="referrer",
        recipient_mobile=mobile,
        template=template,
        category="UTILITY",
        template_params=[
            {"name": "name", "value": name},
            {"name": "record_date", "value": record_date},
            {"name": "token", "value": token},
        ],
        idempotency_key=idem,
        status="queued",
    )

    result = messaging.send_template(
        to=mobile, template=template,
        params={
            "template_params_named": True,
            "template_params": [
                {"name": "name", "value": name},
                {"name": "record_date", "value": record_date},
                {"name": "token", "value": token},
            ],
        },
    )
    n.adapter_kind = getattr(messaging, "kind", "")

    if result.raw_status == wati_status.STATUS_BLOCKED:
        n.status = "skipped"
        n.skip_reason = "recipient not in WATI allowlist (fail-closed)"
        n.save(update_fields=["status", "skip_reason", "adapter_kind", "updated_at"])
        _emit_event(tenant, client_id, template, "blocked")
        return _item(client_id, mobile=masked, template=template, record_date=record_date,
                     outcome=OUTCOME_SKIPPED, reason=n.skip_reason)

    n.provider_message_id = result.provider_message_id or ""
    n.status = "accepted"
    n.save(update_fields=["provider_message_id", "status", "adapter_kind", "updated_at"])

    if not result.accepted:
        n.status = "failed"
        n.save(update_fields=["status", "updated_at"])
        _emit_event(tenant, client_id, template, "failed")
        return _item(client_id, mobile=masked, template=template, record_date=record_date,
                     outcome=OUTCOME_FAILED, reason="send not accepted")

    delivery = messaging.get_message_status(
        provider_message_id=n.provider_message_id, recipient_mobile=mobile, template=template,
    )
    if ds.supersedes(n.status, delivery.status):
        n.status = delivery.status
        if delivery.status == wati_status.STATUS_FAILED:
            n.meta_error_code = delivery.meta_error_code
            n.failure_classification = ds.classify_failure(delivery.meta_error_code)
        n.save(update_fields=["status", "meta_error_code", "failure_classification", "updated_at"])

    _emit_event(tenant, client_id, template, n.status)
    if n.status == wati_status.STATUS_FAILED:
        return _item(client_id, mobile=masked, template=template, record_date=record_date,
                     outcome=OUTCOME_FAILED, reason=n.failure_classification or "delivery failed")
    return _item(client_id, mobile=masked, template=template, record_date=record_date,
                 outcome=OUTCOME_SENT, reason=n.status)


def send_records_links(client_ids: list[str], *, dry_run: bool = True) -> dict:
    """Send (or preview) the records-link template to an explicit client_id list.

    Real sends require BOTH `ENABLE_WATI_SEND` (resolved, admin-override-aware) AND
    `flags.ENABLE_RECORDS_LINK` — checked ONCE up front so a mid-run flag flip can
    never produce a half-sent, half-refused batch. Dry-run needs neither: it never
    calls the messaging port.
    """
    tenant = get_current_tenant()
    tenant_id = getattr(tenant, "id", None)
    template = _template_name(tenant_id)
    cap = _max_per_run(tenant_id)

    if not dry_run:
        # Local imports (not top-of-module) so tests can monkeypatch the resolver /
        # the frozen flags snapshot in place — the same convention `wati/adapter.py`
        # and `zoho/read.py` use for their own flag reads.
        from apps.config.integration_flags import ENABLE_WATI_SEND, resolve_flag
        from gorefer.flags import flags

        if not (resolve_flag(ENABLE_WATI_SEND, tenant_id=tenant_id) and flags.ENABLE_RECORDS_LINK):
            raise SendRefused(
                "refused: --send requires BOTH ENABLE_WATI_SEND and ENABLE_RECORDS_LINK to be on"
            )

    crm_read = get_crm_read_port()
    messaging = None if dry_run else get_messaging_port()

    items: list[dict] = []
    dispatched = 0
    for raw_client_id in client_ids:
        item = _process_one(
            tenant=tenant, tenant_id=tenant_id, raw_client_id=raw_client_id, template=template,
            dry_run=dry_run, cap=cap, dispatched_so_far=dispatched, crm_read=crm_read,
            messaging=messaging,
        )
        items.append(item)
        if item["outcome"] in (OUTCOME_SENT, OUTCOME_WOULD_SEND):
            dispatched += 1

    tally = {"sent": 0, "would_send": 0, "skipped": 0, "failed": 0}
    for item in items:
        tally[item["outcome"]] = tally.get(item["outcome"], 0) + 1

    return {"dry_run": dry_run, "template": template, "items": items, **tally}
