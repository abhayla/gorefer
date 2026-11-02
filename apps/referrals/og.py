"""Link-preview (Open Graph) card for crawlers — D2, owner decision 2026-07-26.

A forwarded referral link used to 302 the CRAWLER too, so WhatsApp built its preview from
the partner's page: every shared link showed the partner's branding instead of PIFS's, on
the one surface a friend sees before tapping. M11 always specified a PIFS card.

Humans are unaffected — they still get the 302. Only a bot/preview user-agent gets this.
Copy is config-driven (CLAUDE.md §6d) so the owner can reword it without a deploy.
"""
from __future__ import annotations

import logging
import re

from django.shortcuts import render

from apps.config.cascade import resolve

TITLE_KEY = "og_preview_title"
DESCRIPTION_KEY = "og_preview_description"
SITE_NAME_KEY = "og_preview_site_name"
IMAGE_KEY = "og_preview_image_url"

# Defaults come from the EXISTING M11 settings (OG_TITLE/OG_DESCRIPTION/OG_SITE_NAME/OG_IMAGE)
# that already drive the landing page's card — so the crawler card and the landing card say the
# same thing instead of drifting apart as two competing sources of copy. The cascade then layers
# a per-tenant override on top (CLAUDE.md §6d).
#
# M11 shipped that card, but it only ever rendered in LANDING_MODE=page. PIFS runs `direct`, so
# in practice the crawler was redirected and the card was never served — which is why forwarded
# links showed the partner's branding despite M11 claiming otherwise.


def _cfg(key: str, setting_name: str, tenant_id: int | None) -> str:
    from django.conf import settings

    default = str(getattr(settings, setting_name, "") or "")
    try:
        return str(resolve(key, tenant_id=tenant_id, default=default) or default)
    except Exception:
        return default


#: Public alias — the T-053 share hub reuses these same title/description/site-name
#: keys so the brand card says ONE thing across every surface (the drift this module's
#: own docstring was written about).
cfg = _cfg


def absolute_image_url(image: str) -> str:
    """THE one way to turn a configured OG image into a crawler-usable absolute URL.

    Open Graph requires an ABSOLUTE url — a crawler has no page context to resolve a
    relative one against. Two things have to happen and both were missing here:
      1. the value must be absolute, and
      2. a bare path like the default `img/og-card.png` is a STATIC path, so it must go
         through `static()` — the asset is served at `/static/img/...`, and `/img/...`
         is a 404.

    Found live 2026-07-26: the D2 crawler card emitted `og:image="img/og-card.png"`, so
    every forwarded referral link rendered a preview with NO image — on precisely the
    surface D2 exists to fix. M11's landing card (`views.py:_og_context`) already had this
    logic; the crawler card did not reuse it. Both now call THIS function, so the two
    cards cannot drift apart again (same reasoning as `nudge_link_for()` being the single
    link builder).

    An already-absolute configured value is returned untouched, so an operator can point
    the cascade key at a CDN URL without code changes (CLAUDE.md §6d).
    """
    from django.conf import settings
    from django.templatetags.static import static

    image = (image or "").strip()
    if not image:
        return ""
    if image.startswith(("http://", "https://", "//")):
        return image
    base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    return base + static(image)


def render_preview(request, *, tenant_id: int | None = None, client_id: str | None = None,
                   tenant=None):
    """200 with an OG card. NEVER a redirect — a crawler that follows a 302 renders the
    partner's card, which is the whole bug this fixes.

    v2 (owner 2026-11-03): when `preview_card_v2_enabled` is on for the tenant, the card is
    the server-rendered v2 image and v2 copy. Only `referral_redirect`'s bot branch passes
    `client_id`, so only a referral link can get the referrer-name card; every other caller
    gets the generic v2 card. With v2 off this is exactly the v1 output.
    """
    if v2_enabled(tenant_id):
        if tenant is None and tenant_id is not None:
            from apps.tenants.models import Tenant

            tenant = Tenant.objects.filter(id=tenant_id).first()
        ctx = v2_meta(tenant_id, tenant=tenant, client_id=client_id)
        ctx["og_url"] = request.build_absolute_uri()
        return render(request, "og_preview.html", ctx)
    return render(
        request,
        "og_preview.html",
        {
            "og_title": _cfg(TITLE_KEY, "OG_TITLE", tenant_id),
            "og_description": _cfg(DESCRIPTION_KEY, "OG_DESCRIPTION", tenant_id),
            "og_site_name": _cfg(SITE_NAME_KEY, "OG_SITE_NAME", tenant_id),
            "og_image": absolute_image_url(_cfg(IMAGE_KEY, "OG_IMAGE", tenant_id)),
            "og_url": request.build_absolute_uri(),
        },
    )


# =====================================================================================
# Preview card v2 (owner 2026-11-03) — a server-rendered card + the referrer's first name.
#
# Two tenant switches, both default OFF (`preview_card_v2_enabled`,
# `preview_card_referrer_name_enabled`). With v2 OFF nothing below runs and every public
# output is byte-identical to the v1 card (snapshot-tested). Every word on the card is a
# cascade key (rail E-6); the legal band always uses the LOCKED compliance values.
# =====================================================================================

logger = logging.getLogger(__name__)
NAME_RE = re.compile(r"[A-Za-z]{2,15}")
CARD_CACHE_PREFIX = "ogcard:v1:"
CARD_CACHE_SECONDS = 7 * 24 * 3600
VERSION_CHARS = 10


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _switch(key: str, tenant_id: int | None) -> bool:
    try:
        return _as_bool(resolve(key, tenant_id=tenant_id, default=False))
    except Exception:  # a broken config row must never turn the card ON by accident
        return False


def v2_enabled(tenant_id: int | None) -> bool:
    from apps.config.preferences import PREVIEW_CARD_V2_ENABLED

    return _switch(PREVIEW_CARD_V2_ENABLED, tenant_id)


def name_enabled(tenant_id: int | None) -> bool:
    """The name switch only counts when v2 itself is on."""
    from apps.config.preferences import PREVIEW_CARD_NAME_ENABLED

    return v2_enabled(tenant_id) and _switch(PREVIEW_CARD_NAME_ENABLED, tenant_id)


def _text(key: str, default: str, tenant_id: int | None) -> str:
    try:
        value = resolve(key, tenant_id=tenant_id, default=default)
    except Exception:
        value = default
    value = str(value if value is not None else "").strip()
    return value or default


def _locked(key: str) -> str:
    """The SAME locked resolver every page uses (context_processors) — never a tenant key."""
    from django.conf import settings

    fallback = getattr(settings, key.upper(), "")
    try:
        return str(resolve(key, default=fallback) or fallback)
    except Exception:
        return fallback


def valid_display_name(raw: str | None) -> str | None:
    """`^[A-Za-z]{2,15}$` after strip, else None. ASCII letters only (no digits, accents,
    markup): the name lands in a public image and a public meta tag."""
    value = (raw or "").strip()
    return value if NAME_RE.fullmatch(value) else None


def customer_display_name(customer) -> str | None:
    """`preview_name` when set, else the first word of the Zoho first name; None if invalid."""
    chosen = (customer.preview_name or "").strip()
    if not chosen:
        parts = (customer.first_name or "").split()
        chosen = parts[0] if parts else ""
    return valid_display_name(chosen)


def live_customer(tenant, normalized: str):
    """The live Customer row for this id on an active program, or None."""
    from apps.referrals.models import Customer

    tenant_id = getattr(tenant, "id", tenant)
    return (
        Customer.objects.for_tenant(tenant_id)
        .filter(client_id=normalized, deleted_at__isnull=True, program__status="active")
        .order_by("id")
        .first()
    )


def named_first_name(tenant, raw_client_id: str | None) -> str | None:
    """The first name to show on this referrer's card, or None for the generic card.

    Every gate must pass: both switches ON; the id is a valid, non-placeholder id for the
    tenant's partner; the referrer identity is not soft-deleted; a live Customer row exists
    with `show_name_on_preview=True`; and its display name is valid. Anything else -> None.
    """
    from apps.referrals.validators import InvalidClientId, is_deleted_referrer, validate_client_id_for

    tenant_id = getattr(tenant, "id", None)
    if tenant is None or not raw_client_id or not name_enabled(tenant_id):
        return None
    try:
        normalized = validate_client_id_for(tenant, raw_client_id)
    except InvalidClientId:
        return None
    if is_deleted_referrer(tenant, normalized):
        return None
    customer = live_customer(tenant, normalized)
    if customer is None or not customer.show_name_on_preview:
        return None
    return customer_display_name(customer)


def v2_card_text(tenant_id: int | None, first_name: str | None = None):
    """Resolve every string the v2 card draws. `first_name` set -> the named variant."""
    from apps.config import preferences as p
    from apps.referrals.preview_card import CardText

    if first_name:
        eyebrow = _text(p.PREVIEW_CARD_NAMED_EYEBROW, p.PREVIEW_CARD_NAMED_EYEBROW_DEFAULT, tenant_id)
        eyebrow = eyebrow.replace("{first_name}", first_name).upper()
    else:
        eyebrow = _text(p.PREVIEW_CARD_EYEBROW, p.PREVIEW_CARD_EYEBROW_DEFAULT, tenant_id)
    return CardText(
        eyebrow=eyebrow,
        headline=_text(p.PREVIEW_CARD_HEADLINE, p.PREVIEW_CARD_HEADLINE_DEFAULT, tenant_id),
        price_big=_text(p.PREVIEW_CARD_PRICE_BIG, p.PREVIEW_CARD_PRICE_BIG_DEFAULT, tenant_id),
        price_rest=_text(p.PREVIEW_CARD_PRICE_REST, p.PREVIEW_CARD_PRICE_REST_DEFAULT, tenant_id),
        docs=_text(p.PREVIEW_CARD_DOCS_LINE, p.PREVIEW_CARD_DOCS_LINE_DEFAULT, tenant_id),
        cta=_text(p.PREVIEW_CARD_CTA, p.PREVIEW_CARD_CTA_DEFAULT, tenant_id),
        legal_disclosure=_locked("ap_disclosure_block"),
        legal_risk=_locked("market_risk_warning"),
        named=bool(first_name),
    )


def card_png(card_text) -> bytes:
    """Rendered PNG bytes, cached 7 days under the text fingerprint (DB cache)."""
    from django.core.cache import cache

    from apps.referrals.preview_card import render_card

    key = CARD_CACHE_PREFIX + card_text.fingerprint()
    try:
        cached = cache.get(key)
    except Exception:
        cached = None
    if cached:
        return cached
    try:
        png = render_card(card_text).png
    except Exception:
        # Never a 500 from an image route: a broken image kills the whole preview. Fall
        # back without caching, so the fixed copy shows as soon as the operator corrects it.
        logger.error("preview card v2: render failed for %s; serving a fallback card",
                     card_text.fingerprint()[:VERSION_CHARS], exc_info=True)
        return _fallback_png(card_text)
    try:
        cache.set(key, png, timeout=CARD_CACHE_SECONDS)
    except Exception:
        pass  # a cache outage costs a re-render, never the image
    return png


def _fallback_png(card_text) -> bytes:
    """The generic card from the shipped default copy; if even that fails (e.g. the locked
    legal text grew too tall for the layout), the committed v1 static card."""
    from pathlib import Path

    from django.conf import settings

    from apps.config import preferences as p
    from apps.referrals.preview_card import CardText, render_card

    try:
        return render_card(CardText(
            eyebrow=p.PREVIEW_CARD_EYEBROW_DEFAULT, headline=p.PREVIEW_CARD_HEADLINE_DEFAULT,
            price_big=p.PREVIEW_CARD_PRICE_BIG_DEFAULT, price_rest=p.PREVIEW_CARD_PRICE_REST_DEFAULT,
            docs=p.PREVIEW_CARD_DOCS_LINE_DEFAULT, cta=p.PREVIEW_CARD_CTA_DEFAULT,
            legal_disclosure=card_text.legal_disclosure, legal_risk=card_text.legal_risk,
        )).png
    except Exception:
        logger.error("preview card v2: default card failed too; serving the v1 static card",
                     exc_info=True)
        return (Path(settings.BASE_DIR) / "static" / "img" / "referral-preview-card.png").read_bytes()


def card_version(card_text) -> str:
    return card_text.fingerprint()[:VERSION_CHARS]


def v2_image_url(tenant_id: int | None, *, client_id: str | None = None,
                 first_name: str | None = None) -> str:
    """Absolute `og:image` for the v2 card; the named route only when the name is eligible."""
    from django.conf import settings
    from django.urls import reverse

    text = v2_card_text(tenant_id, first_name)
    if first_name and client_id:
        path = reverse("og_card_named", kwargs={"client_id": client_id})
    else:
        path = reverse("og_card")
    base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    return f"{base}{path}?v={card_version(text)}"


def v2_meta(tenant_id: int | None, *, tenant=None, client_id: str | None = None) -> dict:
    """og title/description/site/image for v2. Named only when `client_id` is eligible."""
    from apps.config import preferences as p

    first_name = named_first_name(tenant, client_id) if client_id else None
    normalized = None
    if first_name:
        from apps.referrals.validators import validate_client_id_for

        normalized = validate_client_id_for(tenant, client_id)
        title = _text(p.PREVIEW_CARD_OG_TITLE_NAMED, p.PREVIEW_CARD_OG_TITLE_NAMED_DEFAULT, tenant_id)
        title = title.replace("{first_name}", first_name.capitalize())
    else:
        title = _text(p.PREVIEW_CARD_OG_TITLE, p.PREVIEW_CARD_OG_TITLE_DEFAULT, tenant_id)
    return {
        "og_title": title,
        "og_description": _text(p.PREVIEW_CARD_OG_DESCRIPTION, p.PREVIEW_CARD_OG_DESCRIPTION_DEFAULT,
                                tenant_id),
        "og_site_name": _text(p.PREVIEW_CARD_OG_SITE_NAME, p.PREVIEW_CARD_OG_SITE_NAME_DEFAULT, tenant_id),
        "og_image": v2_image_url(tenant_id, client_id=normalized, first_name=first_name),
        "og_v2": True,
    }
