"""The read-only "Referral Records" page — `GET /rr/{value}` (T-051, client-id T-129).

Reached by tapping a [Referral Records] button in a WhatsApp message, with no login.
That convenience is only safe because WhatsApp messages get FORWARDED, so this page is
built to be harmless in a stranger's hands:

  * **read-only** — one GET route, no form, no state-changing endpoint;
  * **masked** — every referred person's name and mobile go through the one canonical
    `apps/common/masking.py` helper, at the DATA level, before the template sees them
    (the same discipline `selfview.py` uses, and for the same reason: a later template
    edit must not be able to re-expose what was masked);
  * **step-up** — full, unmasked detail lives behind the real `/login/`, linked here.

`value` is shape-dispatched (T-129 — WhatsApp/Meta silently replaces a URL-button
variable value containing ':' with EMPTY, proven by a controlled tap 2026-08-14; a
`django.core.signing` token is always colon-separated, so a token-carrying button
arrives blank on every tap). A client-id-shaped value opens the SAME masked view
directly, by lookup — no token needed, and none minted. This is owner-accepted
(2026-08-14): Zerodha client ids are already public in Zerodha's own `r=` links, so
a guessable `/rr/{client_id}` leaks nothing a `/r/{client_id}` link didn't already.
Anything else is tried as a legacy signed token, so already-sent links keep working.

Failure is uniform: an unknown client id and a bad / expired / rotated / undecodable
token all render ONE page with a 404 and zero referral data, so the endpoint can
never be used to probe which client ids exist or which tokens are live.

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
from apps.config import preferences as prefs
from apps.config.i18n import LANG_EN, bi_text, market_risk_warning_hi, resolve_lang, with_lang
from apps.events.models import Event
from apps.referrals.models import Lead, Referral, ReferralIdentity
from apps.referrals.validators import InvalidClientId, validate_client_id_for
from apps.tenants.resolve import get_current_tenant
from gorefer.flags import flags

from .records_link import verify_records_token

logger = logging.getLogger("gorefer.accounts.records")

#: Rate-limit scope for the public token endpoint (shared DB-cache backend, so the
#: quota is global across gunicorn workers rather than per-worker).
RATE_SCOPE = "records_link"

#: EN-only fallback config, used when a caller cannot resolve the cascade (rate-limit
#: 429 path — see `records_view`). `records_config()` is the language-aware version
#: every normal render uses; kept here under the same name/shape for callers that
#: still expect an EN-only dict.
RECORDS_CONFIG = {
    "title": prefs.RECORDS_TITLE_DEFAULT,
    "not_on_file": prefs.RECORDS_NOT_ON_FILE_DEFAULT,
    "masked_note": prefs.RECORDS_MASKED_NOTE_DEFAULT,
    "login_cta": prefs.RECORDS_LOGIN_CTA_DEFAULT,
    "expired_title": prefs.RECORDS_EXPIRED_TITLE_DEFAULT,
    "expired_body": prefs.RECORDS_EXPIRED_BODY_DEFAULT,
    "empty": prefs.RECORDS_EMPTY_DEFAULT,
    # T-053 cross-link. Rendered only when the share hub is actually mounted, so this
    # label can never become a dead button (Constitution §4).
    "hub_cta": prefs.RECORDS_HUB_CTA_DEFAULT,
}


def records_config(lang: str, tenant_id: int | None) -> dict:
    """Bilingual config-over-code strings for this page (the §6d pattern extended to
    HI, T-061). Each value falls back EN when the HI cascade row is unset/blank —
    `apps.config.i18n.bi_text`'s contract — so a missing HI key can never blank the
    page, only silently render its EN text."""

    def t(base_key: str, default_en: str, hi_key: str, default_hi: str) -> str:
        return bi_text(base_key, default_en, lang=lang, tenant_id=tenant_id, default_hi=default_hi)

    return {
        "title": t(
            prefs.RECORDS_TITLE, prefs.RECORDS_TITLE_DEFAULT,
            prefs.RECORDS_TITLE_HI, prefs.RECORDS_TITLE_HI_DEFAULT,
        ),
        "not_on_file": t(
            prefs.RECORDS_NOT_ON_FILE, prefs.RECORDS_NOT_ON_FILE_DEFAULT,
            prefs.RECORDS_NOT_ON_FILE_HI, prefs.RECORDS_NOT_ON_FILE_HI_DEFAULT,
        ),
        "masked_note": t(
            prefs.RECORDS_MASKED_NOTE, prefs.RECORDS_MASKED_NOTE_DEFAULT,
            prefs.RECORDS_MASKED_NOTE_HI, prefs.RECORDS_MASKED_NOTE_HI_DEFAULT,
        ),
        "login_cta": t(
            prefs.RECORDS_LOGIN_CTA, prefs.RECORDS_LOGIN_CTA_DEFAULT,
            prefs.RECORDS_LOGIN_CTA_HI, prefs.RECORDS_LOGIN_CTA_HI_DEFAULT,
        ),
        "expired_title": t(
            prefs.RECORDS_EXPIRED_TITLE, prefs.RECORDS_EXPIRED_TITLE_DEFAULT,
            prefs.RECORDS_EXPIRED_TITLE_HI, prefs.RECORDS_EXPIRED_TITLE_HI_DEFAULT,
        ),
        "expired_body": t(
            prefs.RECORDS_EXPIRED_BODY, prefs.RECORDS_EXPIRED_BODY_DEFAULT,
            prefs.RECORDS_EXPIRED_BODY_HI, prefs.RECORDS_EXPIRED_BODY_HI_DEFAULT,
        ),
        "empty": t(
            prefs.RECORDS_EMPTY, prefs.RECORDS_EMPTY_DEFAULT,
            prefs.RECORDS_EMPTY_HI, prefs.RECORDS_EMPTY_HI_DEFAULT,
        ),
        "hub_cta": t(
            prefs.RECORDS_HUB_CTA, prefs.RECORDS_HUB_CTA_DEFAULT,
            prefs.RECORDS_HUB_CTA_HI, prefs.RECORDS_HUB_CTA_HI_DEFAULT,
        ),
        "stat_referred": t(
            prefs.RECORDS_STAT_REFERRED, prefs.RECORDS_STAT_REFERRED_DEFAULT,
            prefs.RECORDS_STAT_REFERRED_HI, prefs.RECORDS_STAT_REFERRED_HI_DEFAULT,
        ),
        "stat_converted": t(
            prefs.RECORDS_STAT_CONVERTED, prefs.RECORDS_STAT_CONVERTED_DEFAULT,
            prefs.RECORDS_STAT_CONVERTED_HI, prefs.RECORDS_STAT_CONVERTED_HI_DEFAULT,
        ),
        "stat_pending": t(
            prefs.RECORDS_STAT_PENDING, prefs.RECORDS_STAT_PENDING_DEFAULT,
            prefs.RECORDS_STAT_PENDING_HI, prefs.RECORDS_STAT_PENDING_HI_DEFAULT,
        ),
        "col_name": t(
            prefs.RECORDS_COL_NAME, prefs.RECORDS_COL_NAME_DEFAULT,
            prefs.RECORDS_COL_NAME_HI, prefs.RECORDS_COL_NAME_HI_DEFAULT,
        ),
        "col_mobile": t(
            prefs.RECORDS_COL_MOBILE, prefs.RECORDS_COL_MOBILE_DEFAULT,
            prefs.RECORDS_COL_MOBILE_HI, prefs.RECORDS_COL_MOBILE_HI_DEFAULT,
        ),
        "col_status": t(
            prefs.RECORDS_COL_STATUS, prefs.RECORDS_COL_STATUS_DEFAULT,
            prefs.RECORDS_COL_STATUS_HI, prefs.RECORDS_COL_STATUS_HI_DEFAULT,
        ),
        "col_referred": t(
            prefs.RECORDS_COL_REFERRED, prefs.RECORDS_COL_REFERRED_DEFAULT,
            prefs.RECORDS_COL_REFERRED_HI, prefs.RECORDS_COL_REFERRED_HI_DEFAULT,
        ),
        "status_opened": t(
            prefs.RECORDS_STATUS_OPENED, prefs.RECORDS_STATUS_OPENED_DEFAULT,
            prefs.RECORDS_STATUS_OPENED_HI, prefs.RECORDS_STATUS_OPENED_HI_DEFAULT,
        ),
        "status_in_progress": t(
            prefs.RECORDS_STATUS_IN_PROGRESS, prefs.RECORDS_STATUS_IN_PROGRESS_DEFAULT,
            prefs.RECORDS_STATUS_IN_PROGRESS_HI, prefs.RECORDS_STATUS_IN_PROGRESS_HI_DEFAULT,
        ),
    }


def _lang_toggle(lang: str, tenant_id: int | None) -> dict:
    """The EN<->HI toggle link both pages render — a REAL link, never dead UI
    (Constitution §4). `target_lang`/`target_suffix` let the template build the
    toggle href without string-formatting a query param itself."""
    to_hi = bi_text(
        prefs.LANG_TOGGLE_TO_HI_LABEL, prefs.LANG_TOGGLE_TO_HI_LABEL_DEFAULT,
        lang=LANG_EN, tenant_id=tenant_id,
    )
    to_en = bi_text(
        prefs.LANG_TOGGLE_TO_EN_LABEL, prefs.LANG_TOGGLE_TO_EN_LABEL_DEFAULT,
        lang=LANG_EN, tenant_id=tenant_id,
    )
    if lang == "hi":
        return {"target_lang": "en", "label": to_en, "query_suffix": ""}
    return {"target_lang": "hi", "label": to_hi, "query_suffix": "?lang=hi"}

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


def records_ctx(tenant, identity, token: str = "", lang: str = LANG_EN) -> dict:
    """The whole page, from GoRefer's OWN data — no Zoho call on a public path.

    Deliberately not routed through `dashboard.profile.top_band`: that path makes a
    Zoho READ for enrichment chips this page does not show, and a public, forwardable
    URL should not be able to drive traffic at a vendor API.
    """
    tenant_id = getattr(tenant, "id", None)
    config = records_config(lang, tenant_id)

    referrals = Referral.objects.for_tenant(tenant).filter(
        referral_identity=identity, deleted_at__isnull=True
    )
    leads = (
        Lead.objects.for_tenant(tenant)
        .filter(referral__in=referrals, deleted_at__isnull=True)
        .select_related("prospect", "referral")
        .order_by("-created_at")
    )

    nf = config["not_on_file"]
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
                "status": config["status_opened"] if is_converted else config["status_in_progress"],
            }
        )
        if first_at is None or lead.created_at < first_at:
            first_at = lead.created_at
        if last_at is None or lead.created_at > last_at:
            last_at = lead.created_at

    total = len(rows)
    return {
        "config": config,
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
        # (and so unrendered) when that surface is off. Carries the current lang so
        # the referrer stays in the language they picked (DoD, T-061).
        "hub_url": with_lang(f"/hub/{token}", lang) if (token and flags.ENABLE_SHARE_HUB) else "",
        "lang": lang,
        "lang_toggle": _lang_toggle(lang, tenant_id),
        # Bilingual-safe compliance (DoD): the locked EN market_risk_warning always
        # renders (base.html); this ADDS the Hindi wording alongside it when lang=hi.
        "market_risk_warning_hi": market_risk_warning_hi(tenant_id) if lang == "hi" else "",
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


def _client_id_identity(request, value: str) -> ReferralIdentity | None:
    """`value` shaped like an active client id for THIS request's tenant/partner ->
    the identity it names, else `None`. Never raises: an unrecognized shape or an
    unknown id both simply fall through to the legacy token path below, so a garbage
    value gets exactly one uniform failure page, not two different ones.

    Scoped from the REQUEST's resolved tenant (ADR-023) — there is no token payload
    to carry the tenant here, so this is the same resolution `/r/{client_id}` itself
    uses, not the identity-carries-its-own-tenant trick the token path relies on.
    """
    tenant = get_current_tenant(request)
    try:
        client_id = validate_client_id_for(tenant, value)
    except InvalidClientId:
        return None
    return (
        ReferralIdentity.objects.for_tenant(tenant)
        .filter(client_id=client_id, status="active", deleted_at__isnull=True)
        .first()
    )


@require_GET
def records_view(request, value: str):
    """`GET /rr/{value}` — the whole surface. Mounted only when ENABLE_RECORDS_LINK.

    `value` is shape-dispatched (T-129): client-id-shaped -> direct lookup, no
    token; otherwise -> the legacy signed-token path, unchanged.
    """
    lang = resolve_lang(request)
    # No tenant known yet on the failure paths (nothing verified yet) — the central-
    # tier default (tenant_id=None) is the correct, identical-for-everyone fallback.
    fail_config = records_config(lang, None)
    fail_ctx = {
        "config": fail_config,
        "login_url": _login_url(),
        "lang": lang,
        "market_risk_warning_hi": market_risk_warning_hi(None) if lang == "hi" else "",
    }
    try:
        check_rate(
            RATE_SCOPE,
            client_ip(request),
            limit=settings.RATELIMIT_RECORDS_MAX,
            window=settings.RATELIMIT_API_WINDOW,
        )
    except RateLimited as exc:
        # Returned for valid and invalid values alike, so throttling reveals nothing.
        return render(
            request,
            "accounts/records_unavailable.html",
            {**fail_ctx, "retry_after": exc.retry_after},
            status=429,
        )

    client_id_identity = _client_id_identity(request, value)
    if client_id_identity is not None:
        tenant = client_id_identity.tenant
        # No token: nothing was minted for this open, so the hub cross-link (which
        # rides the same token) simply stays hidden — never a dead link.
        ctx = records_ctx(tenant, client_id_identity, "", lang)
        _log_view(tenant, client_id_identity)
        return render(request, "accounts/records.html", ctx)

    identity = verify_records_token(value)
    if identity is None:
        # ONE response for an unrecognized client id and a tampered / expired /
        # rotated / undecodable token alike — no oracle.
        return render(
            request,
            "accounts/records_unavailable.html",
            fail_ctx,
            status=404,
        )

    # Scope from the IDENTITY, not the request host: the token names its own tenant and
    # the signature proves it, so a link opened on another tenant's domain can never
    # read across the ADR-023 boundary.
    tenant = identity.tenant
    ctx = records_ctx(tenant, identity, value, lang)
    _log_view(tenant, identity)
    return render(request, "accounts/records.html", ctx)
