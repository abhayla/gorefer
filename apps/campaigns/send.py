"""Messaging campaign sending (T-125, W2) — a new `SendFamily` instance in the
`apps.integrations.records_link_send` pattern, reusing that module's fail-closed
guards VERBATIM rather than re-implementing them: `_assert_template_approved`,
`assert_computed_vars_filled` (blank token → SKIPPED before any network call), and
`_send_and_record` (accepted → terminal-status recording, doc-08 A3). One send
path, so a campaign send can never disagree with a records-link send about what
"fail closed" means.

The flags gate here is deliberately NOT `records_link_send._assert_flags_on` (which
also demands `ENABLE_WATI_SEND` and refuses outright when it's off — correct for a
human-triggered CLI batch whose default is dry-run, wrong for an unattended engine).
This engine follows the `apps.followups` sweep precedent instead: it always attempts
a send through `get_messaging_port()`, and the PORT FACTORY is what swaps in the
LogOnly adapter when `ENABLE_WATI_SEND` is off — so demo mode logs an intended send
rather than silently skipping every row (CLAUDE.md §7 "demo mode still works
end-to-end"). What this DOES still gate on, unconditionally, is
`ENABLE_RECORDS_LINK`: the seeded campaign template points at `/rr/{token}` — the
same surface `RECORDS_FAMILY` gates on — and sending a link to an unmounted page is
a dead link in a recipient's chat regardless of vendor delivery mode (Constitution §4).
"""
from __future__ import annotations

import logging

from api.records_tokens import resolve_link_details
from apps.common.masking import mask_mobile
from apps.config.preferences import (
    RECORDS_LINK_SEND_MAX_PER_RUN,
    RECORDS_LINK_SEND_MAX_PER_RUN_DEFAULT,
    RECORDS_LINK_SEND_MIN_GAP_DAYS,
    RECORDS_LINK_SEND_MIN_GAP_DAYS_DEFAULT,
    RECORDS_LINK_TEMPLATE_EN,
    RECORDS_LINK_TEMPLATE_EN_DEFAULT,
)
from apps.integrations.computed_vars import MissingComputedVar, assert_computed_vars_filled
from apps.integrations.ports import get_messaging_port
from apps.integrations.records_link_send import (
    OUTCOME_SKIPPED,
    SendFamily,
    SendRefused,
    _assert_template_approved,
    _item,
    _send_and_record,
)

logger = logging.getLogger("gorefer.campaigns.send")


def _campaign_params(client_id: str, details: dict) -> list:
    return [
        {"name": "name", "value": details.get("name") or "there"},
        {"name": "record_date", "value": details.get("record_date", "")},
        {"name": "token", "value": details.get("token") or ""},
    ]


# Cap/gap keys are unused by the campaign engine (its own rolling budgets in
# `services.budget_exceeded` govern spacing) — the SendFamily dataclass requires
# them, so they point at the records-link keys they share a template family with,
# never consulted here.
CAMPAIGN_FAMILY = SendFamily(
    key="messaging_campaign",
    event_kind="messaging_campaign",
    template_key=RECORDS_LINK_TEMPLATE_EN,
    template_default=RECORDS_LINK_TEMPLATE_EN_DEFAULT,
    cap_key=RECORDS_LINK_SEND_MAX_PER_RUN,
    cap_default=RECORDS_LINK_SEND_MAX_PER_RUN_DEFAULT,
    gap_key=RECORDS_LINK_SEND_MIN_GAP_DAYS,
    gap_default=RECORDS_LINK_SEND_MIN_GAP_DAYS_DEFAULT,
    category="UTILITY",
    build_params=_campaign_params,
    link_flag="ENABLE_RECORDS_LINK",
)


def send_campaign_message(*, tenant, client_id: str, mobile: str, template: str) -> dict:
    """Send one campaign step to one recipient. Every fail-closed guard runs BEFORE
    any network call; a refusal or a missing computed var returns a SKIPPED item
    rather than raising, so the sweep can record a reason and move to the next row.
    """
    if not template:
        return _item(client_id, mobile=mask_mobile(mobile) if mobile else "", template="",
                     outcome=OUTCOME_SKIPPED, reason="no template configured for this language")

    from gorefer.flags import flags

    if not flags.ENABLE_RECORDS_LINK:
        return _item(client_id, mobile=mask_mobile(mobile) if mobile else "", template=template,
                     outcome=OUTCOME_SKIPPED,
                     reason="refused: ENABLE_RECORDS_LINK is off (records link surface not mounted)")

    messaging = get_messaging_port()
    try:
        _assert_template_approved(messaging, template)
    except SendRefused as exc:
        return _item(client_id, mobile=mask_mobile(mobile) if mobile else "", template=template,
                     outcome=OUTCOME_SKIPPED, reason=str(exc))

    details = resolve_link_details(tenant, client_id)
    if details.get("error"):
        return _item(client_id, mobile=mask_mobile(mobile) if mobile else "", template=template,
                     outcome=OUTCOME_SKIPPED, reason=details["error"])

    record_date = details.get("record_date", "")
    template_params = CAMPAIGN_FAMILY.build_params(client_id, details)

    # THE fail-closed guard (T-073) — refuses BEFORE any vendor lookup or write, so
    # a template whose {{token}} came back blank costs one skipped row, never a
    # dead link in a recipient's chat history.
    try:
        assert_computed_vars_filled(template, template_params)
    except MissingComputedVar as exc:
        logger.warning("campaign send: refusing %s — %s", client_id, exc.reason)
        return _item(client_id, template=template, record_date=record_date,
                     outcome=OUTCOME_SKIPPED, reason=exc.reason)

    if not mobile:
        return _item(client_id, template=template, record_date=record_date,
                     outcome=OUTCOME_SKIPPED, reason="no mobile on file", token_minted=True)

    return _send_and_record(
        family=CAMPAIGN_FAMILY, tenant=tenant, client_id=client_id, mobile=mobile,
        masked=mask_mobile(mobile), template=template, record_date=record_date,
        template_params=template_params, messaging=messaging,
    )
