"""Management command: send the [Referral Records] WhatsApp link (T-057).

    python manage.py send_records_links --client-ids RJ4521,DA1707
    python manage.py send_records_links --client-ids RJ4521,DA1707 --send

DRY-RUN IS THE DEFAULT — it previews every gate (cap, dedupe, opt-out, mobile
resolution) without sending or writing anything. Only `--send` fires real messages,
and only when both `ENABLE_WATI_SEND` and `ENABLE_RECORDS_LINK` are on.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.records_link_send import SendRefused, send_records_links


class Command(BaseCommand):
    help = "Send the Referral Records WhatsApp link to an explicit list of client ids (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--client-ids", required=True,
            help="Comma-separated client ids, e.g. RJ4521,DA1707",
        )
        parser.add_argument("--limit", type=int, default=None, help="Only process the first N client ids")
        parser.add_argument(
            "--send", action="store_true",
            help="Actually send. Without this flag the command only previews (dry-run).",
        )
        parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")

    def handle(self, *args, **options):
        client_ids = [c.strip() for c in (options["client_ids"] or "").split(",") if c.strip()]
        limit = options.get("limit")
        if limit is not None:
            client_ids = client_ids[: max(limit, 0)]
        if not client_ids:
            raise CommandError("--client-ids must name at least one client id")

        try:
            result = send_records_links(client_ids, dry_run=not options["send"])
        except SendRefused as exc:
            raise CommandError(str(exc)) from exc

        if options.get("json"):
            self.stdout.write(json.dumps(result))
            return

        mode = "DRY-RUN" if result["dry_run"] else "SEND"
        self.stdout.write(f"{mode} — template={result['template']}")
        for item in result["items"]:
            line = (
                f"  {item['client_id']:<10} {item['mobile'] or '-':<14} "
                f"{item['template']:<50} {item['record_date'] or '-':<12} {item['outcome']}"
            )
            if item.get("reason"):
                line += f"  ({item['reason']})"
            self.stdout.write(line)

        summary = (
            f"sent={result['sent']} would_send={result['would_send']} "
            f"skipped={result['skipped']} failed={result['failed']}"
        )
        style = self.style.WARNING if result["failed"] else self.style.SUCCESS
        self.stdout.write(style(summary))
