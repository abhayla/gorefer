"""Template flags for the admin top bar (owner decision 2026-11-28).

`staff_is_owner` shows the "Access list" menu item. Lazy, and skipped for anyone who
is not signed-in staff, so public pages pay nothing for it.
"""
from __future__ import annotations

from django.utils.functional import SimpleLazyObject


def staff_roles(request):
    def _is_owner():
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        if not getattr(user, "is_staff", False):
            return False
        from apps.tenants.access import is_owner

        return is_owner(user)

    return {"staff_is_owner": SimpleLazyObject(_is_owner)}
