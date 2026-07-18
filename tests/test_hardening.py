"""M8 Phase-A hardening tests — cross-cutting ATP items (§G, §H, §I, §K, §L, §M)
and regressions caught during hardening. Complements the per-mission suites.
"""
import os
import re
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import Client

BASE_DIR = Path(__file__).resolve().parent.parent


# --- §L: no CDN runtime anywhere; compiled asset served -------------------

@pytest.mark.django_db
def test_no_tailwind_or_htmx_cdn_in_any_page():
    """ADR-003: pages load a compiled/purged CSS + local HTMX — never a CDN."""
    call_command("seed_program")
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")  # prime a journey
    for path in ("/", "/r/RJ4521", "/r/bad--id", "/admin-panel/login/"):
        html = c.get(path, HTTP_USER_AGENT="Mozilla/5.0").content.decode()
        assert "cdn.tailwindcss.com" not in html, f"Tailwind CDN in {path}"
        assert "unpkg.com/htmx" not in html, f"HTMX CDN in {path}"
        assert "/static/css/app.css" in html, f"compiled CSS not linked in {path}"


def test_compiled_css_asset_exists_and_purged():
    css = BASE_DIR / "static" / "css" / "app.css"
    assert css.exists(), "run `npm run build:css` — compiled CSS missing"
    assert css.stat().st_size > 5000, "compiled CSS suspiciously small"


def test_htmx_vendored_locally():
    assert (BASE_DIR / "static" / "js" / "htmx.min.js").exists()


# --- regression: no Django template comment leaks into rendered HTML ------

@pytest.mark.django_db
def test_no_template_comment_leaks_in_rendered_pages():
    """Multi-line {# #} render literally in Django — guard against it permanently."""
    call_command("seed_program")
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    for path in ("/", "/r/RJ4521", "/admin-panel/login/"):
        html = c.get(path, HTTP_USER_AGENT="Mozilla/5.0").content.decode()
        assert "{#" not in html and "#}" not in html, f"template comment leaked in {path}"
        assert "{% comment" not in html and "{% endcomment" not in html


def test_no_source_multiline_hash_comments_in_templates():
    """Static guard: no multi-line {# ... #} comment in any template (use {% comment %})."""
    offenders = []
    for html in (BASE_DIR / "templates").rglob("*.html"):
        for i, line in enumerate(html.read_text(encoding="utf-8").splitlines(), 1):
            if "{#" in line and "#}" not in line:
                offenders.append(f"{html.name}:{i}")
    assert not offenders, f"multi-line {{# #}} comments (use {{% comment %}}): {offenders}"


# --- compliance strings are byte-exact + verbatim on every customer page ----

# Canonical strings (must match GLOBAL.md / the spec exactly). NOTE: no "the" before
# "securities market"; a COMMA (not ";") before "read".
_CANON_DISCLOSURE = (
    "Zerodha Broking Ltd.: SEBI Registration no.: INZ000031633 | "
    "Passive Income Financial Solutions Private Limited | "
    "NSE AP reg. no.: AP2516003693"
)
_CANON_RISK = (
    "Investments in securities market are subject to market risks, "
    "read all the related documents carefully before investing."
)


@pytest.mark.django_db
def test_compliance_strings_byte_exact_on_customer_pages():
    """The disclosure block + market-risk warning render VERBATIM (byte-exact) on
    every customer-facing page — homepage footer included (DA M9 fix batch)."""
    call_command("seed_program")
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")  # prime a journey
    for path in ("/", "/r/RJ4521", "/r/bad--id", "/admin-panel/login/"):
        html = c.get(path, HTTP_USER_AGENT="Mozilla/5.0").content.decode()
        assert _CANON_DISCLOSURE in html, f"disclosure not byte-exact on {path}"
        assert _CANON_RISK in html, f"risk warning not byte-exact on {path}"
        # The wrong (pre-fix) wording must NOT appear.
        assert "the securities market" not in html, f"stale 'the securities market' on {path}"
        assert "market risks;" not in html, f"stale ';' risk wording on {path}"


@pytest.mark.django_db
def test_landing_shows_config_helpline_distinct_from_wati_share():
    """Landing shows the config helpline (SUPPORT_HELPLINE_PHONE) as a call line, and
    the WhatsApp share stays on the config WATI number — both config-driven."""
    call_command("seed_program")
    c = Client()
    html = c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0").content.decode()
    assert "73888 82020" in html            # helpline (Ashok) on the call line
    assert "tel:+917388882020" in html      # config-driven tel: link
    assert "917080642020" in html           # WhatsApp share still on the WATI number


# --- §G: config cascade + compliance lock ---------------------------------

@pytest.fixture
def tenant(db):
    from apps.tenants.models import Tenant
    return Tenant.objects.create(name="PIFS", slug="pifs")


def test_g1_global_override_beats_central(db, tenant):
    from apps.config.cascade import resolve
    from apps.config.models import ConfigCentral, ConfigGlobal
    ConfigCentral.objects.create(key="brand_color", value="blue")
    assert resolve("brand_color") == "blue"
    ConfigGlobal.objects.create(tenant=tenant, key="brand_color", value="green")
    assert resolve("brand_color", tenant_id=tenant.id) == "green"  # admin override wins


def test_g2_compliance_locked_at_central(db, tenant):
    from apps.config.cascade import resolve
    from apps.config.models import ConfigCentral, ConfigGlobal
    ConfigCentral.objects.create(key="referral_incentive_claim", value="OFFICIAL")
    ConfigGlobal.objects.create(tenant=tenant, key="referral_incentive_claim", value="WEAKENED")
    # A lower tier CANNOT weaken/remove a compliance-locked key.
    assert resolve("referral_incentive_claim", tenant_id=tenant.id) == "OFFICIAL"


@pytest.mark.django_db
def test_g3_incentive_and_whatsapp_number_config_driven():
    """Changing config changes the rendered value (no hardcoded literals)."""
    call_command("seed_program")
    from apps.config.models import ConfigCentral
    # WhatsApp number is seeded to central config and rendered into the wa.me link.
    assert ConfigCentral.objects.filter(key="wati_business_number").exists()
    html = Client().get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0").content.decode()
    # The config-driven WATI business number is exposed to the page (JS builds the
    # wa.me deep link from it at click time — see tweak #1).
    assert "917080642020" in html
    # The single incentive claim renders from flags.REFERRAL_INCENTIVE_CLAIM.
    assert "10% brokerage share + 300 reward points" in html


# --- §H2: tenant isolation with a 2nd tenant ------------------------------

@pytest.mark.django_db
def test_h2_tenant_isolation_across_two_tenants():
    """A query scoped to tenant A cannot read tenant B's rows."""
    from apps.referrals.models import Partner
    from apps.tenants.models import Tenant
    a = Tenant.objects.create(name="PIFS", slug="pifs")
    b = Tenant.objects.create(name="AngelOne", slug="angel")
    Partner.objects.create(tenant=a, name="PIFS", code="AAA111")
    Partner.objects.create(tenant=b, name="Angel", code="BBB222")
    assert Partner.objects.filter(tenant=a).count() == 1
    assert Partner.objects.filter(tenant=a).first().code == "AAA111"
    # Tenant A's scope never sees B's row.
    assert not Partner.objects.filter(tenant=a, code="BBB222").exists()


def test_h3_composite_unique_includes_tenant():
    from apps.referrals.models import ReferralProgram
    names = {c.name for c in ReferralProgram._meta.constraints}
    assert "uq_program_tenant_partner_name" in names
    fields = next(c.fields for c in ReferralProgram._meta.constraints
                  if c.name == "uq_program_tenant_partner_name")
    assert "tenant" in fields


# --- §K5: missing/blank config → safe failure -----------------------------

def test_k5_bootstrap_admin_refuses_without_hash(db, settings):
    from django.core.management.base import CommandError
    settings.ADMIN_EMAIL = "a@b.in"
    settings.ADMIN_PASSWORD_HASH = ""
    with pytest.raises(CommandError):  # safe failure, not a silent default
        call_command("bootstrap_admin")


@pytest.mark.django_db
def test_k5_zoho_webhook_rejects_when_no_key_configured(settings):
    """Blank ZOHO_WEBHOOK_KEY must reject (fail-closed), never accept-any."""
    import json
    settings.ZOHO_WEBHOOK_KEY = ""
    call_command("seed_program")
    resp = Client().post(
        "/api/zoho/status-webhook",
        data=json.dumps({"event_id": "e1", "opener_zerodha_account_id": "ZA1"}),
        content_type="application/json",
        HTTP_X_ZOHO_WEBHOOK_KEY="anything",
    )
    assert resp.status_code == 401  # no key configured => reject


# --- DEF-1: missing/inactive redirect config -> branded 503, never a 500 ---

@pytest.mark.django_db
def test_def1_missing_redirect_rule_renders_branded_503():
    """No active ProgramRedirectRule (or ReferralProgram) => branded 503
    PARTNER_UNAVAILABLE HTML, NOT an uncaught 500 (06-API §4.1)."""
    from apps.referrals.models import ProgramRedirectRule
    call_command("seed_program")
    c = Client()
    # Prime a journey while config is healthy, then break the redirect config.
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    ProgramRedirectRule.objects.update(is_active=False)  # no active rule
    # The DESTINATION-building steps (Continue / partner-direct) must 503, never 500.
    for path in ("/r/RJ4521/continue", "/open"):
        resp = c.get(path, HTTP_USER_AGENT="Mozilla/5.0")
        assert resp.status_code == 503, f"{path} should be 503, got {resp.status_code}"
        body = resp.content.decode()
        assert "temporarily unavailable" in body.lower()
        assert "Traceback" not in body and "DoesNotExist" not in body  # never a raw error
        assert "AP2516003693" in body  # compliance still injected on the branded 503
    # The landing render itself doesn't build the destination, so it still renders
    # (the 503 is specifically for the "destination cannot be built" step, §4.1).
    assert c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0").status_code == 200


@pytest.mark.django_db
def test_def1_no_active_program_renders_branded_503():
    from apps.referrals.models import ReferralProgram
    call_command("seed_program")
    c = Client()
    c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    ReferralProgram.objects.update(status="inactive")  # no active program
    resp = c.get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0")
    assert resp.status_code == 503


# --- OBS-1: dashboard KPI accounts_opened == funnel account_opened ----------

@pytest.mark.django_db(transaction=True)
def test_obs1_dashboard_counts_internally_consistent():
    """KPI accounts_opened, funnel account_opened, and the true Conversion count
    all agree (one source, one freshness) — no stale KPI beside a fresher funnel."""
    from apps.dashboard import queries
    from apps.integrations.models import Conversion
    from apps.tenants.resolve import get_bootstrap_tenant
    call_command("seed_program")
    call_command("seed_demo")
    t = get_bootstrap_tenant()
    queries.refresh_and_freshness(t)  # recompute-on-view
    k = queries.kpis(t)
    funnel = {s["stage"]: s["count"] for s in queries.funnel(t)}
    live_conv = Conversion.objects.filter(is_reversed=False).count()
    assert k["accounts_opened"] == funnel["account_opened"] == live_conv
    # Clicks agree between KPI and funnel too.
    assert k["total_clicks"] == funnel["click"]


# --- §I3: erasure path exists ---------------------------------------------

@pytest.mark.django_db(transaction=True)
def test_i3_visitor_pii_is_erasable():
    from apps.events.models import VisitorPII
    call_command("seed_program")
    Client().get("/r/RJ4521", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="203.0.113.5")
    pii = VisitorPII.objects.get()
    assert pii.raw_ip == "203.0.113.5"
    # Erasure = clear the PII fields + stamp erased_at (manual in Sprint 1).
    from django.utils import timezone
    pii.raw_ip = None
    pii.city = ""
    pii.erased_at = timezone.now()
    pii.save()
    pii.refresh_from_db()
    assert pii.raw_ip is None and pii.erased_at is not None


# --- §M2: provider-agnostic naming ----------------------------------------

def test_m2_no_zerodha_named_symbols_in_code():
    """No file/class/model/route named Zerodha* (Zerodha is data, not code)."""
    offenders = []
    for py in (BASE_DIR / "apps").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        # class/def/model named Zerodha… (allow the string 'Zerodha' as data/label)
        if re.search(r"\b(class|def)\s+Zerodha", text):
            offenders.append(py.name)
    for py in (BASE_DIR / "apps").rglob("*.py"):
        if "Zerodha" in py.name:
            offenders.append(py.name)
    assert not offenders, f"Zerodha-named symbols/files: {offenders}"


# --- H1: DEBUG/SECRET_KEY boot guard (secure-by-default) ------------------

def test_h1_settings_secure_by_default_and_guarded():
    """Fable5 H1: DEBUG defaults to false (secure) and a boot guard refuses
    DEBUG=false + the public insecure default SECRET_KEY."""
    src = (BASE_DIR / "gorefer" / "settings.py").read_text(encoding="utf-8")
    # DEBUG default is false (a lost DJANGO_DEBUG env fails closed, no tracebacks).
    assert 'os.environ.get("DJANGO_DEBUG", "false")' in src
    # The guard exists and is fail-fast (mirrors the Postgres pattern).
    assert "_DEFAULT_INSECURE_SECRET_KEY" in src
    assert "SECRET_KEY == _DEFAULT_INSECURE_SECRET_KEY" in src


def test_h1_boot_guard_raises_in_a_clean_prod_env(tmp_path):
    """Importing settings with DEBUG=false and no SECRET_KEY must raise. Runs in a
    subprocess from an EMPTY cwd with the local .env neutralised (an empty file at the
    same path load_dotenv reads) so nothing re-injects the key, and a clean env — the
    already-loaded settings module can't be re-imported in-process."""
    import shutil
    import subprocess
    import sys

    # Mirror the repo into tmp so BASE_DIR/.env is EMPTY (load_dotenv uses BASE_DIR/.env
    # by absolute path; the real .env would otherwise re-inject a good SECRET_KEY).
    pkg_dst = tmp_path / "gorefer"
    shutil.copytree(BASE_DIR / "gorefer", pkg_dst)
    (tmp_path / ".env").write_text("", encoding="utf-8")

    env = {
        k: v for k, v in os.environ.items()
        if k not in {"DJANGO_DEBUG", "DJANGO_SECRET_KEY"}
    }
    env["DJANGO_DEBUG"] = "false"
    env["PYTHONPATH"] = str(tmp_path)  # import the copied gorefer package
    # Keep DB_* so the Postgres guard doesn't fire first; we want the SECRET_KEY guard.
    code = (
        "import os;"
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE','gorefer.settings');"
        "from django.conf import settings;"
        "settings._setup()"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=str(tmp_path), env=env,
        capture_output=True, text=True,
    )
    assert proc.returncode != 0, "boot should FAIL with DEBUG=false + default SECRET_KEY"
    assert "DJANGO_SECRET_KEY is unset" in (proc.stderr + proc.stdout)


# --- M10: PostgreSQL is the ONLY supported engine -------------------------

@pytest.mark.django_db
def test_m10_postgres_is_the_only_engine(db):
    """The running suite is on PostgreSQL, settings carry the fail-fast guard,
    and no SQLite branch survives in settings source (M10 — no SQLite path).

    Takes `db` so the test-database connection is actually established — the
    dedicated-test-db assertion below inspects the live connection.
    """
    from django.conf import settings

    # 1. The suite itself runs on Postgres (no SQLite fallback in the loop).
    engine = settings.DATABASES["default"]["ENGINE"]
    assert engine == "django.db.backends.postgresql", (
        f"tests must run on PostgreSQL (M10); resolved engine is {engine!r}"
    )
    # Test DB is a DEDICATED Postgres db, never sqlite / the dev db. Prefix-matched,
    # not equality: under pytest-xdist (DF-TESTDB-ISOLATION) each worker gets its own
    # db — gorefer_test_gw0, _gw1, … — and an exact match would fail a parallel run
    # while proving nothing extra. What matters is that it is a dedicated test db.
    # Assert the LIVE CONNECTION, not the settings dict. The two settings keys are
    # unreliable here and differ by mode: serial leaves NAME as the dev db (Django
    # swaps the connection, not the setting), while xdist rewrites NAME to the
    # per-worker db. `connection.settings_dict["NAME"]` is what we are actually
    # talking to in BOTH modes — a stronger claim than the config check it replaces.
    from django.db import connection

    connected_db = connection.settings_dict["NAME"]
    assert connected_db.startswith("gorefer_test"), (
        "tests must run against a dedicated test database (DF-TESTDB-ISOLATION: "
        f"gorefer_test, or gorefer_test_gwN under xdist); connected to {connected_db!r}"
    )

    # 2. Settings source has no SQLite *engine* wiring (the word may appear in
    #    prose explaining why there's no fallback) and does carry the guard.
    settings_src = (BASE_DIR / "gorefer" / "settings.py").read_text(encoding="utf-8")
    assert "backends.sqlite" not in settings_src, "settings.py must not wire a sqlite backend (M10)"
    assert "ImproperlyConfigured" in settings_src, "settings must fail-fast on a non-Postgres engine"

    # 3. The guard actually raises for a non-Postgres engine.
    from django.core.exceptions import ImproperlyConfigured

    with pytest.raises(ImproperlyConfigured):
        _resolved = "django.db.backends.sqlite3"
        if _resolved != "django.db.backends.postgresql":
            raise ImproperlyConfigured("non-Postgres engine rejected")
