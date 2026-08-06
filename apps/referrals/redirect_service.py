"""Redirect resolver + lazy-journey service (M2 — the beating heart).

Responsibilities:
  - Resolve a program's server-side destination and assemble the final Zerodha URL
    with the partner code injected SERVER-SIDE (never stored/exposed to the client).
  - Lazily create-or-find the ReferralIdentity + Referral on first click (ADR-008),
    tenant-scoped; and record the immutable Click event (append-only, PII-free).
  - Partner-direct (/open): a Referral with referral_identity=NULL,
    source=partner_direct — never a synthetic referrer (Gap 1 / ADR-015).

Guardrails enforced here:
  - REDIRECT ONLY. This module assembles a URL and returns it for a 302; it NEVER
    performs an HTTP request to Zerodha (no POST/submit — reCAPTCHA form is off
    limits). There is no outbound-HTTP call anywhere in this file.
  - A bot/preview hit creates NO identity/referral and yields NO human click.
"""
from __future__ import annotations

import logging

from django.db import transaction

from apps.config.cascade import resolve
from apps.events import vocab
from apps.events.bots import is_bot_user_agent
from apps.events.models import Event, VisitorPII
from apps.events.nonces import mint_nonce
from apps.referrals.models import Partner, ProgramRedirectRule, Referral, ReferralIdentity, ReferralProgram

logger = logging.getLogger("gorefer.redirect")


def _active_program(tenant) -> ReferralProgram:
    """The single active program for the tenant (Sprint 1: Zerodha)."""
    qs = ReferralProgram.objects.filter(status="active", deleted_at__isnull=True)
    if tenant is not None:
        qs = qs.for_tenant(tenant)
    program = qs.order_by("id").first()
    if program is None:
        raise ReferralProgram.DoesNotExist("no active ReferralProgram seeded for tenant")
    return program


def assemble_destination(program: ReferralProgram, *, client_id: str | None,
                        tenant_id: int | None = None) -> str:
    """Build the final destination URL SERVER-SIDE from the program's template.

    The partner code is injected here from the Partner row — it is NEVER taken from
    the request and NEVER returned to the client except as the 302 Location.
    For partner-direct (client_id is None) the `r=` param is omitted entirely.
    """
    rule = (
        ProgramRedirectRule.objects.filter(program=program, is_active=True)
        .order_by("priority")
        .first()
    )
    if rule is None:
        raise ProgramRedirectRule.DoesNotExist("no active redirect rule for program")

    partner: Partner = program.partner
    if client_id is None:
        return partner_direct_destination(program, tenant_id=tenant_id)
    return rule.destination_url_template.format(partner_code=partner.code, client_id=client_id)


PARTNER_DIRECT_URL_KEY = "partner_direct_url_template"


def partner_direct_destination(program: ReferralProgram, *, tenant_id: int | None = None) -> str:
    """Where `/open` sends a visitor who arrived without a referrer.

    Owner decision 2026-07-26: default to the partner's plain signup page
    (`https://<signup-host>/?c={partner_code}`, the value `CLAUDE.md` always specified) so a
    self-serve visitor can complete the account themselves — but make it CHANGEABLE from
    config, e.g. back to the lead-capture path, without a deploy (CLAUDE.md §6d).

    Previously this was derived by stripping `&r=` off the referral template, which silently
    inherited that template's PATH — so `/open` was sending people to `/api/lead/` (a
    lead-capture form) rather than signup, disagreeing with the spec.

    The default is derived from the program's OWN template host rather than a hard-coded
    URL, so nothing here is Zerodha-specific and a future partner needs configuration, not
    code (Constitution: configuration over code).
    """
    rule = (
        ProgramRedirectRule.objects.filter(program=program, is_active=True)
        .order_by("priority")
        .first()
    )
    if rule is None:
        raise ProgramRedirectRule.DoesNotExist("no active redirect rule for program")

    template = _resolve_partner_direct_template(rule.destination_url_template, tenant_id)
    return template.format(partner_code=program.partner.code, client_id="")


def _resolve_partner_direct_template(referral_template: str, tenant_id: int | None) -> str:
    override = ""
    try:
        override = str(resolve(PARTNER_DIRECT_URL_KEY, tenant_id=tenant_id, default="") or "")
    except Exception:
        override = ""
    if override.strip():
        return override.strip()
    # Scheme/host split done by hand, deliberately WITHOUT the stdlib URL-parsing module.
    # `test_redirect_service_imports_no_http_client` scans this file's raw source for any
    # sign of an HTTP client, so nothing that resembles one may appear here — not even in a
    # comment. That bluntness is what makes the guardrail hard to game, and this module must
    # never grow an outbound call to the partner (redirect only, never submit).
    if "://" in referral_template:
        scheme, _, rest = referral_template.partition("://")
        host = rest.split("/", 1)[0].split("?", 1)[0]
        if scheme and host:
            return f"{scheme}://{host}/?c={{partner_code}}"
    # Malformed template — fall back to the old strip behaviour rather than 500 the redirect.
    return referral_template.split("&r=")[0].split("?r=")[0]


@transaction.atomic
def _lazy_get_or_create_referral(tenant, program, client_id: str) -> Referral:
    """Create-or-find the referrer identity + referral (idempotent on the identity key)."""
    identity, _ = ReferralIdentity.objects.get_or_create(
        tenant=tenant,
        partner=program.partner,
        client_id=client_id,
        id_source="native",
        defaults={"program": program, "status": "active"},
    )
    referral, _ = Referral.objects.get_or_create(
        tenant=tenant,
        referral_identity=identity,
        source="referral_link",
        defaults={"program": program, "status": "opened"},
    )
    return referral


@transaction.atomic
def _get_or_create_partner_direct_referral(tenant, program) -> Referral:
    """The partner-direct journey: referral_identity NULL, source partner_direct."""
    referral, _ = Referral.objects.get_or_create(
        tenant=tenant,
        referral_identity=None,
        source="partner_direct",
        defaults={"program": program, "status": "opened"},
    )
    return referral


def _record_event(
    *, tenant, referral, visitor_id, user_agent, raw_ip, event_type, source, share_channel=None
):
    """Write an immutable event + (if raw_ip) the SEPARATE erasable PII record.

    PII (raw IP) goes ONLY to VisitorPII; the event carries person_ref_id by id.
    Every event carries a source/origin tag (#18). Returns the created Event so
    callers (landing) can reference it (e.g. the beacon).

    `share_channel` (M11) is the normalized channel LABEL (e.g. "WhatsApp") from the
    `?s=` param — a non-PII attribution tag stored in metadata["channel"], reusing the
    Referral-Profile Clicks "Channel" column. None -> no channel key (renders "Direct").
    """
    person_ref_id = None
    if raw_ip:
        pii = VisitorPII.objects.create(tenant=tenant, visitor_id=visitor_id or "", raw_ip=raw_ip)
        person_ref_id = pii.pk
    metadata = {"channel": share_channel} if share_channel else {}  # NEVER PII (CI-enforced)
    event = Event.objects.create(
        tenant=tenant,
        event_type=event_type,
        source=source,
        referral=referral,
        user_type="anonymous",
        visitor_id=visitor_id,
        user_agent=user_agent or "",
        is_bot=False,
        is_confirmed_human=False,  # promoted only by the JS confirmation beacon
        person_ref_id=person_ref_id,
        metadata=metadata,
    )
    if event_type == vocab.CLICK:
        _stamp_first_click(referral, event.timestamp)
    return event


def _stamp_first_click(referral, when) -> None:
    """Stamp `Referral.first_click_at` on the FIRST click only, never on later ones.

    Every click path (landing view, direct redirect, continue, partner-direct) funnels
    through `_record_event`, so this is the one place that needs to know. Done as a
    CONDITIONAL UPDATE rather than a read-then-save: two simultaneous first clicks on the
    same referral would both read None and the later write would win, silently moving the
    "first" click later. `filter(first_click_at__isnull=True).update(...)` lets the database
    decide, and a no-op on a referral that already has one costs nothing.

    Deliberately not `referral.save()`: a full save would write back every field on this
    in-memory instance, stomping anything a concurrent writer changed on a hot redirect path.
    (Correction to an earlier version of this comment: it also claimed a save would bump
    `version`. It would not — `AuditedModel` declares `version` but overrides no `save()`, so
    nothing increments it automatically. The race-safety reason above is the real one.)

    Note this is currently the ONLY `.filter(...).update(...)` on an audited model in the repo,
    so treat it as a deliberate hot-path exception rather than an established pattern.

    Bot clicks can never reach here: `_record_event` writes `is_bot=False` unconditionally, and
    bot previews are recorded by a separate path, so the stamped value is always a real click.
    (Verified on prod 2026-07-26: one Googlebot click exists against referral 1, and the stamp
    matches the human click 26 ms earlier — but the one-off SQL backfill took `Min(timestamp)`
    across ALL clicks, so a bot arriving first WOULD have poisoned it. Any future backfill or
    recompute must filter `is_bot=False`.)
    """
    updated = Referral.objects.filter(pk=referral.pk, first_click_at__isnull=True).update(
        first_click_at=when
    )
    if updated:
        # keep the in-memory instance consistent for callers that read it after this
        referral.first_click_at = when


def handle_landing_view(*, tenant, client_id: str, visitor_id, user_agent, raw_ip, share_channel=None):
    """Resolve a /r/{client_id} landing view (M3: render page, NOT an immediate 302).

    On a human view: lazily create identity+referral, log a `landing_viewed` event
    (append-only, PII-free), record the raw IP on the erasable VisitorPII record,
    and MINT a one-time nonce for the beacon + name reveal. Returns
    (referral, event, nonce). On a bot/preview hit: create NOTHING and return
    (None, None, None) — the caller renders a generic page (with the OG card, M11)
    with no journey/nonce.

    `share_channel` (M11): the normalized channel label from `?s=`, stamped on the
    click event only (attribution). A bot/preview hit records nothing regardless.

    Written synchronously (not on_commit) because the landing render needs the
    event + nonce; this is the page-render path, not the hot 302.
    """
    program = _active_program(tenant)

    if is_bot_user_agent(user_agent):
        logger.info("bot/preview hit on /r/%s — no journey created", client_id)
        return None, None, None

    referral = _lazy_get_or_create_referral(tenant, program, client_id)
    # The /r/ hit IS the click; the branded page render is the landing view. Emit
    # both funnel stages (click precedes landing_viewed). Raw IP recorded once. The
    # share channel (M11) is attributed to the click event.
    _record_event(
        tenant=tenant, referral=referral, visitor_id=visitor_id, user_agent=user_agent,
        raw_ip=raw_ip, event_type=vocab.CLICK, source=vocab.SRC_CLICK, share_channel=share_channel,
    )
    event = _record_event(
        tenant=tenant, referral=referral, visitor_id=visitor_id, user_agent=user_agent,
        raw_ip=None, event_type=vocab.LANDING_VIEWED, source=vocab.SRC_CLICK,
    )
    nonce = mint_nonce(tenant=tenant, referral=referral, visitor_id=visitor_id or "", client_id=client_id)
    return referral, event, nonce


def handle_direct_redirect(*, tenant, client_id: str, visitor_id, user_agent, raw_ip, share_channel=None):
    """Resolve a /r/{client_id} hit in LANDING_MODE=direct (B3). Returns
    (destination_url, is_human_click).

    Frictionless path: lazily create the referrer identity + referral, log the CLICK
    on transaction.on_commit (never blocks the 302), then 302 straight to Zerodha —
    the landing page is skipped. The channel/`?s` is captured on the click for
    attribution but NEVER enters the Location (the destination is assembled
    server-side from the program template). A bot/preview hit creates nothing and
    still gets the destination (no human click).
    """
    program = _active_program(tenant)
    destination = assemble_destination(program, client_id=client_id)

    if is_bot_user_agent(user_agent):
        logger.info("bot/preview hit on direct /r/%s — no journey created", client_id)
        return destination, False

    referral = _lazy_get_or_create_referral(tenant, program, client_id)
    transaction.on_commit(
        lambda: _record_event(
            tenant=tenant, referral=referral, visitor_id=visitor_id, user_agent=user_agent,
            raw_ip=raw_ip, event_type=vocab.CLICK, source=vocab.SRC_CLICK, share_channel=share_channel,
        )
    )
    return destination, True


def build_continue_redirect(*, tenant, client_id: str, referral, share_channel=None):
    """Assemble the destination for "Continue to Zerodha" and log redirect_completed.

    Returns the destination URL for a 302. The redirect_completed write goes on
    transaction.on_commit so it never blocks the 302. Reuses the M2 engine —
    partner code injected server-side, raw URL never exposed. The `?s=` share channel
    (M11) is captured on the redirect_completed event but NEVER added to the
    destination (assembled from the template, so `s` can't leak into the Location).
    """
    program = _active_program(tenant)
    destination = assemble_destination(program, client_id=client_id)
    if referral is not None:
        transaction.on_commit(
            lambda: _record_event(
                tenant=tenant, referral=referral, visitor_id=None, user_agent="",
                raw_ip=None, event_type=vocab.REDIRECT_COMPLETED, source=vocab.SRC_REDIRECT,
                share_channel=share_channel,
            )
        )
    return destination


def handle_partner_direct(*, tenant, visitor_id, user_agent, raw_ip, share_channel=None):
    """Resolve a /open hit. Returns (destination_url, is_human_click).

    The assembled destination is built from the program template (no request params),
    so the `?s=` param is inherently absent from the 302 Location — it is captured for
    attribution (metadata["channel"]) but never propagated downstream.
    """
    program = _active_program(tenant)
    destination = assemble_destination(program, client_id=None,
                                       tenant_id=getattr(tenant, "id", None))

    if is_bot_user_agent(user_agent):
        logger.info("bot/preview hit on /open — no journey created")
        return destination, False

    referral = _get_or_create_partner_direct_referral(tenant, program)
    transaction.on_commit(
        lambda: _record_event(
            tenant=tenant, referral=referral, visitor_id=visitor_id, user_agent=user_agent,
            raw_ip=raw_ip, event_type=vocab.CLICK, source=vocab.SRC_CLICK, share_channel=share_channel,
        )
    )
    return destination, True


# Public aliases (M-WATI-1): share_intent_service reuses the ADR-008 lazy-creation
# engine + program resolution rather than duplicating them (DRY).
get_active_program = _active_program
lazy_get_or_create_referral = _lazy_get_or_create_referral
