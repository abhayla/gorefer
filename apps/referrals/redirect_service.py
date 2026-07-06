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

from apps.events.bots import is_bot_user_agent
from apps.events.models import Event, VisitorPII
from apps.referrals.models import Partner, ProgramRedirectRule, Referral, ReferralIdentity, ReferralProgram

logger = logging.getLogger("gorefer.redirect")

CLICK_EVENT_TYPE = "ReferralLinkOpened"
PARTNER_DIRECT_EVENT_TYPE = "PartnerDirectOpened"


def _active_program(tenant) -> ReferralProgram:
    """The single active program for the tenant (Sprint 1: Zerodha)."""
    qs = ReferralProgram.objects.filter(status="active", deleted_at__isnull=True)
    if tenant is not None:
        qs = qs.filter(tenant=tenant)
    program = qs.order_by("id").first()
    if program is None:
        raise ReferralProgram.DoesNotExist("no active ReferralProgram seeded for tenant")
    return program


def assemble_destination(program: ReferralProgram, *, client_id: str | None) -> str:
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
        # Partner-direct: strip the r= param from the template, keep c= only.
        # Template form: https://signup.zerodha.com/api/lead/?c={partner_code}&r={client_id}
        base = rule.destination_url_template.split("&r=")[0].split("?r=")[0]
        return base.format(partner_code=partner.code, client_id="")
    return rule.destination_url_template.format(partner_code=partner.code, client_id=client_id)


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


def _record_click(*, tenant, referral, visitor_id, user_agent, raw_ip, event_type):
    """Write the immutable Click event + the SEPARATE erasable PII record.

    PII (raw IP) goes ONLY to VisitorPII; the event carries person_ref_id by id.
    Scheduled via caller's transaction.on_commit so it never blocks the 302.
    """
    person_ref_id = None
    if raw_ip:
        pii = VisitorPII.objects.create(tenant=tenant, visitor_id=visitor_id or "", raw_ip=raw_ip)
        person_ref_id = pii.pk
    Event.objects.create(
        tenant=tenant,
        event_type=event_type,
        referral=referral,
        user_type="anonymous",
        visitor_id=visitor_id,
        user_agent=user_agent or "",
        is_bot=False,
        is_confirmed_human=False,  # promoted only by the JS beacon (M4)
        person_ref_id=person_ref_id,
        metadata={},  # NEVER PII (CI-enforced)
    )


def handle_referral_click(*, tenant, client_id: str, visitor_id, user_agent, raw_ip):
    """Resolve a /r/{client_id} hit. Returns (destination_url, is_human_click).

    On a human click: lazily create identity+referral and schedule the Click write
    on commit. On a bot/preview hit: create NOTHING, just return the destination so
    the caller can still 302 the *bot* (a bot following the redirect is harmless;
    it simply is not counted and leaves no journey).
    """
    program = _active_program(tenant)
    destination = assemble_destination(program, client_id=client_id)

    if is_bot_user_agent(user_agent):
        logger.info("bot/preview hit on /r/%s — no journey created", client_id)
        return destination, False

    referral = _lazy_get_or_create_referral(tenant, program, client_id)
    transaction.on_commit(
        lambda: _record_click(
            tenant=tenant,
            referral=referral,
            visitor_id=visitor_id,
            user_agent=user_agent,
            raw_ip=raw_ip,
            event_type=CLICK_EVENT_TYPE,
        )
    )
    return destination, True


def handle_partner_direct(*, tenant, visitor_id, user_agent, raw_ip):
    """Resolve a /open hit. Returns (destination_url, is_human_click)."""
    program = _active_program(tenant)
    destination = assemble_destination(program, client_id=None)

    if is_bot_user_agent(user_agent):
        logger.info("bot/preview hit on /open — no journey created")
        return destination, False

    referral = _get_or_create_partner_direct_referral(tenant, program)
    transaction.on_commit(
        lambda: _record_click(
            tenant=tenant,
            referral=referral,
            visitor_id=visitor_id,
            user_agent=user_agent,
            raw_ip=raw_ip,
            event_type=PARTNER_DIRECT_EVENT_TYPE,
        )
    )
    return destination, True
