"""Link-preview (Open Graph) card for crawlers — D2, owner decision 2026-07-26.

A forwarded referral link used to 302 the CRAWLER too, so WhatsApp built its preview from
the partner's page: every shared link showed the partner's branding instead of PIFS's, on
the one surface a friend sees before tapping. M11 always specified a PIFS card.

Humans are unaffected — they still get the 302. Only a bot/preview user-agent gets this.
Copy is config-driven (CLAUDE.md §6d) so the owner can reword it without a deploy.
"""
from __future__ import annotations

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


def render_preview(request, *, tenant_id: int | None = None):
    """200 with an OG card. NEVER a redirect — a crawler that follows a 302 renders the
    partner's card, which is the whole bug this fixes."""
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
