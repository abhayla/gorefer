"""`set_landing_mode` — flip LANDING_MODE from a shell, with no browser.

    python manage.py set_landing_mode page|direct [--tenant pifs]

Writes the override at the GLOBAL/tenant tier through the SAME service the
Preferences screen uses (`preferences_service.set_landing_mode`), so the UI and this
command cannot drift: the ADR-032 coupling (`direct` requires a live /d/{slug}
disclosure host) and the unknown->page fallback are enforced in one place for both.
If the coupling forces a downgrade, this command says so and exits non-zero rather
than reporting a success it didn't achieve.

Prints the RESOLVED value + source afterwards — read back through the cascade, not
echoed from the input, so the output reflects what the app will actually do.

Unchanged by this command: the per-referrer landing override (user tier, dormant
behind ENABLE_CUSTOMER_LOGIN) and the ADR-032 disclosure coupling itself.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.config.cascade import resolve
from apps.config.preferences import LANDING_MODE
from apps.dashboard.preferences_service import set_landing_mode
from apps.referrals.landing_mode import (
    LANDING_MODE_DIRECT,
    LANDING_MODE_PAGE,
    resolve_landing_mode,
)
from apps.tenants.models import Tenant
from apps.tenants.resolve import BOOTSTRAP_TENANT_SLUG, get_current_tenant


class Command(BaseCommand):
    help = "Set the tenant's LANDING_MODE (page|direct) via the Preferences config path."

    def add_arguments(self, parser):
        parser.add_argument(
            "mode",
            choices=[LANDING_MODE_PAGE, LANDING_MODE_DIRECT],
            help="page = show the branded landing page; direct = 302 straight to Zerodha",
        )
        parser.add_argument(
            "--tenant",
            default=BOOTSTRAP_TENANT_SLUG,
            help=f"Tenant slug (default: {BOOTSTRAP_TENANT_SLUG})",
        )

    def handle(self, *args, **opts):
        requested = opts["mode"]
        slug = opts["tenant"]

        tenant = Tenant.objects.filter(slug=slug, is_active=True).first() or (
            get_current_tenant() if slug == BOOTSTRAP_TENANT_SLUG else None
        )
        if tenant is None:
            raise CommandError(f"no active tenant with slug {slug!r} — run `manage.py seed_program` first")

        before = resolve_landing_mode(tenant.id)
        written, notices = set_landing_mode(tenant, requested, user=None)

        # Read the value BACK through the cascade rather than trusting the write:
        # the resolved value is what the redirect path will actually use.
        after = resolve_landing_mode(tenant.id)
        source = _source(tenant.id)

        for notice in notices:
            self.stdout.write(self.style.WARNING(f"! {notice}"))

        self.stdout.write("")
        self.stdout.write(f"  tenant           : {tenant.slug}")
        self.stdout.write(f"  requested        : {requested}")
        self.stdout.write(f"  previous         : {before}")
        self.stdout.write(
            f"  resolved LANDING_MODE : {self.style.SUCCESS(after)}  (source={source})"
        )
        if before == after:
            self.stdout.write("  (no change — already in this mode)")
        self.stdout.write("")

        if after != requested:
            # The ADR-032 coupling refused the request. Exit non-zero so a scheduled
            # task/CI sees a failure instead of parsing a cheerful message.
            raise CommandError(
                f"LANDING_MODE is {after!r}, not the requested {requested!r} — see the notice above."
            )
        return None


def _source(tenant_id: int) -> str:
    """Which tier answered: a tenant override row, or the central default."""
    from apps.config.models import ConfigGlobal

    if ConfigGlobal.objects.for_tenant(tenant_id).filter(key=LANDING_MODE).exists():
        return "tenant override (GLOBAL tier)"
    if resolve(LANDING_MODE, tenant_id=tenant_id, default=None) is not None:
        return "central default"
    return "code default"
