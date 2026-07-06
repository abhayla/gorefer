# GoRefer — Framework Evaluation: Grok response

> External review of the tech-stack question (prompt: `Framework-Evaluation-Prompt.md`). Captured 2026-07-06.

## Recommendation
**Python + Django (DRF or Django Ninja for APIs) + server-rendered templates + HTMX + Tailwind.**

### Why it wins for these constraints
Django maximizes solo-maintainability and Sprint 1 velocity while giving a clean path to the multi-tenant future, staying in one language:
- **Built-in admin (customized)** for the internal dashboard (funnel, leaderboards, lead lists, sync status) — a massive solo time-saver; extend with custom views/filters + HTMX actions instead of building CRUD from scratch.
- Excellent ORM + migrations for the immutable event model, config tables, future tenant models; Postgres fits naturally.
- Forms + templates make the mobile-first landing fast to build and lightweight to serve.
- Mature libraries for exactly what's needed: multi-tenancy (**django-tenants** schema-per-tenant, or row-level security), config-over-code (constance or custom JSONB + cascade resolver), feature flags (waffle/constance), background tasks.
- DRF (or lighter **Django Ninja** with native Pydantic) covers the API-first requirement without a separate frontend framework yet.
- Provider-agnostic: `ReferralProvider` model + registry + adapter classes; Pydantic models for strict CRM/event contracts.
- Compliance block: middleware + template tag/include, hard to bypass.

**Performance:** trivial at ~4 req/s and <3M rows/yr — "raw Postgres is bored," 100× headroom. Keep the redirect non-blocking: minimal validation in the view, hand the click/journey write to a background task (`transaction.on_commit`, django-q or Celery), idempotent via unique constraints.

**Multi-tenant future:** django-tenants + tenant-aware middleware → hard isolation, per-tenant config/branding/compliance, pricing hooks with little rework. RLS + queryset filtering is a lighter single-schema alternative; for financial data prefer strong isolation.

### Second choice: FastAPI + Pydantic + Jinja + HTMX + Tailwind (custom or sqladmin dashboard)
Pick FastAPI instead if you strongly prefer explicit async everywhere + first-class Pydantic typing for every contract from day one, and are comfortable building/extending the internal admin yourself rather than starting from Django admin. Slight edge on typing safety + modern async feel; you lose the admin/CRUD velocity win and take on more boilerplate for tenancy, auth, migrations, and internal UI. Choose it when the integration surface + strict payload contracts are clearly the highest-risk early area.

## Trade-off table (Grok)
| Criterion | Django | FastAPI | Next.js (TS) | Go | Rails |
|---|---|---|---|---|---|
| Solo Python maintainability | Excellent | Very Good | Poor | Poor | Poor |
| Sprint 1 velocity | Excellent (admin/forms/ORM/auth) | Good | Good | Fair | Excellent but new lang |
| Perf / redirect + events | Excellent | Excellent | Good | Excellent | Good |
| Multi-tenant SaaS fit | Excellent | Good | Good | Fair | Excellent but new lang |
| Future customer dashboard | Good | Good | Excellent | Fair | Good |
| Typing / contract safety | Good (Pydantic + DRF/Ninja) | Excellent | Excellent | Good | Good |
| Ecosystem/hosting (central PG) | Excellent | Excellent | Good | Good | Excellent |

## Risks / gotchas (Django) + mitigations
- **Admin accumulating logic / slowness** → treat admin as data-inspection/management only; core logic in services/managers/tasks; custom admin views + HTMX for interactivity.
- **"Never block on slow writes" on redirect** → minimal work in the view (validate + 302), hand creation to a background task via `transaction.on_commit` (django-q Postgres-backed = zero extra infra, or Celery); idempotency keys/unique constraints.
- **Multi-tenancy choice locks in early** → decide week 1; prefer strong isolation (schemas or RLS + tenant-aware querysets) for financial data; start with a single bootstrap tenant.
- **Future rich SPA** → put every feature behind a DRF/Ninja API from day one; keep templates/HTMX thin; add Next.js/SvelteKit later on the same APIs. HTMX + Alpine.js carry far.
- **Compliance non-removable** → middleware rewriting HTML + mandatory template inheritance; document as an architectural invariant.
- **Event stream + rollups** → append-only Event (JSONB), no update/delete paths in code or admin; nightly task or materialized views build rollups; JSONB + GIN indexes for analytics.

## Server-rendered vs SPA (Sprint 1)
**Strongly recommend server-rendered Django templates + Tailwind + HTMX.** Traffic is WhatsApp→mobile→slow Android; server-rendered is lighter, better TTI, no hydration issues. Core interactions are forms + admin CRUD/analytics — Django forms + admin + HTMX handle them with minimal code. Keep the door open: expose a clean API before each UI, structure templates with reusable partials (django-components or includes), use HTMX heavily (delays a full frontend 1–2 years); add Next.js/SvelteKit for "My Referrals" only when it genuinely needs complex client state/charts/real-time.

## Bottom line
Django gives the highest probability of shipping a maintainable, correct Sprint 1 quickly while preserving future options — the pragmatic choice for a solo Python founder valuing long-term ownership over novelty. Start with it, add the task queue + tenancy scaffolding early, grow into a real multi-tenant platform without a rewrite.
