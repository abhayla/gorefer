"""The tokened, read-only "Referral Records" page — `GET /rr/{token}` (T-051).

Reached by tapping a [Referral Records] button in a WhatsApp message, with no login.
That convenience is only safe because WhatsApp messages get FORWARDED, so this page is
built to be harmless in a stranger's hands:

  * **read-only** — one GET route, no form, no state-changing endpoint;
  * **masked** — every referred person's name and mobile go through the one canonical
    `apps/common/masking.py` helper, at the DATA level, before the template sees them
    (the same discipline `selfview.py` uses, and for the same reason: a later template
    edit must not be able to re-expose what was masked);
  * **step-up** — full, unmasked detail lives behind the real `/login/`, linked here.

Failure is uniform: bad / expired / rotated tokens all render ONE page with a 404 and
zero referral data, so the endpoint can never be used to probe which client ids exist.

Guardrail 3: this is a client-facing surface, so nothing here may carry the partner
code or a raw Zerodha URL. It renders neither — GoRefer's own counts and masked names
only — and a test asserts it on the response bytes (the /my/referrals leak of
2026-07-26 got in exactly by way of a field nobody thought was client-facing).
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET

from apps.common.masking import mask_mobile, mask_name
from apps.common.ratelimit import RateLimited, check_rate, client_ip
from apps.events.models import Event
from apps.referrals.models import Lead, Referral
from gorefer.flags import flags

from .records_link import verify_records_token

logger = logging.getLogger("gorefer.accounts.records")

#: Rate-limit scope for the public token endpoint (shared DB-cache backend, so the
#: quota is global across gunicorn workers rather than per-worker).
RATE_SCOPE = "records_link"

#: Config-over-code strings for this page (the §6d pattern — one place, not scattered
#: literals). Copy that a non-engineer would ever want to change lives here.
RECORDS_CONFIG = {
    "title": "Your referral records",
    "not_on_file": "— not on file —",
    "masked_note": (
        "Names and numbers are partly hidden on this link because it can be forwarded. "
        "Log in to see full details."
    ),
    "login_cta": "Log in for full details",
    "expired_title": "This link has expired",
    "expired_body": "Referral-record links stop working after a while. Log in to see your records.",
    "empty": "No referrals recorded yet.",
    # T-053 cross-link. Rendered only when the share hub is actually mounted, so this
    # label can never become a dead button (Constitution §4).
    "hub_cta": "Share your referral link",
}

#: Lead status that means the account actually opened. Set ONLY by the Zoho ingest path
#: (guardrail 2) — this page reads it and never writes or infers it.
CONVERTED_STATUS = "account_opened"


def _login_url() -> str:
    """The step-up destination. `reverse()` when the login surface is mounted, else the
    canonical path — this page can be ON while ENABLE_CUSTOMER_LOGIN is off, and a
    NoReverseMatch must not 500 a public page."""
    try:
        return reverse("referrer_login")
    except NoReverseMatch:
        return "/login/"


def records_ctx(tenant, identity, token: str = "") -> dict:
    """The whole page, from GoRefer's OWN data — no Zoho call on a public path.

    Deliberately not routed through `dashboard.profile.top_band`: that path makes a
    Zoho READ for enrichment chips this page does not show, and a public, forwardable
    URL should not be able to drive traffic at a vendor API.
    """
    referrals = Referral.objects.for_tenant(tenant).filter(
        referral_identity=identity, deleted_at__isnull=True
    )
    leads = (
        Lead.objects.for_tenant(tenant)
        .filter(referral__in=referrals, deleted_at__isnull=True)
        .select_related("prospect", "referral")
        .order_by("-created_at")
    )

    nf = RECORDS_CONFIG["not_on_file"]
    rows, converted = [], 0
    first_at = last_at = None
    for lead in leads:
        is_converted = lead.status == CONVERTED_STATUS
        converted += 1 if is_converted else 0
        prospect = lead.prospect
        rows.append(
            {
                # Masked HERE, not in the template: the template must never receive
                # what the visitor may not see.
                "name": mask_name(prospect.name if prospect else "") or nf,
                "mobile": mask_mobile(prospect.mobile if prospect else "") or nf,
                "referred_on": lead.created_at,
                "opened_on": lead.account_opened_at or lead.referral.account_opened_at,
                "converted": is_converted,
                "status": "Account opened" if is_converted else "In progress",
            }
        )
        if first_at is None or lead.created_at < first_at:
            first_at = lead.created_at
        if last_at is None or lead.created_at > last_at:
            last_at = lead.created_at

    total = len(rows)
    return {
        "config": RECORDS_CONFIG,
        "client_id": identity.client_id,
        "rows": rows,
        "totals": {
            "referrals": total,
            "converted": converted,
            "pending": total - converted,
        },
        "first_referred_at": first_at,
        "last_referred_at": last_at,
        "login_url": _login_url(),
        # The SAME token opens the share hub (T-053) — no second token system. Blank
        # (and so unrendered) when that surface is off.
        "hub_url": f"/hub/{token}" if (token and flags.ENABLE_SHARE_HUB) else "",
    }


def _log_view(tenant, identity) -> None:
    """Record the page view on the immutable stream — ids and counters only.

    No name, no mobile, and NOT the token: the event log is append-only and outlives
    any erasure request, so anything that could re-identify a person (or replay a live
    link) must never enter it (#16/#17).
    """
    Event.objects.create(
        tenant=tenant,
        event_type="records_link_viewed",
        source="records_link",
        user_type="referrer",
        metadata={"client_id": identity.client_id},
    )


@require_GET
def records_view(request, token: str):
    """`GET /rr/{token}` — the whole surface. Mounted only when ENABLE_RECORDS_LINK."""
    try:
        check_rate(
            RATE_SCOPE,
            client_ip(request),
            limit=settings.RATELIMIT_RECORDS_MAX,
            window=settings.RATELIMIT_API_WINDOW,
        )
    except RateLimited as exc:
        # Returned for valid and invalid tokens alike, so throttling reveals nothing.
        return render(
            request,
            "accounts/records_unavailable.html",
            {"config": RECORDS_CONFIG, "login_url": _login_url(), "retry_after": exc.retry_after},
            status=429,
        )

    identity = verify_records_token(token)
    if identity is None:
        # ONE response for tampered / expired / rotated / unknown — no oracle.
        return render(
            request,
            "accounts/records_unavailable.html",
            {"config": RECORDS_CONFIG, "login_url": _login_url()},
            status=404,
        )

    # Scope from the IDENTITY, not the request host: the token names its own tenant and
    # the signature proves it, so a link opened on another tenant's domain can never
    # read across the ADR-023 boundary.
    tenant = identity.tenant
    ctx = records_ctx(tenant, identity, token)
    _log_view(tenant, identity)
    return render(request, "accounts/records.html", ctx)
