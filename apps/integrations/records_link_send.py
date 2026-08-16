"""Per-recipient token-carrying WhatsApp sends (T-057 records link, T-073 invite).

One send path, two template FAMILIES. Both carry a `{{token}}` that only GoRefer can
compute, so both must be sent **one recipient at a time, by this code** — never by a
Wati dashboard broadcast, which fills an unknown variable from a contact attribute
nobody sets and ships `https://gorefer.in/hub/` (blank token, dead link) with a green
delivered tick. That failure is what `apps.integrations.computed_vars` now makes
impossible; this module is its first consumer.

  * `send_records_links()` — the approved UTILITY `[Referral Records]` template.
  * `send_invite_links()`  — the referral INVITE template (T-073). CAPABILITY ONLY:
    the configured invite template is a DRAFT at Meta today, and a real send refuses
    an unapproved template, so landing this fires no blast.

Shared discipline, unchanged from T-057:

  * accepted -> terminal-status (doc-08 A3): a submit is recorded ACCEPTED, then the
    SAME messaging port is asked for the terminal status. HTTP-200 is never success.
  * mobile is resolved LIVE from the vendor-neutral CRM READ port (ClientId ->
    Mobile) — never from GoRefer's own Customer record — because these sends exist
    to reach referrers GoRefer itself may hold no phone for.
  * token/name/record_date come from the SAME internal helper the mint API uses
    (`api.records_tokens.resolve_link_details`), so a link handed out here can never
    disagree with one minted through that endpoint or shown on the hub. This module
    never HTTP-calls its own mint API and never re-implements minting.
  * dry-run (the default) runs every gate — approval, cap, dedupe, opt-out, mobile,
    computed-variable — and stops short of only the adapter call and the writes, so
    the preview is an honest prediction of what `--send` would do.

The token is never printed and never enters the immutable event log (T-051): a log
outlives an erasure request, and a logged token is a live credential.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from django.utils import timezone

from api.records_tokens import resolve_link_details
from apps.common.masking import mask_mobile
from apps.common.phone import normalize_phone
from apps.config.cascade import resolve as resolve_config
from apps.config.preferences import (
    INVITE_SEND_MAX_PER_RUN,
    INVITE_SEND_MAX_PER_RUN_DEFAULT,
    INVITE_SEND_MIN_GAP_DAYS,
    INVITE_SEND_MIN_GAP_DAYS_DEFAULT,
    INVITE_TEMPLATE_EN,
    INVITE_TEMPLATE_EN_DEFAULT,
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
from apps.integrations.computed_vars import MissingComputedVar, assert_computed_vars_filled
from apps.integrations.models import Notification
from apps.integrations.ports import SendRefused, get_crm_read_port, get_messaging_port
from apps.integrations.wati import status as wati_status
from apps.referrals.validators import InvalidClientId, validate_client_id
from apps.tenants.resolve import get_current_tenant

logger = logging.getLogger("gorefer.integrations.records_link_send")

#: `Event.metadata["kind"]` tag for the records-link family — the dedupe query keys on it.
EVENT_KIND = "records_link"
#: …and for the invite family. A separate kind so the two min-gaps never see each other.
EVENT_KIND_INVITE = "referral_invite"

OUTCOME_SENT = "sent"
OUTCOME_WOULD_SEND = "would_send"
OUTCOME_SKIPPED = "skipped"
OUTCOME_FAILED = "failed"


#: Re-exported so existing callers importing `SendRefused` from this module keep
#: working — the exception itself now lives at `apps.integrations.ports` (T-161 pt
#: 15), because the template-approval gate that used to raise it here moved into
#: `GuardedMessagingPort`, the ONE place every send path (not just this module's)
#: now inherits it from. `_assert_flags_on` below still raises the SAME exception
#: for the (unrelated) flags-off gate.


# --------------------------------------------------------------------------- families


@dataclass(frozen=True)
class SendFamily:
    """One template family's config keys, event tag and parameter shape.

    Everything that differs between the records link and the invite lives here, so
    the send path itself — gates, dedupe, accepted->terminal recording — is written
    once and cannot drift between the two.
    """

    key: str                      # short label used in messages / idempotency keys
    event_kind: str               # Event.metadata["kind"] (also the dedupe key)
    template_key: str
    template_default: str
    cap_key: str
    cap_default: int
    gap_key: str
    gap_default: int
    category: str                 # Meta category recorded on the Notification
    build_params: Callable[[str, dict], list]   # (client_id, details) -> [{name,value}]
    link_flag: str                # name of the `flags.*` attribute gating this family's link


def _records_params(client_id: str, details: dict) -> list:
    # T-129: the "token" param is the RECORDS URL-button variable. It now carries the
    # raw client_id, not the signed token — a colon (always present in a signed
    # token) makes Meta silently blank a URL-button value (proven live 2026-08-14).
    # The param name stays "token" so the computed_vars registry (which keys on this
    # exact name) needs no change — only the value source moved.
    return [
        {"name": "name", "value": details.get("name") or "there"},
        {"name": "record_date", "value": details.get("record_date", "")},
        {"name": "token", "value": client_id},
    ]


def _invite_params(client_id: str, details: dict) -> list:
    return [
        {"name": "name", "value": details.get("name") or "there"},
        {"name": "client_id", "value": client_id},
        {"name": "token", "value": details.get("token") or ""},
    ]


RECORDS_FAMILY = SendFamily(
    key="records_link",
    event_kind=EVENT_KIND,
    template_key=RECORDS_LINK_TEMPLATE_EN,
    template_default=RECORDS_LINK_TEMPLATE_EN_DEFAULT,
    cap_key=RECORDS_LINK_SEND_MAX_PER_RUN,
    cap_default=RECORDS_LINK_SEND_MAX_PER_RUN_DEFAULT,
    gap_key=RECORDS_LINK_SEND_MIN_GAP_DAYS,
    gap_default=RECORDS_LINK_SEND_MIN_GAP_DAYS_DEFAULT,
    category="UTILITY",
    build_params=_records_params,
    link_flag="ENABLE_RECORDS_LINK",
)

INVITE_FAMILY = SendFamily(
    key="referral_invite",
    event_kind=EVENT_KIND_INVITE,
    template_key=INVITE_TEMPLATE_EN,
    template_default=INVITE_TEMPLATE_EN_DEFAULT,
    cap_key=INVITE_SEND_MAX_PER_RUN,
    cap_default=INVITE_SEND_MAX_PER_RUN_DEFAULT,
    gap_key=INVITE_SEND_MIN_GAP_DAYS,
    gap_default=INVITE_SEND_MIN_GAP_DAYS_DEFAULT,
    # The invite is the ONE marketing-primary send (CLAUDE.md §6f); recorded as such
    # so delivery analysis can tell a 131049 cap failure apart from a utility failure.
    category="MARKETING",
    build_params=_invite_params,
    # The invite CTA links to /hub/{token}, mounted only under ENABLE_SHARE_HUB — NOT
    # ENABLE_RECORDS_LINK (that gates the unrelated /records/ page). Gating on the
    # wrong flag would let a SHARE_HUB-off + RECORDS_LINK-on tenant ship a dead button
    # with a green delivered tick (T-073 checker RULING-3).
    link_flag="ENABLE_SHARE_HUB",
)


# --------------------------------------------------------------------------- config


def _template_name(family: SendFamily, tenant_id: int | None) -> str:
    value = str(
        resolve_config(family.template_key, tenant_id=tenant_id, default=family.template_default)
    ).strip()
    return value or family.template_default


def _max_per_run(family: SendFamily, tenant_id: int | None) -> int:
    try:
        cap = int(resolve_config(family.cap_key, tenant_id=tenant_id, default=family.cap_default))
    except (TypeError, ValueError):
        return family.cap_default
    return cap if cap > 0 else family.cap_default


def _min_gap_days(family: SendFamily, tenant_id: int | None) -> int:
    try:
        days = int(resolve_config(family.gap_key, tenant_id=tenant_id, default=family.gap_default))
    except (TypeError, ValueError):
        return family.gap_default
    return days if days >= 0 else family.gap_default


def _recently_sent(family: SendFamily, tenant, client_id: str, tenant_id: int | None) -> bool:
    """True when a send of THIS family for this client_id landed within the gap."""
    cutoff = timezone.now() - timezone.timedelta(days=_min_gap_days(family, tenant_id))
    return Event.objects.for_tenant(tenant).filter(
        event_type=vocab.NOTIFICATION,
        source=vocab.SRC_WATI,
        metadata__kind=family.event_kind,
        metadata__client_id=client_id,
        timestamp__gte=cutoff,
    ).exists()


def _emit_event(family: SendFamily, tenant, client_id: str, template: str, outcome: str) -> None:
    """PII-free, TOKEN-free funnel event (T-051 precedent: the token never enters the
    immutable event log). client_id is not PII — it is already public (CLAUDE.md §4)."""
    try:
        Event.objects.create(
            tenant=tenant,
            event_type=vocab.NOTIFICATION,
            source=vocab.SRC_WATI,
            user_type="system",
            metadata={
                "kind": family.event_kind, "client_id": client_id,
                "template": template, "outcome": outcome,
            },
        )
    except Exception:
        logger.warning("%s funnel event emit failed for client_id=%s", family.key, client_id,
                       exc_info=True)


def _item(client_id: str, *, mobile: str = "", template: str, record_date: str = "",
          outcome: str, reason: str = "", token_minted: bool = False) -> dict:
    return {
        "client_id": client_id,
        "mobile": mobile,
        "template": template,
        "record_date": record_date,
        # Whether a DISTINCT token was minted for this recipient. Never the token
        # itself — a preview a human reads is still a place a credential can leak.
        "token_minted": token_minted,
        "outcome": outcome,
        "reason": reason,
    }


# --------------------------------------------------------------------------- run gates


def _assert_flags_on(family: SendFamily, tenant_id: int | None) -> None:
    # Local imports (not top-of-module) so tests can monkeypatch the resolver / the
    # frozen flags snapshot in place — the same convention `wati/adapter.py` and
    # `zoho/read.py` use for their own flag reads.
    from apps.config.integration_flags import ENABLE_WATI_SEND, resolve_flag
    from gorefer.flags import flags

    link_on = getattr(flags, family.link_flag)
    if not (resolve_flag(ENABLE_WATI_SEND, tenant_id=tenant_id) and link_on):
        raise SendRefused(
            f"refused: --send requires BOTH ENABLE_WATI_SEND and {family.link_flag} to be on"
        )


# --------------------------------------------------------------------------- per recipient


def _process_one(*, family: SendFamily, tenant, tenant_id, raw_client_id: str, template: str,
                 dry_run: bool, cap: int, dispatched_so_far: int, crm_read, messaging) -> dict:
    try:
        client_id = validate_client_id((raw_client_id or "").strip())
    except InvalidClientId as exc:
        return _item((raw_client_id or "")[:64], template=template, outcome=OUTCOME_SKIPPED,
                     reason=f"invalid client_id: {exc}")

    if dispatched_so_far >= cap:
        return _item(client_id, template=template, outcome=OUTCOME_SKIPPED,
                     reason=f"per-run cap reached ({cap})")

    if _recently_sent(family, tenant, client_id, tenant_id):
        return _item(client_id, template=template, outcome=OUTCOME_SKIPPED,
                     reason=f"{family.key} already sent within the min-gap window")

    # ONE token per recipient, minted HERE, through the same helper the mint API and
    # the hub CTA use — so a link from a broadcast and a link from the logged-in hub
    # can never diverge for the same identity.
    details = resolve_link_details(tenant, client_id)
    if details.get("error"):
        return _item(client_id, template=template, outcome=OUTCOME_SKIPPED, reason=details["error"])
    record_date = details.get("record_date", "")
    template_params = family.build_params(client_id, details)

    # THE fail-closed guard, run BEFORE any vendor lookup or write, so an unfillable
    # computed variable costs one skipped row rather than a blank link in a chat.
    try:
        assert_computed_vars_filled(template, template_params)
    except MissingComputedVar as exc:
        logger.warning("%s: refusing %s — %s", family.key, client_id, exc.reason)
        return _item(client_id, template=template, record_date=record_date,
                     outcome=OUTCOME_SKIPPED, reason=exc.reason)
    token_minted = True

    contact = crm_read.fetch_contact_by_client_id(client_id=client_id)
    mobile = normalize_phone(getattr(contact, "mobile", None))
    if not mobile:
        return _item(client_id, template=template, record_date=record_date, outcome=OUTCOME_SKIPPED,
                     reason="no mobile on file (CRM read)", token_minted=token_minted)
    masked = mask_mobile(mobile)

    from apps.followups.services import is_opted_out  # local import: avoid app-loading cycles

    if is_opted_out(tenant, mobile):
        return _item(client_id, mobile=masked, template=template, record_date=record_date,
                     outcome=OUTCOME_SKIPPED, reason="recipient opted out", token_minted=token_minted)

    if dry_run:
        return _item(client_id, mobile=masked, template=template, record_date=record_date,
                     outcome=OUTCOME_WOULD_SEND, token_minted=token_minted)

    return _send_and_record(
        family=family, tenant=tenant, client_id=client_id, mobile=mobile, masked=masked,
        template=template, record_date=record_date, template_params=template_params,
        messaging=messaging,
    )


def _send_and_record(*, family: SendFamily, tenant, client_id: str, mobile: str, masked: str,
                     template: str, record_date: str, template_params: list, messaging) -> dict:
    idem = f"{family.key}:{template}:{client_id}:{timezone.now().isoformat()}"
    n = Notification.objects.create(
        tenant=tenant,
        recipient_role="referrer",
        recipient_mobile=mobile,
        template=template,
        category=family.category,
        template_params=template_params,
        idempotency_key=idem,
        status="queued",
    )

    result = messaging.send_template(
        to=mobile, template=template,
        params={"template_params_named": True, "template_params": template_params},
    )
    n.adapter_kind = getattr(messaging, "kind", "")

    if result.raw_status == wati_status.STATUS_BLOCKED:
        n.status = "skipped"
        n.skip_reason = "recipient not in WATI allowlist (fail-closed)"
        n.save(update_fields=["status", "skip_reason", "adapter_kind", "updated_at"])
        _emit_event(family, tenant, client_id, template, "blocked")
        return _item(client_id, mobile=masked, template=template, record_date=record_date,
                     outcome=OUTCOME_SKIPPED, reason=n.skip_reason, token_minted=True)

    n.provider_message_id = result.provider_message_id or ""
    n.status = "accepted"
    n.save(update_fields=["provider_message_id", "status", "adapter_kind", "updated_at"])

    if not result.accepted:
        n.status = "failed"
        n.save(update_fields=["status", "updated_at"])
        _emit_event(family, tenant, client_id, template, "failed")
        return _item(client_id, mobile=masked, template=template, record_date=record_date,
                     outcome=OUTCOME_FAILED, reason="send not accepted", token_minted=True)

    delivery = messaging.get_message_status(
        provider_message_id=n.provider_message_id, recipient_mobile=mobile, template=template,
    )
    if ds.supersedes(n.status, delivery.status):
        n.status = delivery.status
        if delivery.status == wati_status.STATUS_FAILED:
            n.meta_error_code = delivery.meta_error_code
            n.failure_classification = ds.classify_failure(delivery.meta_error_code)
        n.save(update_fields=["status", "meta_error_code", "failure_classification", "updated_at"])

    _emit_event(family, tenant, client_id, template, n.status)
    if n.status == wati_status.STATUS_FAILED:
        return _item(client_id, mobile=masked, template=template, record_date=record_date,
                     outcome=OUTCOME_FAILED, reason=n.failure_classification or "delivery failed",
                     token_minted=True)
    return _item(client_id, mobile=masked, template=template, record_date=record_date,
                 outcome=OUTCOME_SENT, reason=n.status, token_minted=True)


# --------------------------------------------------------------------------- entry points


def _run(family: SendFamily, client_ids: list[str], *, dry_run: bool) -> dict:
    """Send (or preview) one family's template to an explicit client_id list.

    Real sends require BOTH `ENABLE_WATI_SEND` (resolved, admin-override-aware) AND
    the family's own `link_flag` (records -> `ENABLE_RECORDS_LINK`, invite ->
    `ENABLE_SHARE_HUB` — the flag that actually mounts the link the template points
    at), plus vendor-confirmed template APPROVAL — all checked ONCE up front so a
    mid-run flip can never produce a half-sent batch. Dry-run needs none of them: it
    never touches the messaging port.
    """
    tenant = get_current_tenant()
    tenant_id = getattr(tenant, "id", None)
    template = _template_name(family, tenant_id)
    cap = _max_per_run(family, tenant_id)

    messaging = None
    if not dry_run:
        _assert_flags_on(family, tenant_id)
        messaging = get_messaging_port()
        # Probe approval ONCE up front so a mid-run flip can never leave a half-sent
        # batch. `GuardedMessagingPort.send_template` (T-161 pt 15) re-asserts this on
        # every per-recipient send too, but that hits the short-TTL cache this call
        # just warmed — so this costs one vendor round trip, not N.
        messaging.assert_template_approved(template)

    crm_read = get_crm_read_port()

    items: list[dict] = []
    dispatched = 0
    for raw_client_id in client_ids:
        item = _process_one(
            family=family, tenant=tenant, tenant_id=tenant_id, raw_client_id=raw_client_id,
            template=template, dry_run=dry_run, cap=cap, dispatched_so_far=dispatched,
            crm_read=crm_read, messaging=messaging,
        )
        items.append(item)
        if item["outcome"] in (OUTCOME_SENT, OUTCOME_WOULD_SEND):
            dispatched += 1

    tally = {"sent": 0, "would_send": 0, "skipped": 0, "failed": 0}
    for item in items:
        tally[item["outcome"]] = tally.get(item["outcome"], 0) + 1

    return {"dry_run": dry_run, "family": family.key, "template": template, "items": items, **tally}


def send_records_links(client_ids: list[str], *, dry_run: bool = True) -> dict:
    """Send (or preview) the `[Referral Records]` template (T-057)."""
    return _run(RECORDS_FAMILY, client_ids, dry_run=dry_run)


def send_invite_links(client_ids: list[str], *, dry_run: bool = True) -> dict:
    """Send (or preview) the referral INVITE template, one minted token each (T-073).

    Landing this fires nothing: the configured template is a DRAFT at Meta, and
    `_assert_template_approved` refuses a real send of anything not APPROVED.
    """
    return _run(INVITE_FAMILY, client_ids, dry_run=dry_run)
