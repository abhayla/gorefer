"""Management command: send the referral INVITE WhatsApp template (T-073).

    python manage.py send_invite_links --client-ids RJ4521,DA1707
    python manage.py send_invite_links --client-ids RJ4521,DA1707 --send

DRY-RUN IS THE DEFAULT. It previews every gate — per-run cap, min-gap dedupe,
opt-out, mobile resolution, and the fail-closed computed-variable check — without
sending or writing anything, and reports that a DISTINCT token was minted for each
recipient WITHOUT ever printing the token (a preview a human reads is still a place
a credential can leak).

`--send` additionally requires both `ENABLE_WATI_SEND` and `ENABLE_SHARE_HUB` (the
flag that mounts the `/hub/{token}` page this invite links to — NOT
`ENABLE_RECORDS_LINK`, which gates the unrelated `/records/` page), AND that the
vendor itself reports the resolved template as APPROVED. The invite template is a
DRAFT at Meta today, so `--send` refuses — this command ships as capability, not as
a blast.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.records_link_send import SendRefused, send_invite_links


class Command(BaseCommand):
    help = (
        "Send the referral invite WhatsApp template (name + client_id + a per-recipient "
        "minted token) to an explicit list of client ids. Dry-run by default."
    )

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
            result = send_invite_links(client_ids, dry_run=not options["send"])
        except SendRefused as exc:
            raise CommandError(str(exc)) from exc

        if options.get("json"):
            self.stdout.write(json.dumps(result))
            return

        mode = "DRY-RUN" if result["dry_run"] else "SEND"
        self.stdout.write(f"{mode} — template={result['template']}")
        for item in result["items"]:
            token_note = "token=minted" if item.get("token_minted") else "token=none"
            line = (
                f"  {item['client_id']:<10} {item['mobile'] or '-':<14} "
                f"{item['template']:<55} {token_note:<13} {item['outcome']}"
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
