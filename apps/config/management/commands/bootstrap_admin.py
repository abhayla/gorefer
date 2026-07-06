"""Bootstrap the single admin user from env vars (implementation/10 §5).

Idempotent: if an admin with ADMIN_EMAIL already exists, this is a no-op.
NEVER seeds a plaintext default password. Accepts ONLY a pre-hashed password via
ADMIN_PASSWORD_HASH (a Django password hash, e.g. produced by
`make_password` / `manage.py changepassword`) — the hash is stored as-is.

Admin-only in Sprint 1; customer login stays behind ENABLE_CUSTOMER_LOGIN=false.
"""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the bootstrap super-admin from ADMIN_EMAIL + ADMIN_PASSWORD_HASH (idempotent)."

    def handle(self, *args, **options):
        email = (settings.ADMIN_EMAIL or "").strip()
        password_hash = (settings.ADMIN_PASSWORD_HASH or "").strip()

        if not email:
            raise CommandError("ADMIN_EMAIL is not set — cannot bootstrap admin.")
        if not password_hash:
            raise CommandError(
                "ADMIN_PASSWORD_HASH is not set — refusing to seed a plaintext/default password. "
                "Generate one with: python -c \"from django.contrib.auth.hashers import make_password; "
                "print(make_password('...'))\""
            )

        User = get_user_model()
        existing = User.objects.filter(username=email).first() or User.objects.filter(email=email).first()
        if existing:
            self.stdout.write(self.style.WARNING(f"Admin '{email}' already exists — no-op."))
            return

        user = User(username=email, email=email, is_staff=True, is_superuser=True, is_active=True)
        user.password = password_hash  # store the provided hash verbatim (already hashed)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Bootstrap admin '{email}' created."))
