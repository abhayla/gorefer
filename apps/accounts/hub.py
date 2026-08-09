"""The referral SHARE HUB — `GET /hub/{token}` (T-053).

Where a [Refer Link] button on a MARKETING WhatsApp template lands. Its whole job is
to make sharing easy and attractive: what the referrer gets, how and where to share,
their own credit link, and one-tap buttons for the channels people actually use.

Deliberately a SEPARATE page from the T-051 records view (`/rr/{token}`): that one is
dry on purpose because it is a UTILITY-button destination. The SAME signed token opens
both — `records_link.verify_records_token` is reused verbatim, and this module adds no
second token system. Each page cross-links to the other, and only when the other's flag
is on (Constitution §4 — no dead links).

The load-bearing security invariant, and the reason this module builds every share URL
SERVER-SIDE rather than letting a template concatenate one:

    the token is PAGE ACCESS, never shared content.

A referrer who taps "WhatsApp" must forward their credit link `/r/wa/{client_id}` — a
public identifier that already appears in the partner's own links — and never the token
that opens their records. So nothing here interpolates `token` into a share URL, a
prefill, or an event payload, and `tests/test_t053_share_hub.py` asserts that on the
built URLs, the response bytes and the Event rows.

Guardrail 3: client-facing surface. The partner code and any raw partner URL are absent
by construction — every destination is either gorefer.in or a platform's own share
intent — and a test asserts it on the response bytes.
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from django.conf import settings
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET

from apps.common.ratelimit import RateLimited, check_rate, client_ip
from apps.config import preferences as prefs
from apps.config.cascade import resolve as resolve_config
from apps.config.i18n import (
    LANG_EN,
    bi_lines,
    bi_text,
    market_risk_warning_hi,
    resolve_lang,
    resolve_lang_or_stored,
    with_lang,
)
from apps.config.preferences import (
    REFERRER_REWARD_CLAIM,
    SHARE_HUB_BENEFITS,
    SHARE_HUB_BENEFITS_DEFAULT,
    SHARE_HUB_BENEFITS_HEADING,
    SHARE_HUB_BENEFITS_HEADING_DEFAULT,
    SHARE_HUB_BENEFITS_HEADING_HI,
    SHARE_HUB_BENEFITS_HEADING_HI_DEFAULT,
    SHARE_HUB_BENEFITS_HI_DEFAULT,
    SHARE_HUB_GUIDANCE,
    SHARE_HUB_GUIDANCE_DEFAULT,
    SHARE_HUB_GUIDANCE_HEADING,
    SHARE_HUB_GUIDANCE_HEADING_DEFAULT,
    SHARE_HUB_GUIDANCE_HEADING_HI,
    SHARE_HUB_GUIDANCE_HEADING_HI_DEFAULT,
    SHARE_HUB_GUIDANCE_HI_DEFAULT,
    SHARE_HUB_HEADLINE,
    SHARE_HUB_HEADLINE_DEFAULT,
    SHARE_HUB_HEADLINE_HI,
    SHARE_HUB_HEADLINE_HI_DEFAULT,
    SHARE_HUB_IMAGE_1_URL,
    SHARE_HUB_IMAGE_2_URL,
    SHARE_HUB_INTRO,
    SHARE_HUB_INTRO_DEFAULT,
    SHARE_HUB_INTRO_HI,
    SHARE_HUB_INTRO_HI_DEFAULT,
    SHARE_HUB_OG_IMAGE_DEFAULT,
    SHARE_HUB_OG_IMAGE_URL,
    SHARE_HUB_PARTNER_ATTRIBUTION,
    SHARE_HUB_PARTNER_ATTRIBUTION_DEFAULT,
    SHARE_HUB_PARTNER_ATTRIBUTION_HI,
    SHARE_HUB_PARTNER_ATTRIBUTION_HI_DEFAULT,
)
from apps.events.models import Event
from apps.referrals.og import absolute_image_url
from apps.referrals.share_intent_service import kit_message, tracked_link
from gorefer.flags import flags

from .records import records_config
from .records_link import verify_records_token

logger = logging.getLogger("gorefer.accounts.hub")

#: Rate-limit scope for this public token endpoint. Separate from the /rr/ scope so a
#: referrer bouncing between the two pages cannot throttle themselves out of either.
RATE_SCOPE = "share_hub"

#: The channel the credit link is tagged with. `wa` because the hub is reached from a
#: WhatsApp button — the tag records where the SHARE originated, and one link for all
#: buttons keeps the referrer's shared URL identical wherever they paste it.
LINK_CHANNEL = "wa"


def hub_chrome(lang: str, tenant_id: int | None) -> dict:
    """Page chrome (button labels, section furniture) — bilingual (T-061), each string
    a cascade key with an `_hi` twin (apps.config.i18n fallback contract)."""
    records = records_config(lang, tenant_id)

    def t(base_key: str, default_en: str, hi_key: str, default_hi: str) -> str:
        return bi_text(base_key, default_en, lang=lang, tenant_id=tenant_id, default_hi=default_hi)

    return {
        "your_link_label": t(
            prefs.HUB_YOUR_LINK_LABEL, prefs.HUB_YOUR_LINK_LABEL_DEFAULT,
            prefs.HUB_YOUR_LINK_LABEL_HI, prefs.HUB_YOUR_LINK_LABEL_HI_DEFAULT,
        ),
        "share_heading": t(
            prefs.HUB_SHARE_HEADING, prefs.HUB_SHARE_HEADING_DEFAULT,
            prefs.HUB_SHARE_HEADING_HI, prefs.HUB_SHARE_HEADING_HI_DEFAULT,
        ),
        "copy_label": t(
            prefs.HUB_COPY_LABEL, prefs.HUB_COPY_LABEL_DEFAULT,
            prefs.HUB_COPY_LABEL_HI, prefs.HUB_COPY_LABEL_HI_DEFAULT,
        ),
        "copy_done_label": t(
            prefs.HUB_COPY_DONE_LABEL, prefs.HUB_COPY_DONE_LABEL_DEFAULT,
            prefs.HUB_COPY_DONE_LABEL_HI, prefs.HUB_COPY_DONE_LABEL_HI_DEFAULT,
        ),
        "more_label": t(
            prefs.HUB_MORE_LABEL, prefs.HUB_MORE_LABEL_DEFAULT,
            prefs.HUB_MORE_LABEL_HI, prefs.HUB_MORE_LABEL_HI_DEFAULT,
        ),
        "records_cta": t(
            prefs.HUB_RECORDS_CTA, prefs.HUB_RECORDS_CTA_DEFAULT,
            prefs.HUB_RECORDS_CTA_HI, prefs.HUB_RECORDS_CTA_HI_DEFAULT,
        ),
        "download_label": t(
            prefs.HUB_DOWNLOAD_LABEL, prefs.HUB_DOWNLOAD_LABEL_DEFAULT,
            prefs.HUB_DOWNLOAD_LABEL_HI, prefs.HUB_DOWNLOAD_LABEL_HI_DEFAULT,
        ),
        "expired_title": records["expired_title"],
        "expired_body": records["expired_body"],
        "login_cta": records["login_cta"],
    }

#: The full platform row (owner decision 2026-08-08 — the full set, not the minimal one).
#:
#: `event_channel` is the code sent to the EXISTING `POST /api/share` endpoint, so taps
#: land in the same `share_clicked` stream as the landing page's button rather than a
#: parallel one. `kind` decides what the button carries:
#:   "text" — platforms whose intent accepts a prefilled message (the link rides inside);
#:   "url"  — platforms that only accept a URL (Facebook and LinkedIn strip any text
#:            parameter, so passing one would be a silent lie about what gets posted).
SHARE_BUTTONS = [
    {"code": "wa", "label": "WhatsApp", "event_channel": "whatsapp", "kind": "text"},
    {"code": "telegram", "label": "Telegram", "event_channel": "telegram", "kind": "text"},
    {"code": "facebook", "label": "Facebook", "event_channel": "facebook", "kind": "url"},
    {"code": "x", "label": "X", "event_channel": "x", "kind": "text"},
    {"code": "linkedin", "label": "LinkedIn", "event_channel": "linkedin", "kind": "url"},
]

#: The code within SHARE_BUTTONS the hub promotes to the one large primary CTA
#: (owner ruling 2026-08-08: WhatsApp is where referrers actually share, per send
#: data). Every other listed channel demotes to the compact icon row.
PRIMARY_SHARE_CODE = "wa"

#: Channel code for the native OS share sheet (`navigator.share`) — no third-party JS,
#: no SDK, just the browser API. Falls back to Copy where the API is absent.
NATIVE_SHARE_CHANNEL = "native_share"
COPY_CHANNEL = "copy_link"


def _cfg(key: str, default, tenant_id: int | None):
    """Cascade lookup that can never 500 a public page on a bad stored value."""
    try:
        value = resolve_config(key, tenant_id=tenant_id, default=default)
    except Exception:  # pragma: no cover - resolver is not expected to raise
        return default
    return default if value is None else value


def _lines(value, default: list[str]) -> list[str]:
    """Coerce a stored bullet list to clean strings.

    Accepts the JSON list it is stored as, or a newline-separated string (what an
    operator pasting copy into a text box would produce). An empty result falls back
    to the default rather than rendering a headless section.
    """
    if isinstance(value, str):
        items = [line.strip() for line in value.splitlines()]
    elif isinstance(value, (list, tuple)):
        items = [str(item).strip() for item in value]
    else:
        items = []
    return [item for item in items if item] or list(default)


def _share_targets(message: str, link: str) -> dict[str, str]:
    """Plain web intents for each platform — no SDK, no third-party script.

    Every value is built from `message`/`link` only, both of which are derived from the
    client_id. The token is not a parameter of this function on purpose: it cannot leak
    into a destination it never receives.
    """
    text = quote(message, safe="")
    url = quote(link, safe="")
    return {
        "wa": f"https://wa.me/?text={text}",
        "telegram": f"https://t.me/share/url?url={url}&text={text}",
        "facebook": f"https://www.facebook.com/sharer/sharer.php?u={url}",
        "x": f"https://x.com/intent/post?text={text}",
        "linkedin": f"https://www.linkedin.com/sharing/share-offsite/?url={url}",
    }


def _login_url() -> str:
    """Step-up destination; mirrors records._login_url (this page can be ON while
    ENABLE_CUSTOMER_LOGIN is off, and a NoReverseMatch must not 500 a public page)."""
    try:
        return reverse("referrer_login")
    except NoReverseMatch:
        return "/login/"


def _brand_name(identity) -> str:
    """The name the header shows (T-056).

    `Partner` is the AP/business (e.g. PIFS) — `ReferralProgram` is the broker/product
    it runs referrals for. Prod data has both on one identity, and they differ: the
    header must read the PROGRAM brand, not the partner-company name (that would
    render as "PIFS ... via PIFS"). Falls back to `program.name` if no display_name is
    set, and only to `partner.name` if the identity carries no program at all — never
    a blank chip.
    """
    program = getattr(identity, "program", None)
    if program is not None:
        display_name = getattr(program, "display_name", "") or ""
        if display_name:
            return display_name
        name = getattr(program, "name", "") or ""
        if name:
            return name
    partner = getattr(identity, "partner", None)
    if partner is not None:
        return getattr(partner, "name", "") or ""
    return ""


def hub_ctx(identity, token: str, lang: str = LANG_EN) -> dict:
    """Everything the page renders. `token` is used for ONE thing — the cross-link to
    the records page — and never reaches a share URL or the prefill. `lang` (T-061)
    selects the bilingual copy twin; defaults to EN so every existing caller (tests,
    the /my/referrals hub-CTA builder) keeps behaving exactly as before."""
    tenant_id = identity.tenant_id
    client_id = identity.client_id

    link = tracked_link(LINK_CHANNEL, client_id)
    # T-059: pass the identity's own program so the prefill's {program_brand} matches
    # the header's brand (same T-056 fallback chain, apps.referrals.branding).
    message = kit_message(
        LINK_CHANNEL, client_id, tenant_id, program=getattr(identity, "program", None), lang=lang
    )
    targets = _share_targets(message, link)

    buttons = [dict(button, href=targets[button["code"]]) for button in SHARE_BUTTONS]
    primary_button = next(b for b in buttons if b["code"] == PRIMARY_SHARE_CODE)
    secondary_buttons = [b for b in buttons if b["code"] != PRIMARY_SHARE_CODE]

    def t(base_key: str, default_en: str, hi_key: str, default_hi: str) -> str:
        return bi_text(base_key, default_en, lang=lang, tenant_id=tenant_id, default_hi=default_hi)

    return {
        "client_id": client_id,
        "chrome": hub_chrome(lang, tenant_id),
        # The BRAND comes from the DB record (never a literal — CLAUDE.md §4): the
        # broker/program, not the partner-company name (PIFS) — see `_brand_name`.
        # The attribution wording is the one config knob (rail E-6 / §6d).
        "brand_name": _brand_name(identity),
        "partner_attribution": t(
            SHARE_HUB_PARTNER_ATTRIBUTION, SHARE_HUB_PARTNER_ATTRIBUTION_DEFAULT,
            SHARE_HUB_PARTNER_ATTRIBUTION_HI, SHARE_HUB_PARTNER_ATTRIBUTION_HI_DEFAULT,
        ),
        "headline": t(
            SHARE_HUB_HEADLINE, SHARE_HUB_HEADLINE_DEFAULT,
            SHARE_HUB_HEADLINE_HI, SHARE_HUB_HEADLINE_HI_DEFAULT,
        ),
        "intro": t(
            SHARE_HUB_INTRO, SHARE_HUB_INTRO_DEFAULT,
            SHARE_HUB_INTRO_HI, SHARE_HUB_INTRO_HI_DEFAULT,
        ),
        "benefits_heading": t(
            SHARE_HUB_BENEFITS_HEADING, SHARE_HUB_BENEFITS_HEADING_DEFAULT,
            SHARE_HUB_BENEFITS_HEADING_HI, SHARE_HUB_BENEFITS_HEADING_HI_DEFAULT,
        ),
        "benefits": _lines(
            bi_lines(
                SHARE_HUB_BENEFITS, SHARE_HUB_BENEFITS_DEFAULT,
                lang=lang, tenant_id=tenant_id, default_hi=SHARE_HUB_BENEFITS_HI_DEFAULT,
            ),
            SHARE_HUB_BENEFITS_DEFAULT,
        ),
        # The ONE editable incentive claim (CLAUDE.md §4) — resolved, never restated.
        "reward_claim": str(
            _cfg(REFERRER_REWARD_CLAIM, flags.REFERRAL_INCENTIVE_CLAIM, tenant_id) or ""
        ),
        "guidance_heading": t(
            SHARE_HUB_GUIDANCE_HEADING, SHARE_HUB_GUIDANCE_HEADING_DEFAULT,
            SHARE_HUB_GUIDANCE_HEADING_HI, SHARE_HUB_GUIDANCE_HEADING_HI_DEFAULT,
        ),
        "guidance": _lines(
            bi_lines(
                SHARE_HUB_GUIDANCE, SHARE_HUB_GUIDANCE_DEFAULT,
                lang=lang, tenant_id=tenant_id, default_hi=SHARE_HUB_GUIDANCE_HI_DEFAULT,
            ),
            SHARE_HUB_GUIDANCE_DEFAULT,
        ),
        "my_link": link,
        "share_message": message,
        "buttons": buttons,
        "primary_button": primary_button,
        "secondary_buttons": secondary_buttons,
        "native_share_channel": NATIVE_SHARE_CHANNEL,
        "copy_channel": COPY_CHANNEL,
        "share_images": _share_images(tenant_id),
        # Cross-link, only when the other surface is actually mounted. Carries the
        # current lang so the referrer stays in the language they picked (T-061).
        "records_url": with_lang(f"/rr/{token}", lang) if flags.ENABLE_RECORDS_LINK else "",
        "login_url": _login_url(),
        "og": _og_context(tenant_id),
        "lang": lang,
        "lang_toggle": _hub_lang_toggle(lang, tenant_id),
        "market_risk_warning_hi": market_risk_warning_hi(tenant_id) if lang == "hi" else "",
    }


def _hub_lang_toggle(lang: str, tenant_id: int | None) -> dict:
    """Same toggle contract as `apps.accounts.records._lang_toggle` — a REAL EN<->HI
    link on this page too (Constitution §4), not shared code across apps to keep each
    page's context builder self-contained the way this module already is."""
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


def resolve_share_image_url(value: str) -> str:
    """Turn a configured share-image value into a SAME-ORIGIN render/fetch URL, or "".

    Three shapes are accepted, all same-origin by construction:
      - a bare static path (e.g. "img/poster-1.png") -> resolved via Django `static()`;
      - a site-relative path (starting "/") -> returned as-is;
      - an absolute URL that starts with `PUBLIC_BASE_URL` -> returned as-is.

    Anything else (a different host, a scheme-relative "//" URL to another origin) is
    REJECTED — returns "" rather than the raw value. This is deliberately stricter
    than `apps.referrals.og.absolute_image_url` (which allows any absolute CDN URL for
    the crawler-only OG card): these images are `fetch()`-ed by JS for the native
    share sheet and linked as direct downloads, so a cross-origin value would either
    break `tests/test_no_third_party_origin.py` (a same-origin page pulling a
    cross-origin subresource) or fail CORS in the browser silently. Called from BOTH
    the Preferences-screen save path and here at render time, so a value written
    straight to the DB (bypassing the screen) can't slip past the check either.
    """
    from django.conf import settings
    from django.templatetags.static import static

    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("//"):
        return ""  # scheme-relative: always a different origin from our https: pages
    if value.startswith(("http://", "https://")):
        base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
        if base and value.startswith(base + "/"):
            return value
        return ""
    if value.startswith("/"):
        return value
    return static(value)


def _share_images(tenant_id: int | None) -> list[dict]:
    """Up to two configured share-poster images (T-063), each same-origin-resolved.

    Empty by default (Constitution §4: no image UI until the owner configures one).
    `filename` drives the download button's `download=` attribute and the file name
    handed to `navigator.canShare({files})` — taken from the resolved URL so it always
    matches what actually gets fetched.
    """
    images = []
    for index, key in enumerate((SHARE_HUB_IMAGE_1_URL, SHARE_HUB_IMAGE_2_URL), start=1):
        raw = str(_cfg(key, "", tenant_id) or "")
        url = resolve_share_image_url(raw)
        if not url:
            continue
        filename = url.rsplit("/", 1)[-1] or f"referral-poster-{index}.png"
        images.append({"url": url, "filename": filename})
    return images


def _og_context(tenant_id: int | None) -> dict:
    """Link-preview card for the hub.

    Title/description/site-name reuse the D2 crawler-card keys so the brand says one
    thing everywhere; only the IMAGE gets its own key, because the hub is the page an
    owner will want a dedicated brand card for. `og:url` is the bare public base URL,
    NOT this request's URI — `build_absolute_uri()` would stamp the access token into a
    meta tag that crawlers cache and preview surfaces echo.
    """
    from apps.referrals import og

    return {
        "title": og.cfg(og.TITLE_KEY, "OG_TITLE", tenant_id),
        "description": og.cfg(og.DESCRIPTION_KEY, "OG_DESCRIPTION", tenant_id),
        "site_name": og.cfg(og.SITE_NAME_KEY, "OG_SITE_NAME", tenant_id),
        "image": absolute_image_url(
            str(_cfg(SHARE_HUB_OG_IMAGE_URL, SHARE_HUB_OG_IMAGE_DEFAULT, tenant_id) or "")
        ),
        "url": (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/"),
    }


def _log_view(tenant, identity) -> None:
    """Page view on the immutable stream — client id only. No name, no mobile, and not
    the token: the log is append-only and outlives erasure, so nothing that could
    re-identify a person or replay a live link may enter it (#16/#17)."""
    Event.objects.create(
        tenant=tenant,
        event_type="share_hub_viewed",
        source="share_hub",
        user_type="referrer",
        metadata={"client_id": identity.client_id},
    )


@require_GET
def hub_view(request, token: str):
    """`GET /hub/{token}`. Mounted only when ENABLE_SHARE_HUB is on."""
    lang = resolve_lang(request)
    # No tenant known yet on the failure paths (token unverified) — the central-tier
    # default (tenant_id=None) is the correct, identical-for-everyone fallback config.
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
        return render(
            request,
            "accounts/records_unavailable.html",
            {**fail_ctx, "retry_after": exc.retry_after},
            status=429,
        )

    identity = verify_records_token(token)
    if identity is None:
        # The SAME friendly page /rr/ renders, for the same reason: telling a visitor
        # why the link failed would make this an oracle for which client ids exist.
        return render(
            request,
            "accounts/records_unavailable.html",
            fail_ctx,
            status=404,
        )

    tenant = identity.tenant
    # T-062: now that the tenant is known, re-resolve — explicit ?lang= still wins
    # (unchanged from the fail-path `lang` above); with none present, default to the
    # referrer's stored language instead of hardcoded EN.
    lang = resolve_lang_or_stored(request, tenant.id)
    ctx = hub_ctx(identity, token, lang)
    _log_view(tenant, identity)
    return render(request, "accounts/share_hub.html", ctx)
