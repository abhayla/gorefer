"""M2 redirect + lazy-journey + click-event tests."""
import pytest
from django.core.management import call_command
from django.test import Client

from apps.events.models import Event, VisitorPII
from apps.referrals.models import Referral, ReferralIdentity, ReferralProgram
from apps.referrals.redirect_service import assemble_destination


@pytest.fixture
def seeded(db):
    call_command("seed_program")


@pytest.fixture
def client():
    return Client()


# --- destination assembly (server-side c= injection) -----------------------

def test_destination_assembled_with_server_side_partner_code(seeded):
    program = ReferralProgram.objects.get()
    url = assemble_destination(program, client_id="RJ4521")
    assert url == "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=RJ4521"


def test_partner_direct_destination_has_no_r_param(seeded):
    program = ReferralProgram.objects.get()
    url = assemble_destination(program, client_id=None)
    # D1 (owner, 2026-07-26): /open now goes to the plain signup page, not the lead form.
    assert url == "https://signup.zerodha.com/?c=ZMPHZC"
    assert "r=" not in url.split("?", 1)[1]


# --- /r/{client_id} landing view (M3: renders 200, lazy journey + landing_viewed) --

def test_referral_landing_renders_200_and_creates_lazy_journey(seeded, client):
    resp = client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0 (Android)", REMOTE_ADDR="203.0.113.7")
    assert resp.status_code == 200  # landing page, NOT an immediate 302 (ADR-002)
    assert ReferralIdentity.objects.count() == 1
    assert Referral.objects.filter(source="referral_link").count() == 1
    assert Event.objects.filter(event_type="landing_viewed").count() == 1
    assert "gr_vid" in resp.cookies  # visitor cookie set on first landing


def test_continue_action_302s_to_zerodha(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    resp = client.get("/r/RJ4521/continue", HTTP_USER_AGENT="Mozilla/5.0")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=RJ4521"


def test_client_id_normalized_uppercase(seeded, client):
    client.get("/r/rj4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    assert ReferralIdentity.objects.get().client_id == "RJ4521"


def test_repeat_landing_same_visitor_is_idempotent_on_identity(seeded, client):
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    assert ReferralIdentity.objects.count() == 1
    assert Referral.objects.filter(source="referral_link").count() == 1


def test_invalid_client_id_returns_400_and_creates_nothing(seeded, client):
    resp = client.get("/r/bad--id!!", HTTP_USER_AGENT="Mozilla/5.0")
    assert resp.status_code == 400
    assert ReferralIdentity.objects.count() == 0
    assert Referral.objects.count() == 0


# --- bot/preview UA: generic landing, NO journey --------------------------

def test_bot_preview_creates_no_journey(seeded, client):
    resp = client.get("/r/RJ4521", HTTP_USER_AGENT="WhatsApp/2.23.20")
    assert resp.status_code == 200  # generic landing renders, but...
    assert ReferralIdentity.objects.count() == 0  # ...no journey/identity for a bot
    assert Referral.objects.count() == 0
    assert Event.objects.count() == 0


@pytest.mark.parametrize(
    "ua",
    [
        # Observed live 2026-07-20: Meta's WhatsApp preview crawler slipped the
        # filter and was recorded as a human click (channel=WhatsApp).
        "facebookexternalua",
        "meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)",
        "meta-externalfetcher/1.1",
    ],
)
def test_meta_preview_crawler_uas_create_no_journey(seeded, client, ua):
    resp = client.get("/r/wa/RJ4521", HTTP_USER_AGENT=ua)
    assert resp.status_code == 200
    assert ReferralIdentity.objects.count() == 0
    assert Referral.objects.count() == 0
    assert Event.objects.count() == 0


# --- /open partner-direct --------------------------------------------------

def test_partner_direct_creates_none_referrer_journey(seeded, client):
    resp = client.get("/open", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://signup.zerodha.com/?c=ZMPHZC"
    referral = Referral.objects.get(source="partner_direct")
    assert referral.referral_identity is None  # never a synthetic referrer
    assert ReferralIdentity.objects.count() == 0


# --- PII placement: raw IP on erasable record, NOT in event ---------------

@pytest.mark.django_db(transaction=True)
def test_raw_ip_stored_on_erasable_record_not_in_event(client):
    call_command("seed_program")
    client.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    pii = VisitorPII.objects.get()  # raw IP recorded once, on the erasable record
    assert pii.raw_ip == "203.0.113.7"
    # No event (click or landing_viewed) carries the raw IP in its metadata.
    for event in Event.objects.all():
        assert "203.0.113.7" not in str(event.metadata)
    # The click event references the PII record by id only.
    click = Event.objects.get(event_type="click")
    assert click.person_ref_id == pii.pk


def test_first_click_at_is_stamped_on_first_click_only(seeded, client):
    """`first_click_at` was declared + shown in admin but never written (always None).

    It must be set by the first click and then stay put — a later click must not move it.
    """
    client.get("/r/FSTCLK", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    referral = Referral.objects.get(referral_identity__client_id="FSTCLK")
    assert referral.first_click_at is not None, "first click did not stamp first_click_at"
    stamped = referral.first_click_at

    client.get("/r/FSTCLK", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    referral.refresh_from_db()
    assert referral.first_click_at == stamped, "a later click moved first_click_at"


def test_first_click_at_stamped_for_partner_direct(
    seeded, client, django_capture_on_commit_callbacks
):
    """The partner-direct journey is a click path too, so it must stamp as well.

    `/open` writes its click on `transaction.on_commit` so the 302 is never blocked;
    inside a test transaction that callback only runs if we capture + execute it.
    """
    with django_capture_on_commit_callbacks(execute=True):
        client.get("/open", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.7")
    referral = Referral.objects.get(source="partner_direct")
    assert referral.first_click_at is not None


def test_bot_click_does_not_stamp_first_click_at(seeded, client):
    """A bot preview never creates a journey, so nothing should be stamped for it."""
    client.get("/r/BOTCLK1", HTTP_USER_AGENT="facebookexternalhit/1.1")
    assert not ReferralIdentity.objects.filter(client_id="BOTCLK1").exists()


# --- D1: /open destination is configurable (owner decision 2026-07-26) -------

def test_open_defaults_to_the_plain_signup_page_not_the_lead_form(seeded):
    """/open used to inherit the referral template's PATH (`/api/lead/`) because it was built
    by stripping `&r=`. The spec always said the plain signup page."""
    program = ReferralProgram.objects.first()
    url = assemble_destination(program, client_id=None)
    assert url == "https://signup.zerodha.com/?c=ZMPHZC", url
    assert "/api/lead/" not in url
    assert "r=" not in url


def test_open_destination_can_be_changed_by_config_without_a_deploy(seeded):
    """CLAUDE.md §6d — the owner must be able to point /open elsewhere themselves."""
    from apps.config.cascade import set_tenant
    from apps.referrals.redirect_service import PARTNER_DIRECT_URL_KEY
    from apps.tenants.resolve import get_bootstrap_tenant

    tenant = get_bootstrap_tenant()
    set_tenant(PARTNER_DIRECT_URL_KEY,
               "https://signup.zerodha.com/api/lead/?c={partner_code}",
               tenant_id=tenant.id)
    program = ReferralProgram.objects.first()
    url = assemble_destination(program, client_id=None, tenant_id=tenant.id)
    assert url == "https://signup.zerodha.com/api/lead/?c=ZMPHZC", url


def test_referral_links_are_unaffected_by_the_partner_direct_change(seeded):
    """Only /open changes; a referral link must still carry r= and the lead path."""
    program = ReferralProgram.objects.first()
    url = assemble_destination(program, client_id="RJ4521")
    assert "c=ZMPHZC" in url and "r=RJ4521" in url


# --- strict per-partner client_id on the identity-CREATING paths (2026-07-27) ---

def test_a_junk_client_id_creates_no_identity_on_the_redirect_path(client, seeded):
    """THE point of the strict rule: junk must not become a referrer.

    Live history: a Wati chatbot flow leaked the menu label "Talk to advisor" into the
    client_id slot and GoRefer created a real ReferralIdentity called `TALK`; the partner
    code `ZMPHZC` got in the same way. Both had to be soft-deleted by hand (D7).

    Asserting the 400 alone would be weak — the defect was the ROW, not the status code.
    """
    from apps.referrals.models import ReferralIdentity

    before = ReferralIdentity.objects.count()
    resp = client.get("/r/ABHAY", HTTP_USER_AGENT="Mozilla/5.0 (Android)", REMOTE_ADDR="203.0.113.9")
    assert resp.status_code == 400
    assert ReferralIdentity.objects.count() == before, "a junk id must create NO identity"
    assert not ReferralIdentity.objects.filter(client_id="ABHAY").exists()


def test_a_real_client_id_still_works_end_to_end(client, seeded):
    """The tightening must not break a legitimate referrer — the actual risk."""
    from apps.referrals.models import ReferralIdentity

    resp = client.get("/r/DA1707", HTTP_USER_AGENT="Mozilla/5.0 (Android)", REMOTE_ADDR="203.0.113.9")
    assert resp.status_code in (200, 302)
    assert ReferralIdentity.objects.filter(client_id="DA1707").exists()


def test_share_path_also_refuses_junk(client, seeded):
    """/share/ lazily creates an identity too, so it gets the same rule."""
    from apps.referrals.models import ReferralIdentity

    before = ReferralIdentity.objects.count()
    client.get("/share/wa/ABHAY", HTTP_USER_AGENT="Mozilla/5.0 (Android)", REMOTE_ADDR="203.0.113.9")
    assert ReferralIdentity.objects.count() == before
