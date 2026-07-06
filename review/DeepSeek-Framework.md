# GoRefer — Framework Evaluation: DeepSeek response

> External review of the tech-stack question (prompt: `Framework-Evaluation-Prompt.md`). Captured 2026-07-06.

## Recommendation: Python + Django + HTMX + Tailwind + PostgreSQL + django-tenants
- **Backend:** Django 5.x (+ DRF for APIs)
- **Frontend:** server-rendered Django templates + HTMX + Tailwind
- **DB:** PostgreSQL, **django-tenants** for multi-tenancy
- **Background tasks:** DB-backed light queue (django-lightweight-queue / django-rq); **no Celery until scheduled workflows demand it**
- **Typed contracts:** Pydantic models for CRM/webhook payloads alongside DRF serializers

### Why it fits
- **Solo Python fluency** — all Python; batteries (ORM, migrations, admin, auth, forms, templates) = time on business logic, not glue.
- **Sprint-1 velocity** — Django's built-in admin gives a CRUD dashboard (funnel/leaderboards/leads) with a few ModelAdmin tweaks, no views written; redirect is a plain function view (indexed query + `transaction.on_commit()` fire-and-forget insert + 302, <10ms sync); landing = template + compliance auto-injected via a template tag from the config cascade.
- **Performance** — sync Django is trivial at 4 req/s; at 100× (25k/day) still <1 req/s average; Postgres idle.
- **Multi-tenant future** — django-tenants = per-schema isolation in one Postgres DB (hard isolation, per-tenant config/branding/domain routing); matches the single central-app constraint; cascade as JSON on the Tenant model.
- **API-first** — every feature a DRF endpoint, consumed by HTMX templates + future external clients; free OpenAPI docs.

### Second choice: FastAPI + Jinja2 + HTMX + Tailwind
Pick it if the redirect *must* be async at code level (asyncpg), if philosophically opposed to Django's monolith and want explicit control, or if the admin must be highly custom from day 1 (build it or use SQLAdmin/FastAPI-Admin). Why not first: no built-in admin; less multi-tenancy momentum (roll your own middleware); sacrifices Sprint-1 speed for architectural purity you don't yet need.

## Trade-off table (DeepSeek)
| Criterion | Django+HTMX | FastAPI+HTMX | Next.js | Rails/Laravel | Go |
|---|---|---|---|---|---|
| Solo Python maintainability | ★★★★★ | ★★★★★ | ★☆☆☆☆ | ★★☆☆☆ | ★☆☆☆☆ |
| Sprint-1 velocity | ★★★★★ (admin/ORM/forms) | ★★★☆☆ (build own admin) | ★★★☆☆ | ★★★★☆ | ★★☆☆☆ |
| Redirect + event perf | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★★ |
| Multi-tenant SaaS fit | ★★★★★ (django-tenants) | ★★★☆☆ (DIY) | ★★★☆☆ | ★★★★☆ | ★★☆☆☆ |
| Future customer dashboard | ★★★★☆ | ★★★★☆ | ★★★★★ | ★★★★☆ | ★★★★☆ |
| Typing / contract safety | ★★★★☆ (Pydantic+DRF) | ★★★★★ (native Pydantic) | ★★★★☆ | ★★★☆☆ | ★★★★☆ |
| Ecosystem/hosting (central PG) | ★★★★★ | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★☆☆ |

## Risks + mitigations
- **"Django is sync" for redirect** — non-issue at scale; guarantee non-blocking via `transaction.on_commit()` + a durable task table or django-rq. Don't add async for 4 req/s.
- **Admin customisation limits** — fine for internal dashboard; embed small JS/Vue or a custom view if charts get interactive.
- **HTMX ceiling** — handles tabs/polling/modals for "My Referrals"; adopt a small SPA for that area later if needed (API-first makes it natural).
- **django-tenants migration nuance** — separate tenant vs shared apps early even with one tenant in Sprint 1.

## Frontend verdict: server-rendered templates + HTMX + Tailwind
Mobile-first, WhatsApp, slow networks → server-rendered HTML + purged Tailwind + ~14KB HTMX beats any SPA bundle; keeps the stack fully Python. Door open for a richer SPA later on the same DRF API.

## Summary
Go **Django + HTMX + Tailwind + Postgres + django-tenants** — optimises a solo dev's velocity, admin instantly, handles current + 100× load without complexity, smooth path to multi-tenancy. Sync is not a bottleneck; avoid async until data proves need. FastAPI is the second choice if you genuinely want to build more from scratch / prefer async-by-default, but you lose a sprint's worth of admin + tenant management Django gives free.
