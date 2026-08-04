"""`golive_smoke` — drive the FULL capture loop on demand and report what happened.

    python manage.py golive_smoke --referrer EKU497 --mobile 9876543210 [--name X] [--email Y]

Why this exists: verifying go-live previously meant a human filling the landing
form. This runs the same loop head-lessly so any Code session (or a scheduled task)
can exercise it and the DA can then verify the Zoho write / Wati send via MCP.

What it does and does NOT do:
  - Runs the REAL service layer (`redirect_service` lazy click + `lead_service.capture_lead`).
    It does not re-implement capture; a smoke test that tests a copy of the code
    proves nothing about the code that actually runs.
  - Independent of LANDING_MODE: it calls the capture service directly rather than
    driving /r/{id}, so capture is testable even while the site is in `direct` mode
    (where a browser never sees the form).
  - Honors the live flags exactly as prod does. Flags OFF ⇒ the adapters are the
    log-only ones ⇒ zero live effect. This command NEVER flips a flag.
  - NEVER fabricates status: conversion/account status is Zoho-inbound only
    (guardrail #2). This command only reports what the loop actually produced.
  - PII (name/mobile/email) stays on prospect/lead and out of the event log (#16),
    because it goes through the same service that enforces that.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.common.phone import normalize_phone
from apps.config.integration_flags import flag_source, resolve_flag
from apps.integrations import services
from apps.referrals import redirect_service
from apps.referrals.lead_service import capture_lead
from apps.referrals.models import Lead
from apps.referrals.validators import InvalidClientId, validate_client_id
from apps.tenants.resolve import get_current_tenant

SYNTH_UA = "GoReferGoLiveSmoke/1.0 (management-command; human-equivalent)"


class Command(BaseCommand):
    help = "Run the full referral capture loop end-to-end and report the result."

    def add_arguments(self, parser):
        parser.add_argument("--referrer", required=True, help="Referrer's Zerodha client id (e.g. EKU497)")
        parser.add_argument("--mobile", required=True, help="Prospect mobile (10-digit Indian)")
        parser.add_argument("--name", default="GoLive Smoke", help="Prospect name")
        parser.add_argument("--email", default="", help="Prospect email")
        parser.add_argument("--json", action="store_true", help="Emit the report as JSON only")

    def handle(self, *args, **opts):
        report = run_smoke(
            referrer=opts["referrer"],
            mobile=opts["mobile"],
            name=opts["name"],
            email=opts["email"],
        )
        if opts["json"]:
            self.stdout.write(json.dumps(report, indent=2, default=str))
        else:
            self.stdout.write(_render(report))
        return None


def run_smoke(*, referrer: str, mobile: str, name: str = "GoLive Smoke", email: str = "") -> dict:
    """Execute the loop and return a structured report. Importable, so the test
    asserts on the same path the operator runs."""
    try:
        client_id = validate_client_id(referrer)
    except InvalidClientId as exc:
        raise CommandError(f"invalid --referrer: {exc}") from exc

    canonical_mobile = normalize_phone(mobile)
    if not canonical_mobile:
        raise CommandError("invalid --mobile: could not normalize")

    tenant = get_current_tenant()
    if tenant is None:
        raise CommandError("no bootstrap tenant — run `manage.py seed_program` first")

    report: dict = {
        "referrer_client_id": client_id,
        "flags": {
            key: {
                "value": resolve_flag(key, tenant_id=tenant.id),
                "source": flag_source(key, tenant_id=tenant.id),
            }
            for key in ("ENABLE_ZOHO_WRITE", "ENABLE_WATI_SEND", "ENABLE_ZOHO_READ")
        },
        "errors": [],
    }

    # --- 1. Synthesize the click: lazy referrer identity + journey + click event ---
    # Same service the real /r/{client_id} hit uses, so the journey is shaped exactly
    # like a browser-created one. A visitor_id stands in for the first-party cookie.
    # NOTE: the click event is written on_commit, so everything below runs inside an
    # atomic block that we let COMMIT — otherwise the hooks would never fire and the
    # smoke run would report a loop that in fact did nothing.
    visitor_id = f"smoke-{canonical_mobile[-4:]}"
    try:
        with transaction.atomic():
            _destination, is_human = redirect_service.handle_direct_redirect(
                tenant=tenant,
                client_id=client_id,
                visitor_id=visitor_id,
                user_agent=SYNTH_UA,
                raw_ip=None,  # no real IP to record; VisitorPII stays clean
            )
        report["click"] = {"is_human_click": is_human}
    except Exception as exc:
        report["errors"].append(f"click: {exc!r}")
        report["ok"] = False
        return report

    referral = redirect_service._lazy_get_or_create_referral(
        tenant, redirect_service._active_program(tenant), client_id
    )
    report["journey_id"] = referral.pk
    report["gorefer_reference"] = f"GR-{referral.pk}"

    # --- 2. Capture the lead through the REAL service (capture-first) -------------
    # capture_lead is idempotent on (referral, normalized mobile): a re-run returns
    # the existing lead rather than creating a twin. Its on_commit hooks fire the
    # WATI notifications and the Zoho upsert per the live flags.
    observed: dict = {}
    try:
        with services.observe_zoho_upsert_action(observed), transaction.atomic():
            lead = capture_lead(
                tenant=tenant,
                referral=referral,
                name=name,
                mobile=canonical_mobile,
                email=email,
                city="",
                consent=True,  # smoke run stands in for a consented form submit
                submitted_by="friend",
                lead_source="landing",
            )
    except Exception as exc:
        report["errors"].append(f"capture: {exc!r}")
        report["ok"] = False
        return report

    lead.refresh_from_db()
    report["lead_id"] = lead.pk
    report["lead_status"] = lead.status

    # --- 3. Report what the flags actually produced -------------------------------
    report["zoho"] = _zoho_result(lead, observed.get("action"))
    report["notifications"] = _notification_results(referral)
    report["conversion_status"] = lead.referral.conversion_status or ""
    report["conversion_note"] = "status is Zoho-inbound only; never set by this command"
    report["ok"] = not report["errors"]
    return report


def _zoho_result(lead: Lead, observed_action: str | None) -> dict:
    """What the Zoho leg did.

    `insert|update` is reported from the adapter's own LeadWriteResult.action —
    Zoho decides create-vs-update server-side on the mobile dedup key, so `update`
    on a re-run IS the idempotency proof (no twin). The action is not persisted on
    the Lead, so it is observed in-process (see `_observe_zoho_action`) rather than
    inferred from sync_status, which cannot tell insert from update.
    `log-only` when the flag is off: no network call was made.
    """
    if not resolve_flag("ENABLE_ZOHO_WRITE"):
        action = "log-only"
    elif observed_action:
        action = observed_action
    elif lead.zoho_sync_status == Lead.SYNC_SYNCED:
        # Synced, but this run didn't perform the write (an earlier run did, and the
        # task no-ops on an already-synced lead). Don't guess insert vs update.
        action = "already-synced (no write this run)"
    else:
        action = lead.zoho_sync_status or "pending"
    return {
        "action": action,
        "zoho_lead_id": lead.zoho_lead_id or "",
        "sync_status": lead.zoho_sync_status,
        "error": lead.zoho_last_error or "",
    }


def _notification_results(referral) -> list[dict]:
    """Per-recipient outcome. A skipped role is reported WITH its reason (opt-out,
    unknown phone, routed off) rather than omitted — the operator needs to see that
    it did not go, and why."""
    from apps.integrations.models import Notification

    rows = []
    for n in Notification.objects.filter(referral=referral).order_by("recipient_role", "id"):
        status = n.status
        if status == "skipped":
            outcome = f"skipped ({n.skip_reason or 'no reason recorded'})"
        elif not resolve_flag("ENABLE_WATI_SEND"):
            outcome = "log-only"
        else:
            outcome = status
        rows.append({
            "role": n.recipient_role,
            "recipient": n.recipient_mobile or "—",
            "template": n.template,
            "status": outcome,
            "meta_error_code": n.meta_error_code,
            "failure": n.failure_classification or "",
        })
    return rows


def _render(r: dict) -> str:
    lines = []
    lines.append("=" * 66)
    lines.append("  GoRefer go-live smoke — full capture loop")
    lines.append("=" * 66)
    lines.append("")
    lines.append("Flags (live, as resolved by the app):")
    for key, f in r["flags"].items():
        lines.append(f"  {key:<20} {str(f['value']):<6} (source={f['source']})")
    lines.append("")
    lines.append(f"Referrer client id : {r['referrer_client_id']}")
    lines.append(f"Journey id         : {r.get('journey_id', '—')}")
    lines.append(f"GoRefer reference  : {r.get('gorefer_reference', '—')}")
    lines.append(f"Lead id            : {r.get('lead_id', '—')}  (status={r.get('lead_status', '—')})")
    lines.append("")
    z = r.get("zoho") or {}
    lines.append("Zoho:")
    lines.append(f"  action        : {z.get('action', '—')}")
    lines.append(f"  zoho_lead_id  : {z.get('zoho_lead_id') or '—'}")
    lines.append(f"  sync_status   : {z.get('sync_status', '—')}")
    if z.get("error"):
        lines.append(f"  error         : {z['error']}")
    lines.append("")
    lines.append("Notifications:")
    for n in r.get("notifications", []):
        line = f"  {n['role']:<9} {n['recipient']:<14} {n['status']}"
        if n.get("meta_error_code"):
            line += f"  [meta {n['meta_error_code']} {n.get('failure', '')}]"
        lines.append(line)
    if not r.get("notifications"):
        lines.append("  (none created)")
    lines.append("")
    status = r.get("conversion_status") or "(none)"
    lines.append(f"Conversion status  : {status} — {r.get('conversion_note', '')}")
    if r.get("errors"):
        lines.append("")
        lines.append("ERRORS:")
        for e in r["errors"]:
            lines.append(f"  - {e}")
    lines.append("")
    lines.append("RESULT: " + ("OK" if r.get("ok") else "FAILED"))
    lines.append("=" * 66)
    return "\n".join(lines)
