"""Staff roles, the access list and Google sign-in for staff (owner decision 2026-11-28).

Pins:
  * staff with NO access-list row keep the S2-06 rule exactly (binding wins);
  * an access-list row decides alone: a person may hold owner + admin + manager;
  * a manager grant never widens to another business, an inactive business grants nothing;
  * only owners open the access list; the last owner can't be removed or demoted;
  * every change is logged; a revoked person loses access on their next request;
  * Google sign-in admits only listed emails, and never disturbs the referrer sign-in.
"""
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.accounts import oauth
from apps.dashboard import staff_auth
from apps.tenants import access
from apps.tenants.models import StaffAccess, StaffAccessLog, StaffTenantBinding, Tenant
from apps.tenants.resolve import get_bootstrap_tenant

PW = "pw-for-tests-only"


@pytest.fixture
def pifs(db):
    call_command("seed_program")
    return get_bootstrap_tenant()


def _user(username, *, email="", superuser=False, staff=True, tenant=None):
    u = get_user_model().objects.create_user(
        username=username, email=email, password=PW, is_staff=staff, is_superuser=superuser,
    )
    if tenant is not None:
        StaffTenantBinding.objects.create(user=u, tenant=tenant)
    return u


def _client(user):
    c = Client()
    assert c.login(username=user.username, password=PW)
    return c


def _roles(user):
    return [(g.role, getattr(g.tenant, "slug", None)) for g in access.resolve_grants(user)]


# --- the resolver -------------------------------------------------------------------

def test_legacy_staff_map_onto_the_new_roles_unchanged(pifs):
    su = _user("su", superuser=True)
    apa = _user("apa", tenant=pifs)
    assert _roles(su) == [("owner", None), ("admin", None)]
    assert access.resolve_role(su).is_super_admin
    assert _roles(apa) == [("manager", pifs.slug)]
    assert access.resolve_role(apa).is_ap_admin and access.resolve_role(apa).tenant == pifs
    assert _roles(_user("norole")) == [] and access.resolve_role(_user("x2")).kind == access.DENIED


def test_access_row_grants_several_roles_at_once(pifs):
    me = _user("me", email="Owner@Example.com")
    StaffAccess.objects.create(email="owner@example.com", is_owner=True, is_admin=True, manager_tenant=pifs)
    assert _roles(me) == [("owner", None), ("admin", None), ("manager", pifs.slug)]
    assert access.resolve_role(me).is_super_admin
    assert access.is_owner(me)


def test_manager_only_row_is_one_business(pifs):
    other = Tenant.objects.create(name="Other AP", slug="other")
    mgr = _user("mgr", email="m@example.com")
    StaffAccess.objects.create(email="m@example.com", manager_tenant=pifs)
    assert _roles(mgr) == [("manager", pifs.slug)]
    role = access.resolve_role(mgr)
    assert role.is_ap_admin and role.tenant == pifs and role.tenant != other
    assert not access.is_owner(mgr)


def test_inactive_business_and_revoked_rows_grant_nothing(pifs):
    gone = Tenant.objects.create(name="Gone", slug="gone", is_active=False)
    u = _user("u", email="u@example.com")
    row = StaffAccess.objects.create(email="u@example.com", manager_tenant=gone)
    assert _roles(u) == [] and access.resolve_role(u).kind == access.DENIED
    row.manager_tenant, row.is_admin = None, True
    row.save()
    assert _roles(u) == [("admin", None)]
    from django.utils import timezone
    row.revoked_at = timezone.now()
    row.save()
    assert _roles(u) == []  # not a superuser, no binding: nothing left


def test_non_staff_never_gets_a_role_even_if_listed(pifs):
    referrer = _user("ref", email="r@example.com", staff=False)
    StaffAccess.objects.create(email="r@example.com", is_owner=True)
    assert _roles(referrer) == [] and access.resolve_role(referrer).kind == access.DENIED


# --- the access list screen -----------------------------------------------------------

def test_only_owners_open_the_access_list(pifs):
    owner = _user("own", email="own@example.com")
    StaffAccess.objects.create(email="own@example.com", is_owner=True)
    admin = _user("adm", email="adm@example.com")
    StaffAccess.objects.create(email="adm@example.com", is_admin=True)
    assert _client(owner).get("/admin-panel/access/").status_code == 200
    assert _client(admin).get("/admin-panel/access/").status_code == 302
    assert _client(_user("apa", tenant=pifs)).get("/admin-panel/access/").status_code == 302
    assert Client().get("/admin-panel/access/").status_code == 302


def test_grant_change_revoke_are_logged(pifs):
    owner = _user("own", email="own@example.com")
    StaffAccess.objects.create(email="own@example.com", is_owner=True)
    c = _client(owner)
    c.post("/admin-panel/access/", {"email": "New@Example.com", "manager_tenant": str(pifs.id)})
    row = StaffAccess.objects.get(email="new@example.com")
    assert (row.is_owner, row.is_admin, row.manager_tenant) == (False, False, pifs)
    c.post("/admin-panel/access/", {"email": "new@example.com", "admin": "on"})
    row.refresh_from_db()
    assert (row.is_admin, row.manager_tenant) == (True, None)
    c.post(f"/admin-panel/access/{row.id}/revoke")
    row.refresh_from_db()
    assert row.revoked_at is not None
    assert list(StaffAccessLog.objects.order_by("at").values_list("action", flat=True)) == [
        "grant", "change", "revoke"]
    assert all(e.actor_email == "own@example.com" for e in StaffAccessLog.objects.all())


def test_bad_input_is_refused_with_a_message(pifs):
    owner = _user("own", email="own@example.com")
    StaffAccess.objects.create(email="own@example.com", is_owner=True)
    c = _client(owner)
    c.post("/admin-panel/access/", {"email": "not-an-email", "admin": "on"})
    c.post("/admin-panel/access/", {"email": "ok@example.com"})  # no role ticked
    assert StaffAccess.objects.count() == 1


def test_the_last_owner_can_never_be_removed_or_demoted(pifs):
    owner = _user("own", email="own@example.com")
    row = StaffAccess.objects.create(email="own@example.com", is_owner=True)
    c = _client(owner)
    c.post(f"/admin-panel/access/{row.id}/revoke")
    c.post("/admin-panel/access/", {"email": "own@example.com", "admin": "on"})
    row.refresh_from_db()
    assert row.revoked_at is None and row.is_owner is True


def test_revoked_person_is_refused_on_the_next_request(pifs):
    owner = _user("own", email="own@example.com")
    StaffAccess.objects.create(email="own@example.com", is_owner=True)
    mgr = _user("mgr", email="m@example.com")
    row = StaffAccess.objects.create(email="m@example.com", manager_tenant=pifs)
    mc = _client(mgr)
    assert mc.get("/admin-panel/daily/").status_code == 200
    _client(owner).post(f"/admin-panel/access/{row.id}/revoke")
    assert mc.get("/admin-panel/daily/").status_code == 302


# --- Google sign-in for staff ----------------------------------------------------------

@pytest.fixture
def google(settings, monkeypatch):
    settings.GOOGLE_OAUTH_CLIENT_ID = "test-client-id"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "test-secret"

    def as_email(email):
        monkeypatch.setattr(oauth, "_post_form", lambda url, fields: {"access_token": "tok"})
        monkeypatch.setattr(oauth, "_get_json", lambda url, bearer: {
            "email": email, "email_verified": True, "name": "Staff", "sub": "g1"})
    return as_email


def _google_round_trip(client):
    start = client.get("/admin-panel/login/google")
    assert start.status_code == 302 and start["Location"].startswith(oauth.AUTHORIZATION_ENDPOINT)
    state = client.session[oauth.SESSION_STATE]
    return client.get("/login/google/callback", {"code": "abc", "state": state})


@pytest.mark.urls("tests.urls_m13")
def test_listed_email_signs_in_with_google_and_gets_its_roles(pifs, google):
    StaffAccess.objects.create(email="mgr@example.com", manager_tenant=pifs)
    google("mgr@example.com")
    c = Client()
    resp = _google_round_trip(c)
    assert resp.status_code == 302
    user = get_user_model().objects.get(email="mgr@example.com")
    assert user.is_staff and not user.is_superuser and not user.has_usable_password()
    assert _roles(user) == [("manager", pifs.slug)]
    assert c.get("/admin-panel/daily/").status_code == 200


@pytest.mark.urls("tests.urls_m13")
def test_unlisted_google_email_is_refused(pifs, google):
    google("stranger@example.com")
    resp = _google_round_trip(Client())
    assert resp.status_code == 403
    assert b"have access. Ask the owner to add it." in resp.content  # apostrophe is HTML-escaped
    assert not get_user_model().objects.filter(email="stranger@example.com").exists()


@pytest.mark.urls("tests.urls_m13")
def test_referrer_sign_in_is_never_routed_as_staff(pifs, google):
    StaffAccess.objects.create(email="mgr@example.com", is_admin=True)
    google("mgr@example.com")
    c = Client()
    c.get("/admin-panel/login/google")            # staff sign-in started, then abandoned
    c.get("/login/google/start")                   # a referrer sign-in in the same browser
    assert staff_auth.SESSION_PURPOSE not in c.session
    state = c.session[oauth.SESSION_STATE]
    resp = c.get("/login/google/callback", {"code": "abc", "state": state})
    assert resp["Location"] == "/login/bind"       # the referrer path, not a staff login
    assert not get_user_model().objects.filter(email="mgr@example.com").exists()


@pytest.mark.urls("tests.urls_m13")
def test_google_button_shows_only_when_configured(pifs, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = ""
    assert b"Continue with Google" not in Client().get("/admin-panel/login/").content
    assert Client().get("/admin-panel/login/google").status_code == 404
    settings.GOOGLE_OAUTH_CLIENT_ID, settings.GOOGLE_OAUTH_CLIENT_SECRET = "id", "secret"
    assert b"Continue with Google" in Client().get("/admin-panel/login/").content
