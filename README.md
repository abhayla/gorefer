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

# 2. Configure env (copy the template, fill values)
cp .env.example .env
#   - For a zero-dependency run keep DB_ENGINE=sqlite (no Postgres needed).
#   - For a production-shaped run set DB_ENGINE=postgres + the DB_* vars (enables django-tenants).

# 3. Apply migrations (forward-only) and seed the single ReferralProgram (Zerodha)
python manage.py migrate
python manage.py seed_program          # idempotent: tenant + central config + partner + program + redirect rule
python manage.py seed_demo             # optional: demo journeys/events so the funnel + dashboard render (no conversions)
python manage.py recompute_rollups     # recompute daily/monthly rollups for any dirty periods (run by a worker in prod)

# 4. (Optional) create the admin from env vars — no plaintext password, hash only
#    Generate a hash:  python -c "from django.contrib.auth.hashers import make_password; print(make_password('your-pw'))"
#    Put ADMIN_EMAIL + ADMIN_PASSWORD_HASH in .env, then:
python manage.py bootstrap_admin       # idempotent

# 5. Run
python manage.py runserver
#    /            -> PIFS-branded home (compliance footer auto-injected)
#    /api/health  -> JSON liveness probe
#    /admin/      -> admin (behind ENABLE_ADMIN_DASHBOARD)
```

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
