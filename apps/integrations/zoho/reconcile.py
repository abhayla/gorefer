"""Conversion reconciler — poll Zoho **Contacts** for account openings (P0, 2026-07-26).

WHY THIS EXISTS
---------------
The webhook alone was silently delivering nothing for a month. Two independent causes, both
found on 2026-07-26:

1. **Wrong module.** The ingest was built around Zoho *Leads* (it matches `zoho_lead_id`, and
   `followups.services.has_converted` reads `Lead.status`) — but a Zoho lead that converts
   BECOMES A CONTACT. The account-opened event never happens in the module anything watched,
   so the workflow rule never fired and `POST /api/zoho/status-webhook` was never called.
2. **Nothing was watching.** With no reconciliation, "no conversions arrived" and "no
   conversions happened" look identical. Six real openings — three of them referred — sat
   uncredited while the dashboard and the 21:30 report both said `accounts_opened: 0`.

So this module does NOT replace the webhook; it makes the webhook's delivery non-critical.
A missed, failed or mis-triggered webhook self-heals on the next sweep. That is the property
that was missing, and it is worth more than the trigger fix on its own.

GUARDRAIL 2 IS RESPECTED. This reads Zoho and hands every row to
`apps.integrations.zoho.ingest.ingest_conversion` — the single sanctioned writer of
conversion/account status. It never sets status itself, and never infers a conversion Zoho
does not assert.

FIELD MAP (Zoho Contacts → webhook payload), discovered from the live layout:
    ClientId            -> opener_zerodha_account_id
    Referrer_Client_Id  -> referrer_client_id      (blank ⇒ credit NOBODY, never guess)
    Account_Opened_On   -> account_opened_at       (the TRUE opening date, ADR-017)
    Account_Status      -> status                  (null in practice; ingest defaults it)
    Full_Name           -> opener_name
"""
from __future__ import annotations

import logging
import re

from django.utils import timezone

from apps.config.cascade import resolve
from apps.integrations.zoho import ingest
from apps.integrations.zoho.client import ZohoHttpClient

logger = logging.getLogger("gorefer.zoho.reconcile")

# Cascade keys — per CLAUDE.md §6d, behaviour is configuration, not code.
WATERMARK_KEY = "zoho_reconcile_since"          # ISO date; only look at openings on/after this
ENABLED_KEY = "zoho_reconcile_enabled"
ACCOUNT_PATTERN_KEY = "zoho_reconcile_account_pattern"

# Zerodha client ids are 6 alphanumerics (RJ4521, EKU497, CWD202). This filter matters:
# the SAME Contacts module holds non-Zerodha accounts — `AACK095261` (AngelOne) sits right
# beside the Zerodha rows. Without it the reconciler would invent conversions for another
# broker's customers and credit PIFS referrers for accounts PIFS never opened.
DEFAULT_ACCOUNT_PATTERN = r"^[A-Z]{2,3}[0-9]{3,4}$"

DEFAULT_SINCE = "2026-07-01"


def _cfg(key, default, tenant_id=None):
    try:
        return resolve(key, tenant_id=tenant_id, default=default)
    except Exception:
        return default


def _as_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


FIELDS = ("id", "Full_Name", "Mobile", "ClientId", "Referrer_Client_Id",
          "Referrer_Name", "Account_Opened_On", "Account_Status")


def fetch_opened_contacts(since: str, *, client: ZohoHttpClient | None = None) -> list[dict]:
    """Fetch Contacts whose account opened on/after `since`.

    Uses `/crm/v8/Contacts/search`, the SAME endpoint `read.py` already uses in production —
    deliberately NOT COQL. The live refresh token has no COQL scope (`/crm/v8/coql` returns
    `OAUTH_SCOPE_MISMATCH`), and requiring a new scope would mean the owner re-authorising
    Zoho before conversions could flow again. Search needs no new permission.

    Paginated: a `since` covering a long backfill window can exceed one page, and silently
    processing only the first 200 would look like success while dropping conversions.
    """
    client = client or ZohoHttpClient()
    rows: list[dict] = []
    page = 1
    while page <= 20:  # hard stop; 4000 openings is far beyond any real window
        resp = client.get(
            "/crm/v8/Contacts/search",
            params={
                "criteria": f"(Account_Opened_On:greater_equal:{since})",
                "fields": ",".join(FIELDS),
                "per_page": 200,
                "page": page,
            },
        )
        batch = (resp or {}).get("data") or []
        rows.extend(batch)
        info = (resp or {}).get("info") or {}
        if not batch or not info.get("more_records"):
            break
        page += 1
    rows.sort(key=lambda r: r.get("Account_Opened_On") or "")
    return rows


def reconcile_conversions(*, tenant=None, since: str | None = None, dry_run: bool = False) -> dict:
    """Ingest every Zoho-Contacts account opening we do not already hold.

    Idempotent twice over: `ingest_conversion` dedupes on `event_id` via
    ZohoSyncIdempotency, and re-ingesting an unchanged row is a no-op update. So this is safe
    to run every few minutes forever.
    """
    from apps.tenants.resolve import get_bootstrap_tenant

    tenant = tenant or get_bootstrap_tenant()
    tid = getattr(tenant, "id", None)

    if not _as_bool(_cfg(ENABLED_KEY, True, tid)):
        return {"skipped": "disabled"}

    since = since or str(_cfg(WATERMARK_KEY, DEFAULT_SINCE, tid))
    pattern = re.compile(str(_cfg(ACCOUNT_PATTERN_KEY, DEFAULT_ACCOUNT_PATTERN, tid)))

    counts = {"seen": 0, "ingested": 0, "already_ingested": 0, "skipped_no_client_id": 0,
              "skipped_not_zerodha": 0, "failed": 0, "since": since}
    try:
        rows = fetch_opened_contacts(since)
    except Exception:
        logger.exception("zoho reconcile: Contacts query failed")
        counts["failed"] = 1
        return counts

    for row in rows:
        counts["seen"] += 1
        account = (row.get("ClientId") or "").strip()
        if not account:
            counts["skipped_no_client_id"] += 1
            continue
        if not pattern.match(account.upper()):
            # e.g. AACK095261 — an AngelOne account sharing the module. Not ours.
            counts["skipped_not_zerodha"] += 1
            continue

        payload = {
            # Stable per contact+date, so a re-run dedupes instead of duplicating.
            "event_id": f"reconcile:{row.get('id')}:{row.get('Account_Opened_On')}",
            "opener_zerodha_account_id": account,
            "zoho_lead_id": str(row.get("id") or ""),
            "opener_name": row.get("Full_Name") or "",
            # Blank stays blank: no referrer in Zoho ⇒ credit nobody (ADR-013/016).
            "referrer_client_id": (row.get("Referrer_Client_Id") or "").strip(),
            "status": row.get("Account_Status") or "account opened",
            "account_opened_at": row.get("Account_Opened_On") or "",
        }
        if dry_run:
            # Report what would ACTUALLY happen, not what we hope would. Counting every row
            # as "would ingest" made a fully-caught-up reconciler look like it had 6 rows of
            # real work pending — which is exactly what masked the counting bug below on
            # 2026-07-27: the dry-run said `ingested: 6, failed: 0` while every scheduled run
            # was recording `ingested: 0, failed: 6`.
            from apps.integrations.models import ZohoSyncIdempotency

            key = ingest._dedupe_key(payload)
            done = ZohoSyncIdempotency.objects.for_tenant(tenant).filter(
                dedupe_key=key, processed_at__isnull=False
            ).exists()
            if done:
                counts["already_ingested"] += 1
            else:
                logger.info(
                    "zoho reconcile DRY-RUN would ingest %s",
                    payload["opener_zerodha_account_id"],
                )
                counts["ingested"] += 1
            continue
        try:
            ingest.ingest_conversion(tenant=tenant, payload=payload)
            counts["ingested"] += 1
        except ingest.DuplicateDelivery:
            # THE NORMAL OUTCOME, not an error. A reconciler replays EVERY row since the
            # watermark on every sweep, so almost all of them are already ingested — that is
            # precisely the self-healing property this module exists to provide.
            #
            # Counting it as `failed` (the bug, found 2026-07-27) meant prod logged
            # `failed: 6` every 15 minutes forever. Worse than the noise: it MASKED real
            # failures — a genuinely broken 7th opening would have been invisible among six
            # permanent ones, which is the exact blindness the reconciler was built to end.
            counts["already_ingested"] += 1
        except Exception:
            logger.exception("zoho reconcile: ingest failed for %s", account)
            counts["failed"] += 1

    logger.info("zoho reconcile finished: %s", counts)
    counts["ran_at"] = timezone.now().isoformat()
    return counts
