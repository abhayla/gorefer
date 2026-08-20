# GoRefer

> **Building GoRefer?** Start with [`CLAUDE.md`](./CLAUDE.md) — the operating manual and entry point for Claude Code. It maps the docs, states the non-negotiable guardrails, and defines the Sprint 1 build order.

GoRefer is a **referral management & referral intelligence platform**: users manage, share, and track referral links from partner businesses (Sprint 1: Zerodha) through multi-channel campaigns (WhatsApp/WATI + Zoho CRM), with AP compliance built in. This repository holds the **Sprint 1** design and implementation — a deliberately extensible foundation — authored with AI assistance. The documents below are the single source of truth; the raw ChatGPT/working material that seeded them is preserved under `_source-archive/` in the private companion repo [gorefer-ops](https://github.com/abhayla/gorefer-ops).

## Document Map

| Area | Document | Path |
|------|----------|------|
| Foundation | Foundation Specification | [docs/foundation/01-GoRefer-Foundation-Specification.md](docs/foundation/01-GoRefer-Foundation-Specification.md) |
| Foundation | Constitution | [docs/foundation/03-GoRefer-Constitution.md](docs/foundation/03-GoRefer-Constitution.md) |
| Architecture | Architecture Decisions (ADR) | [docs/architecture/02-Architecture-Decisions-ADR.md](docs/architecture/02-Architecture-Decisions-ADR.md) |
| Architecture | System Architecture | [docs/architecture/04-System-Architecture.md](docs/architecture/04-System-Architecture.md) |
| Architecture | Partner Hierarchy & Vendor Independence (target/vision — not locked) | [docs/architecture/13-Partner-Hierarchy-and-Vendor-Independence.md](docs/architecture/13-Partner-Hierarchy-and-Vendor-Independence.md) |
| Database | Database Design | [docs/database/05-Database-Design.md](docs/database/05-Database-Design.md) |
| API | API Specification | [docs/api/06-API-Specification.md](docs/api/06-API-Specification.md) |
| UI/UX | UI/UX Specification | [docs/ui-ux/07-UI-UX-Specification.md](docs/ui-ux/07-UI-UX-Specification.md) |
| Integrations | Zoho + WATI Integration | [docs/integrations/08-Zoho-WATI-Integration.md](docs/integrations/08-Zoho-WATI-Integration.md) |
| Workflow | Referral Workflow & Edge Cases | [docs/workflow/11-Referral-Workflow-and-Edge-Cases.md](docs/workflow/11-Referral-Workflow-and-Edge-Cases.md) |
| Workflow | Resolved Gaps & Edge-Case Decisions | [docs/workflow/12-Resolved-Gaps-and-Edge-Case-Decisions.md](docs/workflow/12-Resolved-Gaps-and-Edge-Case-Decisions.md) |
| Review | LLM Review Pack | `review/09-LLM-Review-Pack.md` in the private [gorefer-ops](https://github.com/abhayla/gorefer-ops) repo |
| Review | Review Bundle (full concatenation) | `review/GoRefer-Review-Bundle.md` in the private [gorefer-ops](https://github.com/abhayla/gorefer-ops) repo |
| Implementation | Claude Code Implementation Guide | [implementation/10-Claude-Code-Implementation-Guide.md](implementation/10-Claude-Code-Implementation-Guide.md) |
| Decision | Framework/Stack Decision & Synthesis (basis of ADR-024) | `review/Framework-Decision-Synthesis.md` in the private [gorefer-ops](https://github.com/abhayla/gorefer-ops) repo |
| Design | UI Mockups (landing, dashboard, components, journey, etc.) | [mockups/](mockups/) |
| Source | Original ChatGPT/source & superseded drafts | `_source-archive/` in the private [gorefer-ops](https://github.com/abhayla/gorefer-ops) repo |
| **Integration boundary** | **Zoho ⇄ GoRefer — contract** (webhook, HMAC seal, status→stage, upsert-by-mobile) | [Zoho-GoRefer/Zoho-Integration-Contract.md](Zoho-GoRefer/Zoho-Integration-Contract.md) |
| **Integration boundary** | **Zoho ⇄ GoRefer — live state** (flags, what's proven, what's staged) | `Zoho-GoRefer/Zoho-GoRefer-State.md` in the private [gorefer-ops](https://github.com/abhayla/gorefer-ops) repo (pointer stub kept here) |
| **Integration boundary** | Zoho-side Deluge signer — paste-ready steps | [Zoho-GoRefer/Zoho-Signer-Steps.md](Zoho-GoRefer/Zoho-Signer-Steps.md) |
| **Integration boundary** | **Wati ⇄ GoRefer — contract** (send shape, terminal-status rule, allowlist gate, reconcile sweep) | [Wati-GoRefer/Wati-Integration-Contract.md](Wati-GoRefer/Wati-Integration-Contract.md) |
| **Integration boundary** | **Wati ⇄ GoRefer — templates** (elementNames, ids, categories, role→template map) | [Wati-GoRefer/Wati-GoRefer-Templates.md](Wati-GoRefer/Wati-GoRefer-Templates.md) |

> **Sibling projects** (filed by the system that *owns and executes* the artifact):
> **`C:\Abhay\5Wealths\Zoho-Project\`** — everything running inside Zoho (Deluge, workflow rules,
> the WhatsApp Send Queue) → start at `zoho-pifs-crm-state.md`.
> **`C:\Abhay\5Wealths\Wati-Project\`** — the WhatsApp channel/platform (delivery health, template
> catalogue, nightly report) → start at `wati-shared-platform-knowledge.md`.
> The two `*-GoRefer/` folders above are **GoRefer's side** of each boundary.

## Running locally (Sprint 1 skeleton — M1)

The app is **Django + Django Ninja + HTMX + Tailwind + PostgreSQL** (stack LOCKED, ADR-024). **PostgreSQL is the sole supported engine** (M10) across dev/test/CI/prod — there is no SQLite fallback. Multi-tenancy is single-schema `tenant_id` discriminator isolation (ADR-023, Q-M1-1). Requires Python 3.11+.

```bash
# 1. Create + activate a virtualenv, install deps
python -m venv .venv
.venv/Scripts/activate          # Windows (Git Bash);  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt

# 2. Provision the database. PostgreSQL is the ONLY supported engine (M10) — it
#    matches production and GoRefer relies on Postgres-only behaviour (JSONB,
#    partial-unique constraints, case-sensitivity). There is NO SQLite fallback;
#    settings fail-fast if the engine isn't Postgres. Create a dedicated
#    least-privilege role + db (run as a Postgres superuser; pick your own password):
#      CREATE ROLE gorefer LOGIN PASSWORD '<choose-one>';
#      CREATE DATABASE gorefer_dev OWNER gorefer;
#      \c gorefer_dev
#      GRANT ALL ON SCHEMA public TO gorefer;
#      ALTER ROLE gorefer CREATEDB;   -- lets the test runner create gorefer_test

# 3. Configure env (copy the template; fill values in the gitignored .env — NEVER commit).
cp .env.example .env
#    .env.example lists KEY NAMES only. Set the Postgres DB_* vars:
#      DB_NAME=gorefer_dev  DB_HOST=127.0.0.1  DB_PORT=5432
#      DB_USER=gorefer      DB_PASSWORD=<the gorefer role password>
#      TEST_DB_NAME=gorefer_test

# 4. Apply migrations (forward-only) and seed the single ReferralProgram (Zerodha)
python manage.py migrate
python manage.py seed_program          # idempotent: tenant + central config + partner + program + redirect rule
python manage.py seed_demo             # optional: demo journeys/events so the funnel + dashboard render (no conversions)
python manage.py recompute_rollups     # recompute daily/monthly rollups for any dirty periods (run by a worker in prod)

# Background queue (django-q2, ORM broker — no Redis). In dev/CI/demo, Q_ASYNC=false
# runs tasks INLINE (no worker needed). In production set Q_ASYNC=true and run:
#   python manage.py setup_schedules    # register recurring schedules (idempotent):
#                                       #   - rollup recompute (every 5 min)
#                                       #   - Zoho WRITE backfill sweep (every 10 min) —
#                                       #     re-enqueues leads that never reached Zoho.
#                                       #     REQUIRED with ENABLE_ZOHO_WRITE on, else a
#                                       #     lead stranded by a Zoho outage never retries.
#   python manage.py qcluster           # the worker: WATI sends + terminal-status polling
#                                       # + the async Zoho lead upsert + schedules
# Stuck leads are visible in the admin: Leads -> "Zoho sync" filter (unsynced /
# needs attention / awaiting retry), with a "Retry Zoho sync" action.

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

**Inter is self-hosted** at `static/fonts/inter-latin-var.woff2` (one variable woff2, latin subset, covers weights 400–800). Pages load **no third-party origin at all** — no `fonts.googleapis.com`, no CDN. This is not only a privacy/offline preference: a render-blocking stylesheet on a third-party origin leaves the document loading forever on any network that *blackholes* that origin (the request neither completes nor fails), so the page never reaches "idle" and browser automation cannot read or fill it. `tests/test_no_third_party_origin.py` fails if a cross-origin `<link>`/`<script>` is reintroduced on a public page.

**Operator commands (no browser needed):**

```bash
# Run the FULL capture loop end-to-end and print a structured report.
# Uses the real service layer and honors the live flags: with the integration flags
# OFF this is log-only (zero network, zero live effect). Idempotent — re-running with
# the same mobile updates rather than duplicating. Never fabricates account status.
python manage.py golive_smoke --referrer EKU497 --mobile 9876543210 [--name X] [--email Y] [--json]

# Flip the landing mode without the Preferences screen (same config path the UI uses).
# `direct` is refused (non-zero exit) unless a live /d/{slug} disclosure page exists — ADR-032.
python manage.py set_landing_mode page|direct [--tenant pifs]
```

**Tests + lint** (run against Postgres `gorefer_test`; CI runs the same against a Postgres service container):

```bash
ruff check .
python manage.py makemigrations --check --dry-run   # fails on schema drift
python -m pytest -q                                 # serial (~6 min)
python -m pytest -q -n 4                            # parallel (~2 min) — see below
```

**Parallel runs (DF-TESTDB-ISOLATION).** `-n 4` uses pytest-xdist, and pytest-django
gives each worker its **own** database (`gorefer_test_gw0`, `_gw1`, …). That isolation
is what makes it correct, not just faster: on one shared test DB the workers deadlock
on `otp_challenges` and the lock collision looks exactly like a regression.

Two caveats worth knowing before you misread a red suite:
- **Don't run two pytest invocations at once** against the same DB name — the second
  fails with `database "gorefer_test" already exists` / `is being accessed by other
  users`. That is a collision, **not** a code regression. For a genuinely concurrent
  run, give it its own name: `TEST_DB_NAME=gorefer_test_mine python -m pytest -q`.
- If a run is killed mid-way it can leave the test DB behind; drop it (or use
  `--create-db`) before the next run.

**Feature flags** live in one place — `gorefer/flags.py`, resolved from env at startup (`ENABLE_*`, plus the single swappable `REFERRAL_INCENTIVE_CLAIM`). Defaults keep every not-yet-built capability and every external adapter **off** (adapters log their intended call instead of sending), so demo mode runs end-to-end with no external systems.

> **PostgreSQL only (M10).** PostgreSQL is the sole supported engine across dev/test/CI/prod — there is no SQLite fallback, and settings raise `ImproperlyConfigured` if the resolved DB engine isn't Postgres (a green run on any other engine would be false confidence, since GoRefer relies on JSONB / partial-unique constraints / case-sensitivity). Multi-tenancy is **single-schema `tenant_id` discriminator** isolation (not django-tenants schema-per-tenant); `apps.tenants` keeps a plain Tenant/Domain registry and isolation is enforced by tenant-scoped managers + `TenantResolutionMiddleware` + composite unique constraints. Schema-per-tenant physical isolation is deferred (backlog DF-7). See the M1 QUESTION (Q-M1-1) in `COORDINATION.md` in the private [gorefer-ops](https://github.com/abhayla/gorefer-ops) repo (pointer stub kept here).

## How to use for external LLM review

To have another LLM review the design, feed it `review/GoRefer-Review-Bundle.md` in the private [gorefer-ops](https://github.com/abhayla/gorefer-ops) repo (the full concatenated spec) as context, then apply the questions and rubric in `review/09-LLM-Review-Pack.md` in the private [gorefer-ops](https://github.com/abhayla/gorefer-ops) repo.

## Notes

The numbered documents (01–12) cross-reference each other by their number and name (e.g. "see 05-Database-Design"). Those references are unchanged; every target is listed with its new path in the table above. `_source-archive/` (in [gorefer-ops](https://github.com/abhayla/gorefer-ops)) holds raw and superseded material (ChatGPT transcripts, context/build/resume briefs, master source-of-truth, and the previous `00-README.md`) kept for provenance — not part of the active spec.
