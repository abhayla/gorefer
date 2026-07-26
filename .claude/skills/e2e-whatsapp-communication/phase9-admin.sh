#!/usr/bin/env bash
# Ephemeral staff credential for Phase 9 (admin dashboard testing).
#
#   bash phase9-admin.sh create    # prints USERNAME + PASSWORD on stdout, ONCE
#   bash phase9-admin.sh destroy   # removes the account
#   bash phase9-admin.sh status    # does it currently exist?
#
# WHY THIS EXISTS: Phase 9 previously used a standing prod account whose plaintext
# password lived in the project `.env`. CLAUDE.md §4 requires admin bootstrap from
# ADMIN_EMAIL + ADMIN_PASSWORD_HASH and "never a seeded plaintext credential" — a
# standing shared password on production conflicts with that. So: create at the start
# of Phase 9, use it, destroy at the end. The password is generated on the VPS, printed
# once, and never written to disk on either side.
#
# ALWAYS `destroy` when the phase ends, including on failure.
#
# PRIVILEGE — measured, not assumed (2026-07-26). is_staff=True, is_superuser=False:
#   /admin-panel/            200  (the GoRefer dashboard — what Phase 9 tests)
#   /django-admin/           200  <- Django gates its admin on is_staff, NOT is_superuser,
#                                    so this DOES open the admin shell. Do not assume otherwise.
#   /django-admin/<model>/   403  for referrals/customer, referrals/lead, events/visitorpii,
#                                    auth/user — no model permissions are granted, so no data
#                                    is reachable and nothing can be edited.
# Net: an empty admin shell, no data access. Acceptable for a short-lived test account, and a
# further reason to destroy it rather than leave one standing.

set -uo pipefail
VPS_KEY="${VPS_KEY:-$HOME/.ssh/firekaro_v6_vps}"
VPS="${VPS:-root@72.61.240.224}"
EMAIL="${E2E_ADMIN_EMAIL:-e2e-phase9@gorefer.in}"
ACTION="${1:-}"

run_remote() { ssh -i "$VPS_KEY" -o BatchMode=yes "$VPS" \
  "cd /var/www/gorefer && sudo -u www-data .venv/bin/python manage.py shell" ; }

case "$ACTION" in
create)
  run_remote << PYEOF
import secrets, string
from django.contrib.auth import get_user_model
U = get_user_model()
email = "$EMAIL"
alpha = string.ascii_letters + string.digits
pw = "Ph9-" + "".join(secrets.choice(alpha) for _ in range(18))
u = U.objects.filter(username=email).first() or U(username=email, email=email)
u.is_staff = True          # enough for every /admin-panel/ route
u.is_superuser = False     # deliberately NOT superuser — no /django-admin/
u.is_active = True
u.set_password(pw)
u.save()
print("E2E_PHASE9_USER=" + email)
print("E2E_PHASE9_PASS=" + pw)
print("NOTE: printed once, stored nowhere. Run 'phase9-admin.sh destroy' when done.")
PYEOF
  ;;
destroy)
  run_remote << PYEOF
from django.contrib.auth import get_user_model
U = get_user_model()
n, _ = U.objects.filter(username="$EMAIL").delete()
print("destroyed" if n else "nothing to destroy", "(", "$EMAIL", ")")
PYEOF
  ;;
status)
  run_remote << PYEOF
from django.contrib.auth import get_user_model
U = get_user_model()
u = U.objects.filter(username="$EMAIL").values("username","is_staff","is_superuser","is_active").first()
print(u or "absent (expected between runs)")
PYEOF
  ;;
*)
  echo "usage: bash phase9-admin.sh create|destroy|status" >&2
  exit 64
  ;;
esac
