"""Bilingual (EN/HI) copy resolution for the hub/records web surfaces (T-061).

Not Django i18n/gettext (CLAUDE.md pre-made decision #1) — this follows the repo's
existing cascade pattern: every owner-editable string already resolves through
`apps.config.cascade.resolve()`, so a Hindi twin is just a second cascade key,
`{base_key}_hi`, resolved beside the existing `{base_key}` (EN) one.

Language selection is a plain query param, `?lang=hi`, validated against
`LANGUAGES` — anything else (missing, `en`, garbage) resolves to `en`. There is no
session/cookie persistence; the caller is responsible for carrying `lang` across
internal links (see `lang_query_suffix` / `with_lang`).

The load-bearing guarantee: a HI twin that is unset, blank, or whitespace-only
FALLS BACK to the EN value — a surface can never render blank because one HI key
was missed when the estate was translated (DoD, T-061).
"""
from __future__ import annotations

from django.utils.http import urlencode

from .cascade import resolve as resolve_config

LANG_EN = "en"
LANG_HI = "hi"
LANGUAGES = (LANG_EN, LANG_HI)

LANG_PARAM = "lang"


def resolve_lang(request) -> str:
    """The effective page language for this request. Invalid/missing -> EN."""
    raw = str(request.GET.get(LANG_PARAM, "") or "").strip().lower()
    return raw if raw in LANGUAGES else LANG_EN


def hi_key(base_key: str) -> str:
    return f"{base_key}_hi"


def bi_text(base_key: str, default_en, *, lang: str, tenant_id: int | None, default_hi=None) -> str:
    """Resolve a single bilingual copy string.

    `lang == "hi"` resolves `{base_key}_hi` (default `default_hi`, or `default_en`
    when no HI default was authored) and falls back to the EN value whenever the
    resolved HI value is unset/blank. Any other `lang` resolves EN directly.
    """
    en_value = resolve_config(base_key, tenant_id=tenant_id, default=default_en)
    if lang != LANG_HI:
        return en_value
    hi_default = default_en if default_hi is None else default_hi
    hi_value = resolve_config(hi_key(base_key), tenant_id=tenant_id, default=hi_default)
    if isinstance(hi_value, str) and not hi_value.strip():
        return en_value
    return hi_value if hi_value else en_value


def bi_lines(base_key: str, default_en: list, *, lang: str, tenant_id: int | None, default_hi=None) -> list:
    """Same fallback contract as `bi_text`, for a bullet-list (JSON list) value."""
    en_value = resolve_config(base_key, tenant_id=tenant_id, default=default_en)
    if lang != LANG_HI:
        return en_value
    hi_default = default_en if default_hi is None else default_hi
    hi_value = resolve_config(hi_key(base_key), tenant_id=tenant_id, default=hi_default)
    if not hi_value:
        return en_value
    return hi_value


def lang_query_suffix(lang: str) -> str:
    """`?lang=hi` for HI, empty string for EN — EN stays the unparameterized default."""
    return f"?{urlencode({LANG_PARAM: lang})}" if lang == LANG_HI else ""


def with_lang(url: str, lang: str) -> str:
    """Append the current language to an internal cross-link URL, if non-empty."""
    if not url:
        return url
    suffix = lang_query_suffix(lang)
    return f"{url}{suffix}" if suffix else url


def market_risk_warning_hi(tenant_id: int | None) -> str:
    """The Hindi market-risk warning — a SEPARATE, unlocked cascade key, never the
    locked `market_risk_warning` EN key itself (D-1 rail, CLAUDE.md §4/§2c): lower
    tiers can never weaken the compliance-locked EN claim, and this key only ever
    carries an ADDITIONAL Hindi rendering alongside it, never a replacement. Default
    is the wording already approved and live in the HI WhatsApp templates."""
    from .preferences import MARKET_RISK_WARNING_HI, MARKET_RISK_WARNING_HI_DEFAULT

    value = resolve_config(
        MARKET_RISK_WARNING_HI, tenant_id=tenant_id, default=MARKET_RISK_WARNING_HI_DEFAULT
    )
    return value if (isinstance(value, str) and value.strip()) else MARKET_RISK_WARNING_HI_DEFAULT
