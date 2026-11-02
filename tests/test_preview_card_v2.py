"""Preview card v2 + the referrer's first name (owner 2026-11-03).

What this file pins:
  A. The renderer (pure): deterministic bytes, 1200x630, never runs into the legal band,
     the rupee glyph is real, the locked compliance strings are drawn whole.
  A. The switch: with `preview_card_v2_enabled` OFF every public output (crawler page for
     every /r/ shape, /open, the pop-up path, landing OG meta, hub OG meta) is byte-identical
     to the v1 snapshots in tests/snapshots/ (captured from origin/main before this change).
  A. The image routes: 404 when off; 200 image/png 1200x630 when on; cached; `?v=` follows
     the text; 429 under the rate limit.
  B. The name: one test per row of the eligibility matrix, the crawler page for a named
     referrer, the migration default, the Zoho sync never touching the new fields, and the
     My Referrals box (switches, self view only, save + PRG, validation, CSRF, ownership).
  Compliance: locked strings on the card, no "free demat", no superlatives, guardrail 3.

Names are fictional (Rahul, Priya) — never a real customer name in a committed file.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest
from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, RequestFactory
from django.utils import timezone
from PIL import Image, ImageFont

from apps.config import preferences as p
from apps.config.cascade import resolve, set_tenant
from apps.referrals import og
from apps.referrals import preview_card as pc
from apps.referrals.models import Customer, ReferralIdentity, ReferralProgram
from apps.tenants.resolve import get_bootstrap_tenant

BOT = {"HTTP_USER_AGENT": "WhatsApp/2.23.20 A"}
SNAP = Path(dj_settings.BASE_DIR) / "tests" / "snapshots"
CID = "RJ4521"
OTHER = "PQ7788"
SUPERLATIVES = ["best", "no. 1", "number one", "top", "leading", "lowest", "cheapest", "largest",
                "biggest", "greatest", "fastest", "most trusted"]
V1_PINS = {
    "OG_TITLE": "Open a free Zerodha demat & trading account",
    "OG_DESCRIPTION": ("You've been personally referred. PIFS helps you open your Zerodha account "
                       "smoothly with trusted guidance. Investments in securities market are subject "
                       "to market risks."),
    "OG_IMAGE": "img/referral-preview-card.png",
    "OG_SITE_NAME": "GoRefer · PIFS",
    "PUBLIC_BASE_URL": "https://gorefer.in",
}


def _defaults_text(**over) -> pc.CardText:
    base = dict(
        eyebrow=p.PREVIEW_CARD_EYEBROW_DEFAULT, headline=p.PREVIEW_CARD_HEADLINE_DEFAULT,
        price_big=p.PREVIEW_CARD_PRICE_BIG_DEFAULT, price_rest=p.PREVIEW_CARD_PRICE_REST_DEFAULT,
        docs=p.PREVIEW_CARD_DOCS_LINE_DEFAULT, cta=p.PREVIEW_CARD_CTA_DEFAULT,
        legal_disclosure=dj_settings.AP_DISCLOSURE_BLOCK, legal_risk=dj_settings.MARKET_RISK_WARNING,
    )
    base.update(over)
    return pc.CardText(**base)


# ============================================================ A. renderer (pure, no DB)

def test_renderer_is_deterministic():
    assert pc.render_card(_defaults_text()).png == pc.render_card(_defaults_text()).png


def test_renderer_draws_a_1200x630_png():
    img = Image.open(io.BytesIO(pc.render_card(_defaults_text()).png))
    assert (img.format, img.size) == ("PNG", (1200, 630))


@pytest.mark.parametrize("headline", [
    "Open your Zerodha account online today with a very long headline that keeps on going and going",
    "Supercalifragilisticexpialidociousandthensomemorewordsthatneverbreak at all ever",
    " ".join(["word"] * 60),
])
def test_long_headlines_never_overlap_the_legal_band(headline):
    # render_card raises ValueError if content reaches the band; this must not raise.
    result = pc.render_card(_defaults_text(headline=headline, price_rest="account opening " * 6,
                                           docs="Keep documents ready " * 8, eyebrow="X" * 90))
    assert result.png.startswith(b"\x89PNG")


@pytest.mark.parametrize("field", ["eyebrow", "price_big", "price_rest", "docs", "cta", "headline"])
def test_a_newline_in_operator_copy_does_not_crash_the_renderer(field):
    # Review finding 2026-11-03: Pillow cannot measure multi-line text -> a 500 on the route.
    result = pc.render_card(_defaults_text(**{field: "Ab\nCd\r\nEf"}))
    assert "Ab Cd Ef" in result.drawn


def test_typed_spaces_are_kept_so_the_default_card_is_unchanged():
    # The approved "Tap to start  →" has a deliberate double space; only line breaks go.
    assert pc.render_card(_defaults_text()).drawn[5] == p.PREVIEW_CARD_CTA_DEFAULT


def test_a_long_price_shrinks_instead_of_running_under_the_button():
    drawn = pc.render_card(_defaults_text(price_big="₹0 only today for everyone")).drawn
    assert drawn[2].endswith("…") or drawn[2] == "₹0 only today for everyone"


def test_rupee_sign_is_a_real_glyph_in_the_committed_font():
    font = ImageFont.truetype(str(pc.BOLD), 92)
    assert font.getmask("₹").getbbox() != font.getmask("").getbbox()


def test_drawn_text_carries_the_locked_strings_whole():
    drawn = pc.render_card(_defaults_text()).drawn
    assert dj_settings.AP_DISCLOSURE_BLOCK in drawn
    assert dj_settings.MARKET_RISK_WARNING in drawn


def test_card_fonts_are_committed_with_their_licence():
    for name in ("Inter-Regular.ttf", "Inter-Bold.ttf", "LICENSE.txt"):
        assert (pc.FONT_DIR / name).exists(), name
    assert "Open Font License" in (pc.FONT_DIR / "LICENSE.txt").read_text(encoding="utf-8")


def _v2_defaults() -> list[str]:
    return [d for _k, _l, d in p.PREVIEW_CARD_FIELDS]


def test_v2_defaults_make_no_free_account_claim():
    for text in _v2_defaults() + pc.render_card(_defaults_text()).drawn:
        low = text.lower()
        assert "free demat" not in low and "free trading" not in low and "open a free" not in low, text


def test_v2_defaults_carry_no_superlative():
    for text in _v2_defaults():
        words = re.findall(r"[a-z.0-9]+(?: [a-z.0-9]+)?", text.lower())
        joined = " " + " ".join(words) + " "
        for word in SUPERLATIVES:
            assert f" {word} " not in joined, (word, text)


def test_v2_defaults_carry_no_partner_code_or_partner_url():
    for text in _v2_defaults() + pc.render_card(_defaults_text()).drawn:
        assert dj_settings.PARTNER_CODE not in text and "signup.zerodha.com" not in text


# ============================================================ fixtures (DB)

@pytest.fixture
def seeded(db, settings):
    for name, value in V1_PINS.items():
        setattr(settings, name, value)
    call_command("seed_program")
    return get_bootstrap_tenant()


def _on(tenant, *, name: bool = False):
    set_tenant(p.PREVIEW_CARD_V2_ENABLED, True, tenant_id=tenant.id)
    if name:
        set_tenant(p.PREVIEW_CARD_NAME_ENABLED, True, tenant_id=tenant.id)


def _customer(tenant, client_id: str = CID, *, first_name: str = "Rahul", evidence: bool = True,
              **fields) -> Customer:
    """A Customer row. By default also a real-referrer signal, so a test about ANOTHER gate
    (opted out, deleted, bad name, ...) fails on that gate, not on missing evidence."""
    program = ReferralProgram.objects.get(tenant=tenant)
    customer = Customer.objects.create(tenant=tenant, program=program, partner=program.partner,
                                       client_id=client_id, first_name=first_name, **fields)
    if evidence:
        _evidence(tenant, client_id)
    return customer


def _evidence(tenant, client_id: str = CID, kind: str = "synced", *, active: bool = True):
    """One real-referrer signal (og.is_evidenced_referrer): synced / account / conversion."""
    from apps.campaigns.models import SyncedReferrer

    if kind == "synced":
        SyncedReferrer.objects.get_or_create(
            tenant=tenant, client_id=client_id,
            defaults={"mobile": "919800000000", "record_created_at": timezone.now(), "active": active})
    elif kind == "account":
        from apps.accounts import service as accounts_service
        from apps.accounts.models import ReferrerAccount

        account = accounts_service.get_or_create_account(
            tenant, client_id, bound_via=ReferrerAccount.BOUND_VIA_OTP, mobile="919800000001")
        if not active:
            account.status = ReferrerAccount.STATUS_DISABLED
            account.save(update_fields=["status"])
    elif kind == "conversion":
        _conversion(tenant, client_id)


def _conversion(tenant, client_id: str, *, reversed_: bool = False):
    """A Zoho-shaped conversion row crediting `client_id` (test fixture, not a GoRefer write)."""
    from apps.integrations.models import Conversion

    return Conversion.objects.create(
        tenant=tenant, program=ReferralProgram.objects.get(tenant=tenant),
        referrer_client_id=client_id, opener_zerodha_account_id=f"OP{client_id}",
        source_origin="zoho", is_reversed=reversed_)


def _identity(tenant, client_id: str = CID) -> ReferralIdentity:
    program = ReferralProgram.objects.get(tenant=tenant)
    return ReferralIdentity.objects.create(tenant=tenant, program=program, partner=program.partner,
                                           client_id=client_id)


def _generic_png(tenant) -> bytes:
    return og.card_png(og.v2_card_text(tenant.id, None))


def _named_png(tenant, name: str) -> bytes:
    return og.card_png(og.v2_card_text(tenant.id, name))


def _meta(html: str, prop: str) -> str:
    m = re.search(rf'<meta (?:property|name)="{re.escape(prop)}" content="([^"]*)"', html)
    return m.group(1) if m else ""


# ============================================================ A. v2 OFF = byte-identical

SNAP_PATHS = [("r_valid", "/r/RJ4521"), ("r_channel", "/r/wa/RJ4521"),
              ("r_prefixed", "/zerodha/r/RJ4521"), ("open", "/open"), ("r_popup", "/r/")]


@pytest.mark.parametrize("name,path", SNAP_PATHS)
def test_v2_off_crawler_page_is_byte_identical_to_v1(seeded, name, path):
    _customer(seeded)  # a named-eligible row must not change anything while v2 is off
    set_tenant(p.PREVIEW_CARD_NAME_ENABLED, True, tenant_id=seeded.id)  # name ON, v2 OFF
    resp = Client().get(path, **BOT)
    assert resp.status_code == 200
    assert resp.content == (SNAP / f"og_v1_{name}.html").read_bytes()


def test_v2_off_landing_and_hub_og_meta_are_identical_to_v1(seeded):
    from apps.accounts.hub import _og_context as hub_og
    from apps.referrals.views import _og_context as landing_og

    req = RequestFactory().get("/r/RJ4521")
    req.tenant = seeded
    got = {"landing": landing_og(req, CID), "hub": hub_og(seeded.id)}
    want = json.loads((SNAP / "og_v1_meta.json").read_text(encoding="utf-8"))
    assert json.loads(json.dumps(got)) == want


# ============================================================ A. image routes

@pytest.mark.parametrize("path", ["/og/card.png", f"/og/card/{CID}.png"])
def test_image_routes_404_while_v2_is_off(seeded, path):
    assert Client().get(path).status_code == 404


def test_generic_route_serves_a_1200x630_png(seeded):
    _on(seeded)
    resp = Client().get("/og/card.png")
    assert resp.status_code == 200 and resp["Content-Type"] == "image/png"
    assert resp["Cache-Control"] == "public, max-age=86400"
    assert Image.open(io.BytesIO(resp.content)).size == (1200, 630)


def test_second_call_is_a_cache_hit(seeded, monkeypatch):
    _on(seeded)
    calls = []
    real = pc.render_card
    monkeypatch.setattr(pc, "render_card", lambda t: calls.append(1) or real(t))
    first = Client().get("/og/card.png").content
    second = Client().get("/og/card.png").content
    assert first == second and len(calls) == 1


def test_version_param_follows_the_card_text(seeded):
    _on(seeded)
    before = og.v2_image_url(seeded.id)
    set_tenant(p.PREVIEW_CARD_HEADLINE, "Open your account online", tenant_id=seeded.id)
    after = og.v2_image_url(seeded.id)
    assert re.search(r"\?v=[0-9a-f]{10}$", before) and before != after


def test_image_route_is_rate_limited(seeded, settings):
    _on(seeded)
    settings.RATELIMIT_ENABLED = True
    settings.RATELIMIT_CLICK_MAX = 2
    client = Client()
    codes = [client.get("/og/card.png", REMOTE_ADDR="198.51.100.7").status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_route_serves_a_fallback_card_when_rendering_fails(seeded, monkeypatch):
    """Never a 500 from an image route: operator copy that cannot be drawn -> default card."""
    _on(seeded)
    real = pc.render_card

    def flaky(text):
        if text.headline == "boom":
            raise ValueError("card content overlaps the legal band")
        return real(text)

    monkeypatch.setattr(pc, "render_card", flaky)
    set_tenant(p.PREVIEW_CARD_HEADLINE, "boom", tenant_id=seeded.id)
    resp = Client().get("/og/card.png")
    assert resp.status_code == 200 and resp["Content-Type"] == "image/png"
    assert resp.content == real(_defaults_text(
        legal_disclosure=resolve("ap_disclosure_block"), legal_risk=resolve("market_risk_warning"))).png


def test_route_serves_the_v1_card_when_even_the_default_card_fails(seeded, monkeypatch):
    _on(seeded)

    def broken(_text):
        raise ValueError("legal band too tall")

    monkeypatch.setattr(pc, "render_card", broken)
    resp = Client().get(f"/og/card/{CID}.png")
    v1 = (Path(dj_settings.BASE_DIR) / "static" / "img" / "referral-preview-card.png").read_bytes()
    assert resp.status_code == 200 and resp.content == v1


def test_card_from_central_defaults_draws_the_cascade_locked_strings(seeded):
    drawn = pc.render_card(og.v2_card_text(seeded.id)).drawn
    assert resolve("ap_disclosure_block") in drawn
    assert resolve("market_risk_warning") in drawn


# ============================================================ A. crawler page, v2 ON

@pytest.mark.parametrize("path", ["/r/RJ4521", "/r/wa/RJ4521", "/zerodha/r/RJ4521", "/open", "/r/"])
def test_v2_on_crawler_page_points_at_the_generic_card(seeded, path):
    _on(seeded)
    html = Client().get(path, **BOT).content.decode()
    assert re.fullmatch(r"https://gorefer\.in/og/card\.png\?v=[0-9a-f]{10}", _meta(html, "og:image"))
    assert _meta(html, "og:title") == "Open your Zerodha account online — ₹0 account opening"
    assert _meta(html, "og:site_name") == "GoRefer"
    assert "Investments in securities market are subject to market risks" in _meta(html, "og:description")
    assert _meta(html, "twitter:card") == "summary_large_image"
    assert _meta(html, "og:image:width") == "1200" and _meta(html, "og:image:height") == "630"
    assert dj_settings.PARTNER_CODE not in html and "signup.zerodha.com" not in html


def test_v2_on_landing_and_hub_use_the_generic_v2_card(seeded):
    from apps.accounts.hub import _og_context as hub_og
    from apps.referrals.views import _og_context as landing_og

    _on(seeded, name=True)
    _customer(seeded)
    req = RequestFactory().get("/r/RJ4521")
    req.tenant = seeded
    assert "/og/card.png?v=" in landing_og(req, CID)["og_image"]
    assert "/og/card.png?v=" in hub_og(seeded.id)["image"]


def test_every_card_word_is_a_cascade_key(seeded):
    """E-6 spot test: each card/preview key, overridden at the tenant tier, changes output."""
    _on(seeded)
    for key, _label, _default in p.PREVIEW_CARD_FIELDS:
        set_tenant(key, f"Changed {key}", tenant_id=seeded.id)
    text = og.v2_card_text(seeded.id)
    assert text.headline == f"Changed {p.PREVIEW_CARD_HEADLINE}"
    assert text.cta == f"Changed {p.PREVIEW_CARD_CTA}"
    html = Client().get("/open", **BOT).content.decode()
    assert _meta(html, "og:title") == f"Changed {p.PREVIEW_CARD_OG_TITLE}"
    assert _meta(html, "og:site_name") == f"Changed {p.PREVIEW_CARD_OG_SITE_NAME}"


def test_stray_braces_in_operator_copy_do_not_break_the_named_card(seeded):
    _on(seeded, name=True)
    _customer(seeded)
    set_tenant(p.PREVIEW_CARD_NAMED_EYEBROW, "{first_name} {oops} {0} INVITED YOU", tenant_id=seeded.id)
    assert og.v2_card_text(seeded.id, "Rahul").eyebrow == "RAHUL {OOPS} {0} INVITED YOU"


# ============================================================ B. eligibility matrix

def _named_route(tenant, client_id=CID) -> bytes:
    resp = Client().get(f"/og/card/{client_id}.png")
    assert resp.status_code == 200 and resp["Content-Type"] == "image/png"
    return resp.content


def test_eligible_referrer_gets_the_named_card(seeded):
    _on(seeded, name=True)
    _customer(seeded)
    _evidence(seeded)
    assert _named_route(seeded) == _named_png(seeded, "Rahul") != _generic_png(seeded)


def test_name_switch_off_gives_the_generic_card(seeded):
    _on(seeded, name=False)
    _customer(seeded)
    assert _named_route(seeded) == _generic_png(seeded)


def test_v2_off_named_route_is_404_even_with_name_switch_on(seeded):
    set_tenant(p.PREVIEW_CARD_NAME_ENABLED, True, tenant_id=seeded.id)
    _customer(seeded)
    assert Client().get(f"/og/card/{CID}.png").status_code == 404


def test_referrer_opted_out_gets_the_generic_card(seeded):
    _on(seeded, name=True)
    _customer(seeded, show_name_on_preview=False)
    assert _named_route(seeded) == _generic_png(seeded)


def test_deleted_identity_gets_the_generic_card(seeded):
    _on(seeded, name=True)
    _customer(seeded)
    ident = _identity(seeded)
    ident.deleted_at = timezone.now()
    ident.save(update_fields=["deleted_at"])
    assert _named_route(seeded) == _generic_png(seeded)


def test_soft_deleted_customer_gets_the_generic_card(seeded):
    _on(seeded, name=True)
    cust = _customer(seeded)
    cust.deleted_at = timezone.now()
    cust.save(update_fields=["deleted_at"])
    assert _named_route(seeded) == _generic_png(seeded)


def test_placeholder_id_gets_the_generic_card(seeded):
    _on(seeded, name=True)
    _customer(seeded, client_id="KITEID")
    assert _named_route(seeded, "KITEID") == _generic_png(seeded)


def test_unknown_id_without_customer_gets_the_generic_card(seeded):
    _on(seeded, name=True)
    assert _named_route(seeded, OTHER) == _generic_png(seeded)


def test_a_strangers_click_plus_the_zoho_sync_never_publishes_a_name(
        seeded, monkeypatch, django_capture_on_commit_callbacks):
    """Tier-A review MAJOR #1 (2026-11-03), reproduced through the REAL path: a stranger
    clicks /r/<a client's id>, the daily Zoho name sync then writes that client's real first
    name into a Customer row — and the card must still be generic, because nothing shows
    this client ever referred anyone."""
    from apps.integrations.zoho import tasks
    from apps.integrations.zoho.read import ZohoContact

    class _Fake:
        def fetch_contact_by_client_id(self, *, client_id):
            return ZohoContact(client_id=client_id, matched=True, full_name="Priya Sharma")

    _on(seeded, name=True)
    with django_capture_on_commit_callbacks(execute=True):
        Client().get(f"/r/{OTHER}", HTTP_USER_AGENT="Mozilla/5.0 (Android)", REMOTE_ADDR="203.0.113.10")
    monkeypatch.setattr("apps.integrations.zoho.read.get_zoho_read_adapter", lambda: _Fake())
    tasks.sync_referrer_names()
    assert Customer.objects.get(client_id=OTHER).first_name == "Priya"  # the hole's precondition holds
    assert og.named_first_name(seeded, OTHER) is None
    assert _named_route(seeded, OTHER) == _generic_png(seeded)
    html = Client().get(f"/r/{OTHER}", **BOT).content.decode()
    assert "Priya" not in html and "/og/card.png?v=" in html


@pytest.mark.parametrize("kind", ["synced", "account", "conversion"])
def test_each_real_referrer_signal_turns_the_name_on(seeded, kind):
    _on(seeded, name=True)
    _customer(seeded, evidence=False)
    assert og.named_first_name(seeded, CID) is None
    _evidence(seeded, CID, kind)
    assert og.named_first_name(seeded, CID) == "Rahul"


@pytest.mark.parametrize("kind", ["synced", "account", "conversion"])
def test_a_switched_off_signal_is_not_evidence(seeded, kind):
    _on(seeded, name=True)
    _customer(seeded, evidence=False)
    if kind == "conversion":
        _conversion(seeded, CID, reversed_=True)  # Zoho took the credit back
    else:
        _evidence(seeded, CID, kind, active=False)
    assert og.named_first_name(seeded, CID) is None


def test_another_tenants_signal_is_not_evidence(seeded):
    from apps.tenants.models import Tenant

    _on(seeded, name=True)
    _customer(seeded, evidence=False)
    other = Tenant.objects.create(name="Other AP", slug="other-ap")
    from apps.campaigns.models import SyncedReferrer

    SyncedReferrer.objects.create(tenant=other, client_id=CID, mobile="919800000002",
                                  record_created_at=timezone.now())
    assert og.named_first_name(seeded, CID) is None


def test_empty_first_name_gets_the_generic_card(seeded):
    _on(seeded, name=True)
    _customer(seeded, first_name="")
    assert _named_route(seeded) == _generic_png(seeded)


@pytest.mark.parametrize("bad", ["R", "Rahul1", "Ráhul", "<script>", "A" * 16])
def test_invalid_names_get_the_generic_card(seeded, bad):
    _on(seeded, name=True)
    _customer(seeded, first_name=bad)
    assert _named_route(seeded) == _generic_png(seeded)


def test_preview_name_beats_the_zoho_first_name(seeded):
    _on(seeded, name=True)
    _customer(seeded, first_name="Rahul", preview_name="Priya")
    _evidence(seeded)
    assert og.named_first_name(seeded, CID) == "Priya"
    assert _named_route(seeded) == _named_png(seeded, "Priya")


def test_zoho_full_name_uses_the_first_word(seeded):
    _on(seeded, name=True)
    _customer(seeded, first_name="RAHUL KUMAR")
    _evidence(seeded)
    assert og.v2_card_text(seeded.id, og.named_first_name(seeded, CID)).eyebrow == "RAHUL INVITED YOU"
    title = _meta(Client().get(f"/r/{CID}", **BOT).content.decode(), "og:title")
    assert title == "Rahul invited you — open your Zerodha account online"


@pytest.mark.parametrize("path", [f"/r/{CID}", f"/r/wa/{CID}", f"/zerodha/r/{CID}"])
def test_crawler_page_for_an_eligible_referrer_is_named(seeded, path):
    _on(seeded, name=True)
    _customer(seeded)
    _evidence(seeded)
    html = Client().get(path, **BOT).content.decode()
    assert re.fullmatch(rf"https://gorefer\.in/og/card/{CID}\.png\?v=[0-9a-f]{{10}}", _meta(html, "og:image"))
    assert _meta(html, "og:title").startswith("Rahul invited you")


@pytest.mark.parametrize("path", ["/open", "/r/", "/r/wa/KITEID"])
def test_no_referrer_paths_never_carry_a_name(seeded, path):
    _on(seeded, name=True)
    _customer(seeded)
    html = Client().get(path, **BOT).content.decode()
    assert "Rahul" not in html and "/og/card.png?v=" in html


def test_new_customer_rows_default_to_showing_the_name(seeded):
    assert _customer(seeded).show_name_on_preview is True


def test_migration_0012_defaults_existing_rows_to_true(transactional_db):
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    call_command("seed_program")
    tenant = get_bootstrap_tenant()
    program = ReferralProgram.objects.get(tenant=tenant)
    before = [("referrals", "0011_program_url_prefix")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    try:
        old_apps = executor.loader.project_state(before).apps
        OldCustomer = old_apps.get_model("referrals", "Customer")
        OldCustomer.objects.create(tenant_id=tenant.id, program_id=program.id,
                                   partner_id=program.partner_id, client_id="MG1001",
                                   first_name="Rahul")
    finally:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
    row = Customer.objects.get(client_id="MG1001")
    assert row.show_name_on_preview is True and row.preview_name == ""


def test_zoho_name_sync_never_touches_the_preview_fields(seeded, monkeypatch):
    from apps.integrations.zoho import tasks
    from apps.integrations.zoho.read import ZohoContact

    class _Fake:
        def fetch_contact_by_client_id(self, *, client_id):
            return ZohoContact(client_id=client_id, matched=True, full_name="Priya Sharma")

    _identity(seeded)
    stamp = timezone.now()
    _customer(seeded, first_name="Old", show_name_on_preview=False, preview_name="Rahul",
              preview_name_updated_at=stamp)
    monkeypatch.setattr("apps.integrations.zoho.read.get_zoho_read_adapter", lambda: _Fake())
    tasks.sync_referrer_names()
    row = Customer.objects.get(client_id=CID)
    assert row.first_name == "Priya"  # the sync really ran
    kept = (row.show_name_on_preview, row.preview_name, row.preview_name_updated_at)
    assert kept == (False, "Rahul", stamp)


# ============================================================ B. My Referrals box

pytestmark_login = pytest.mark.urls("tests.urls_hub_login")


def _login(tenant, client_id=CID) -> Client:
    from apps.accounts import service as accounts_service
    from apps.accounts.models import ReferrerAccount

    account = accounts_service.get_or_create_account(
        tenant, client_id, bound_via=ReferrerAccount.BOUND_VIA_OTP, mobile="919876543210")
    client = Client()
    client.force_login(account.user)
    return client


@pytestmark_login
def test_box_shows_only_when_both_switches_are_on(seeded):
    _identity(seeded)
    _customer(seeded)
    client = _login(seeded)
    assert b'data-test="preview-box"' not in client.get("/my/referrals").content
    _on(seeded, name=False)
    assert b'data-test="preview-box"' not in client.get("/my/referrals").content
    _on(seeded, name=True)
    body = client.get("/my/referrals").content.decode()
    assert 'data-test="preview-box"' in body
    assert f"/og/card/{CID}.png?v=" in body and "&amp;own=1" in body
    assert 'value="Rahul"' in body


@pytestmark_login
def test_box_never_shows_on_the_admin_profile(seeded, django_capture_on_commit_callbacks):
    _on(seeded, name=True)
    _customer(seeded)
    # The admin profile 404s for a stranger: one human click gives the id a referral.
    with django_capture_on_commit_callbacks(execute=True):
        Client().get(f"/r/{CID}", HTTP_USER_AGENT="Mozilla/5.0 (Android)", REMOTE_ADDR="203.0.113.9")
    get_user_model().objects.create_user(username="staff@pifs.in", email="staff@pifs.in",
                                         password="pw12345!", is_staff=True)
    admin = Client()
    admin.login(username="staff@pifs.in", password="pw12345!")
    resp = admin.get(f"/admin-panel/referrer/{CID}/")
    assert resp.status_code == 200
    assert b'data-test="preview-box"' not in resp.content


@pytestmark_login
def test_save_persists_redirects_and_shows_the_message(seeded):
    _on(seeded, name=True)
    _identity(seeded)
    _customer(seeded)
    client = _login(seeded)
    resp = client.post("/my/referrals/preview-name", {"preview_name": "Priya"})
    assert resp.status_code == 302 and resp["Location"] == "/my/referrals"
    row = Customer.objects.get(client_id=CID)
    assert (row.preview_name, row.show_name_on_preview) == ("Priya", False)  # box unticked
    assert row.preview_name_updated_at is not None
    body = client.get("/my/referrals").content.decode()
    assert 'value="Priya"' in body and "Saved. New shares will show this card." in body


@pytestmark_login
def test_invalid_name_rerenders_with_the_error_and_saves_nothing(seeded):
    _on(seeded, name=True)
    _identity(seeded)
    _customer(seeded)
    client = _login(seeded)
    resp = client.post("/my/referrals/preview-name",
                       {"preview_name": "<b>Rahul</b>", "show_name_on_preview": "on"})
    assert resp.status_code == 400
    assert "Use your first name in English letters only" in resp.content.decode()
    row = Customer.objects.get(client_id=CID)
    assert (row.preview_name, row.preview_name_updated_at) == ("", None)


@pytestmark_login
def test_post_requires_csrf(seeded):
    from apps.accounts import service as accounts_service
    from apps.accounts.models import ReferrerAccount

    _on(seeded, name=True)
    _identity(seeded)
    _customer(seeded)
    account = accounts_service.get_or_create_account(
        seeded, CID, bound_via=ReferrerAccount.BOUND_VIA_OTP, mobile="919876543210")
    client = Client(enforce_csrf_checks=True)
    client.force_login(account.user)
    resp = client.post("/my/referrals/preview-name", {"preview_name": "Priya"})
    assert resp.status_code == 403
    assert Customer.objects.get(client_id=CID).preview_name == ""


@pytestmark_login
def test_posted_client_id_is_ignored(seeded):
    _on(seeded, name=True)
    _identity(seeded)
    _customer(seeded)
    _customer(seeded, OTHER, first_name="Priya")
    client = _login(seeded)  # logged in as CID
    client.post("/my/referrals/preview-name",
                {"preview_name": "Hacked", "client_id": OTHER, "show_name_on_preview": "on"})
    assert Customer.objects.get(client_id=OTHER).preview_name == ""
    assert Customer.objects.get(client_id=CID).preview_name == "Hacked"


@pytestmark_login
def test_anonymous_post_goes_to_login(seeded):
    _on(seeded, name=True)
    resp = Client().post("/my/referrals/preview-name", {"preview_name": "Priya"})
    assert resp.status_code == 302 and "/login" in resp["Location"]


def test_django_admin_change_form_shows_the_preview_fields(seeded):
    cust = _customer(seeded)
    get_user_model().objects.create_superuser(username="root@pifs.in", email="root@pifs.in",
                                              password="pw12345!")
    client = Client()
    client.login(username="root@pifs.in", password="pw12345!")
    body = client.get(f"/django-admin/referrals/customer/{cust.pk}/change/").content.decode()
    for field in ("show_name_on_preview", "preview_name", "preview_name_updated_at"):
        assert f'name="{field}' in body, field
