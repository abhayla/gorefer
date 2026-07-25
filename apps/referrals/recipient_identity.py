"""Recipient-identity resolver — "who is this message for?" (doc 15).

Given ``(tenant, mobile)``, resolve the recipient's **role** (prospect | referrer |
unknown), their **originating referrer's client_id** (for a prospect), the referrer's
own client_id + **phone** (for the §6.1 referrer-nudge), and **language** (from the
EXISTING ``referrer_language`` cascade key — doc 15 §8, NOT a new signal).

Pure + read-only + defensively wrapped: a schema surprise returns ``role="unknown"``,
never raises into a send sweep (mirrors ``apps.followups.services.has_converted``).
"""
from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from apps.common.phone import normalize_phone

ROLE_PROSPECT = "prospect"
ROLE_REFERRER = "referrer"
ROLE_UNKNOWN = "unknown"

# A Lead is "in progress" until Zoho marks it account_opened (the engaged-exit signal
# apps.followups.services.has_converted already reads). Kept in sync deliberately.
ACCOUNT_OPENED = "account_opened"

# doc 15 §5 / §8 config key — how a prospect nudge picks its link.
LINK_MODE_KEY = "followup_link_mode"
LINK_MODE_DEFAULT = "referrer_then_open"  # referrer link if known, else partner-direct /open


@dataclass(frozen=True)
class RecipientIdentity:
    role: str = ROLE_UNKNOWN
    referrer_client_id: str = ""   # a PROSPECT's originating referrer (link to embed); "" if none
    referrer_mobile: str = ""      # that referrer's phone IF GoRefer knows it (§6.1); "" otherwise
    self_client_id: str = ""       # a REFERRER's own client_id (their share link); "" if n/a
    prospect_id: int | None = None
    lead_id: int | None = None
    lang: str = "en"
    confidence: str = "none"       # zoho_credited | lead_join | customer_match | none


def _resolve_lang(tenant_id) -> str:
    """Language from the EXISTING referrer_language rule (doc 15 §8). Never a new key."""
    try:
        from apps.config.cascade import resolve
        from apps.config.preferences import (
            _VALID_LANGUAGES,
            LANG_EN,
            REFERRER_LANGUAGE,
        )

        lang = str(resolve(REFERRER_LANGUAGE, tenant_id=tenant_id, default=LANG_EN) or "").strip().lower()
        return lang if lang in _VALID_LANGUAGES else LANG_EN
    except Exception:
        return "en"


def _referrer_mobile_for(tenant, client_id: str) -> str:
    """The referrer's phone IF GoRefer knows it — a Customer row with a phone (M5 rule).

    Reverses ``notify._referrer_if_known`` (which keys on client_id already). Never
    guesses: no Customer / no phone → "".
    """
    if not client_id:
        return ""
    try:
        from apps.referrals.models import Customer

        cust = (
            Customer.objects.filter(tenant=tenant, client_id=client_id, deleted_at__isnull=True)
            .exclude(mobile="")
            .first()
        )
        return normalize_phone(cust.mobile) if cust else ""
    except Exception:
        return ""


def resolve_recipient(tenant, mobile: str) -> RecipientIdentity:
    """Resolve who ``mobile`` is within ``tenant``. Pure, read-only, never raises."""
    lang = _resolve_lang(getattr(tenant, "id", None))
    try:
        canonical = normalize_phone(mobile)
        if not canonical:
            return RecipientIdentity(role=ROLE_UNKNOWN, lang=lang)

        from apps.referrals.models import Customer, Lead, Prospect

        prospect = (
            Prospect.objects.filter(tenant=tenant, mobile=canonical, deleted_at__isnull=True)
            .order_by("-created_at")
            .first()
        )

        lead = None
        referrer_client_id = ""
        confidence = "none"
        in_progress = False
        if prospect is not None:
            lead = (
                Lead.objects.filter(tenant=tenant, prospect=prospect, deleted_at__isnull=True)
                .select_related("referral", "referral__referral_identity")
                .order_by("-created_at")
                .first()
            )
            if lead is not None:
                ref = lead.referral
                if ref is not None and ref.credited_referrer:
                    referrer_client_id = ref.credited_referrer   # Zoho winner (ADR-016)
                    confidence = "zoho_credited"
                elif ref is not None and ref.referral_identity_id:
                    referrer_client_id = ref.referral_identity.client_id
                    confidence = "lead_join"
                in_progress = lead.status != ACCOUNT_OPENED

        # Customer.mobile may be stored un-normalized (M5 only ever queried it by client_id),
        # so match both the 91-prefixed and bare-10-digit forms.
        candidates = {canonical}
        if canonical.startswith("91") and len(canonical) > 10:
            candidates.add(canonical[2:])
        customer = (
            Customer.objects.filter(
                tenant=tenant, mobile__in=list(candidates), deleted_at__isnull=True
            ).first()
        )
        self_client_id = customer.client_id if customer else ""

        # Precedence (doc 15 §4): a prospect with an incomplete account wins (they need the
        # completion nudge), even if they also refer; else a known referrer; else a prospect
        # (converted / lead-less); else unknown.
        if prospect is not None and in_progress:
            role = ROLE_PROSPECT
        elif customer is not None:
            role = ROLE_REFERRER
            if confidence == "none":
                confidence = "customer_match"
        elif prospect is not None:
            role = ROLE_PROSPECT
        else:
            role = ROLE_UNKNOWN

        return RecipientIdentity(
            role=role,
            referrer_client_id=referrer_client_id,
            referrer_mobile=_referrer_mobile_for(tenant, referrer_client_id),
            self_client_id=self_client_id,
            prospect_id=(prospect.id if prospect is not None else None),
            lead_id=(lead.id if lead is not None else None),
            lang=lang,
            confidence=confidence,
        )
    except Exception:
        return RecipientIdentity(role=ROLE_UNKNOWN, lang=lang)


def prospect_descriptor(tenant, mobile: str) -> str:
    """A referrer-facing label for an idle prospect (doc 15 §6.1.1).

    name (when a Lead/Prospect was captured) → generic. NEVER empty (a WhatsApp template
    variable cannot be blank). The click-derived descriptor (city/channel/date) is a future
    enhancement — it needs a mobile→visitor_id link that GoRefer does not store today.
    """
    try:
        from apps.referrals.models import Prospect

        canonical = normalize_phone(mobile)
        p = (
            Prospect.objects.filter(tenant=tenant, mobile=canonical, deleted_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if p and (p.name or "").strip():
            return p.name.strip()
    except Exception:
        pass
    return "one of your recent referrals"


def _public_host() -> str:
    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    for prefix in ("https://", "http://"):
        if base.startswith(prefix):
            return base[len(prefix):]
    return base


def nudge_link_for(identity: RecipientIdentity, *, tenant_id=None, channel: str = "wa") -> str:
    """The account-opening link to embed in a PROSPECT nudge (doc 15 §5).

    ``referrer_then_open`` (default): the prospect's referrer link ``/r/{channel}/{id}``
    (credits the original referrer, idempotent with their pending application) when known,
    else the partner-direct ``/open`` (PIFS credit). ``open_only`` always ``/open``;
    ``none`` returns "". Bare host, no scheme (matches kit-message convention).
    """
    try:
        from apps.config.cascade import resolve

        mode = str(resolve(LINK_MODE_KEY, tenant_id=tenant_id, default=LINK_MODE_DEFAULT) or "").strip()
    except Exception:
        mode = LINK_MODE_DEFAULT
    if mode == "none":
        return ""
    host = _public_host()
    if mode != "open_only" and identity.referrer_client_id:
        return f"{host}/r/{channel}/{identity.referrer_client_id}"
    return f"{host}/open"
