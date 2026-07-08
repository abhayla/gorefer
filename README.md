# GoRefer

> **Building GoRefer?** Start with [`CLAUDE.md`](./CLAUDE.md) — the operating manual and entry point for Claude Code. It maps the docs, states the non-negotiable guardrails, and defines the Sprint 1 build order.

GoRefer is a **referral management & referral intelligence platform**: users manage, share, and track referral links from partner businesses (Sprint 1: Zerodha) through multi-channel campaigns (WhatsApp/WATI + Zoho CRM), with AP compliance built in. This repository holds the **Sprint 1** design and implementation — a deliberately extensible foundation — authored with AI assistance. The documents below are the single source of truth; the raw ChatGPT/working material that seeded them is preserved under `_source-archive/`.

## Document Map

| Area | Document | Path |
|------|----------|------|
| Foundation | Foundation Specification | [docs/foundation/01-GoRefer-Foundation-Specification.md](docs/foundation/01-GoRefer-Foundation-Specification.md) |
| Foundation | Constitution | [docs/foundation/03-GoRefer-Constitution.md](docs/foundation/03-GoRefer-Constitution.md) |
| Architecture | Architecture Decisions (ADR) | [docs/architecture/02-Architecture-Decisions-ADR.md](docs/architecture/02-Architecture-Decisions-ADR.md) |
| Architecture | System Architecture | [docs/architecture/04-System-Architecture.md](docs/architecture/04-System-Architecture.md) |
| Database | Database Design | [docs/database/05-Database-Design.md](docs/database/05-Database-Design.md) |
| API | API Specification | [docs/api/06-API-Specification.md](docs/api/06-API-Specification.md) |
| UI/UX | UI/UX Specification | [docs/ui-ux/07-UI-UX-Specification.md](docs/ui-ux/07-UI-UX-Specification.md) |
| Integrations | Zoho + WATI Integration | [docs/integrations/08-Zoho-WATI-Integration.md](docs/integrations/08-Zoho-WATI-Integration.md) |
| Workflow | Referral Workflow & Edge Cases | [docs/workflow/11-Referral-Workflow-and-Edge-Cases.md](docs/workflow/11-Referral-Workflow-and-Edge-Cases.md) |
| Workflow | Resolved Gaps & Edge-Case Decisions | [docs/workflow/12-Resolved-Gaps-and-Edge-Case-Decisions.md](docs/workflow/12-Resolved-Gaps-and-Edge-Case-Decisions.md) |
| Review | LLM Review Pack | [review/09-LLM-Review-Pack.md](review/09-LLM-Review-Pack.md) |
| Review | Review Bundle (full concatenation) | [review/GoRefer-Review-Bundle.md](review/GoRefer-Review-Bundle.md) |
| Implementation | Claude Code Implementation Guide | [implementation/10-Claude-Code-Implementation-Guide.md](implementation/10-Claude-Code-Implementation-Guide.md) |
| Decision | Framework/Stack Decision & Synthesis (basis of ADR-024) | [review/Framework-Decision-Synthesis.md](review/Framework-Decision-Synthesis.md) |
| Design | UI Mockups (landing, dashboard, components, journey, etc.) | [mockups/](mockups/) |
| Source | Original ChatGPT/source & superseded drafts | [_source-archive/](_source-archive/) |

## Running locally (Sprint 1 skeleton — M1)

The app is **Django + Django Ninja + HTMX + Tailwind + PostgreSQL** (stack LOCKED, ADR-024), with `django-tenants` for the multi-tenant boundary (ADR-023). Requires Python 3.11+.

```bash
# 1. Create + activate a virtualenv, install deps
python -m venv .venv
.venv/Scripts/activate          # Windows (Git Bash);  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt

# 2. Provision the database. Postgres is the DEFAULT (ADR-021); it matches
#    production and exercises Postgres-only behaviour (JSONB, partial-unique
#    constraints, case-sensitivity). Create a dedicated least-privilege role + db
#    (run as a Postgres superuser; substitute your own role password):
#      CREATE ROLE gorefer LOGIN PASSWORD '<choose-one>';
#      CREATE DATABASE gorefer_dev OWNER gorefer;
#      \c gorefer_dev
#      GRANT ALL ON SCHEMA public TO gorefer;
#      ALTER ROLE gorefer CREATEDB;   -- lets the test runner create test_gorefer_dev
#    (SQLite is an optional fallback: set DB_ENGINE=sqlite for a zero-dependency run.)

# 3. Configure env (copy the template; fill values in the gitignored .env — NEVER commit).
cp .env.example .env
#    .env.example lists KEY NAMES only. Set the Postgres DB_* vars:
#      DB_ENGINE=postgres  DB_NAME=gorefer_dev  DB_HOST=127.0.0.1  DB_PORT=5432
#      DB_USER=gorefer     DB_PASSWORD=<the gorefer role password>

# 4. Apply migrations (forward-only) and seed the single ReferralProgram (Zerodha)
python manage.py migrate
python manage.py seed_program          # idempotent: tenant + central config + partner + program + redirect rule
python manage.py seed_demo             # optional: demo journeys/events so the funnel + dashboard render (no conversions)
python manage.py recompute_rollups     # recompute daily/monthly rollups for any dirty periods (run by a worker in prod)

# Background queue (django-q2, ORM broker — no Redis). In dev/CI/demo, Q_ASYNC=false
# runs tasks INLINE (no worker needed). In production set Q_ASYNC=true and run:
#   python manage.py setup_schedules    # register the recurring rollup recompute (idempotent)
#   python manage.py qcluster           # the worker: WATI sends + terminal-status polling + schedules

# 5. (Optional) create the admin from env vars — no plaintext password, hash only
#    Generate a hash:  python -c "from django.contrib.auth.hashers import make_password; print(make_password('your-pw'))"
#    Put ADMIN_EMAIL + ADMIN_PASSWORD_HASH in .env, then:
python manage.py bootstrap_admin       # idempotent

# 6. Run
python manage.py runserver
#    /                          -> PIFS-branded home (compliance footer auto-injected)
#    /r/{client_id}             -> branded landing (renders; Continue -> 302 to Zerodha)
#    /api/health                -> JSON liveness probe
#    /api/analytics/funnel      -> read-only funnel (bots excluded; unique = approximate)
#    /api/zoho/status-webhook   -> Zoho conversion webhook (the ONLY writer of account status)
#    /admin-panel/              -> M7 admin dashboard (login-gated; dashboard / explorer / journey)
#    /admin-panel/referrers/    -> M9 Referral Profile search (client_id / name)
#    /admin-panel/referrer/{id}/-> M9 Referral Profile (one referrer's 360: Zoho enrichment + clicks + referred people)
#    /django-admin/             -> Django admin base
#    (both admin surfaces are behind ENABLE_ADMIN_DASHBOARD; sign in with the bootstrap admin)
```

> **Conversions come ONLY from Zoho** (`/api/zoho/status-webhook`, behind `ENABLE_ZOHO_WRITE` for the outbound lead write; the inbound status webhook is the sole writer of account/reward status — never fabricated internally). `seed_demo` seeds demo conversions **through** that ingest path so the funnel's "Account opened" reflects real Zoho-sourced data, dated to the true open date.

> **Zoho READ enrichment (M9)** is separate and read-only: behind `ENABLE_ZOHO_READ` (default off → seeded fixtures), it enriches the **Referral Profile** by matching a referrer to their Zoho Contact by `ClientId`. **Zoho WRITE stays OFF** (`ENABLE_ZOHO_WRITE=false`) — PIFS enters Zoho leads manually (DF-9); READ never sets conversion status (guardrail #2 holds).

> **Visual language — "Variant C · Cobalt Clean-Fintech"** (DA DESIGN LOCKED 2026-07-08): all screens use the cobalt theme in `mockups/*.html`. Tokens are **CSS variables** (`static/css/input.css`) wired into `tailwind.config.js`, so DF-10 runtime theming is a later config layer, not a rewrite. Rebuild `app.css` after template/CSS changes.

> **Compliance + helpline config.** The AP disclosure block + market-risk warning are canonical, **byte-exact** strings from a single source (`AP_DISCLOSURE_BLOCK` / `MARKET_RISK_WARNING` in settings, injected into every page) so wording can never drift. The landing page's "free, fully-assisted account opening — call" line uses **`SUPPORT_HELPLINE_PHONE`** (default `+91 73888 82020`, Ashok); the WhatsApp-share button uses the config-driven WATI number `WATI_BUSINESS_NUMBER` (`917080642020`) — the two are distinct and both config-driven.

**Frontend assets** (compiled Tailwind — NO CDN runtime; light + offline for mobile-first, ADR-003):

```bash
npm install            # once (installs tailwindcss)
npm run build:css      # compile static/css/app.css (purged from templates/); rerun after template changes
# npm run watch:css    # or watch during development
```

HTMX is vendored at `static/js/htmx.min.js`; the compiled CSS is `static/css/app.css`. Both are committed so the app runs without Node at runtime; rebuild the CSS whenever templates change (a test asserts the asset exists).

**Tests + lint** (CI runs the same on the SQLite path):

```bash
ruff check .
python manage.py makemigrations --check --dry-run   # fails on schema drift
python -m pytest -q
```

**Feature flags** live in one place — `gorefer/flags.py`, resolved from env at startup (`ENABLE_*`, plus the single swappable `REFERRAL_INCENTIVE_CLAIM`). Defaults keep every not-yet-built capability and every external adapter **off** (adapters log their intended call instead of sending), so demo mode runs end-to-end with no external systems.

> **SQLite vs PostgreSQL / django-tenants.** `django-tenants` is PostgreSQL-only (schema-per-tenant). To keep the skeleton bootable and CI green with no external DB, tenant schema-routing activates **only** when `DB_ENGINE=postgres`; on SQLite the same apps load without the router and the `tenant_id` discriminator columns still exist. The physical multi-tenant isolation strategy is a deferred decision — see the M1 QUESTION in [`COORDINATION.md`](./COORDINATION.md).

## How to use for external LLM review

To have another LLM review the design, feed it [review/GoRefer-Review-Bundle.md](review/GoRefer-Review-Bundle.md) (the full concatenated spec) as context, then apply the questions and rubric in [review/09-LLM-Review-Pack.md](review/09-LLM-Review-Pack.md).

## Notes

The numbered documents (01–12) cross-reference each other by their number and name (e.g. "see 05-Database-Design"). Those references are unchanged; every target is listed with its new path in the table above. `_source-archive/` holds raw and superseded material (ChatGPT transcripts, context/build/resume briefs, master source-of-truth, and the previous `00-README.md`) kept for provenance — not part of the active spec.
