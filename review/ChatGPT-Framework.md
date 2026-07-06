# GoRefer — Framework Evaluation: ChatGPT response

> External review of the tech-stack question (prompt: `Framework-Evaluation-Prompt.md`). Captured 2026-07-06.

## Recommendation

- **Backend:** Python + FastAPI
- **Frontend:** Server-rendered Jinja2 + HTMX + Tailwind CSS
- **Database:** PostgreSQL
- **Background jobs:** Celery (or Dramatiq) + Redis
- **ORM:** SQLAlchemy 2.0 + Alembic
- **Validation & contracts:** Pydantic v2
- **Hosting:** Single VM/container + managed PostgreSQL + Redis

"This is the stack I'd choose if I were responsible for maintaining GoRefer alone for the next 3–5 years."

## Why (key points)
1. **Python everywhere** — single language/debugger/ecosystem/mental model; the biggest factor for a solo Python-fluent founder. Matters more than shaving 5ms off redirect latency.
2. **API-first is FastAPI's natural strength** — everything in GoRefer is an API; Pydantic models become contracts + docs and prevent CRM field mix-ups.
3. **Redirect service fits perfectly** — at ~4 req/s FastAPI is "basically idle"; nowhere near needing Go.
4. **Event sourcing stays clean** — API serves projections, workers process them.
5. **Provider adapters** — Python ABCs + Pydantic model PartnerProvider/CRMProvider/MessagingProvider well; no framework fights it.
6. **Background workers** — Celery/Dramatiq mature for polling, rollups, webhooks, retries, notifications.
7. **Multi-tenancy** — FastAPI gives no tenancy, which is good: build exactly the isolation you want (tenant_id/org_id/user_id on every aggregate), no framework lock-in.

## Frontend: server-rendered (not React/Next/SPA)
- Users: WhatsApp → cheap Android → slow network → open one page → one form → redirect. Server rendering wins (no hydration/bundle/client routing). Landing page can stay <100KB.
- HTMX handles admin search/filters/pagination/status-update/refresh without Redux/React Query.
- Tailwind = consistent design, mobile-responsive, no CSS architecture headaches — ideal solo.
- React solves problems GoRefer doesn't have yet; keep the door open via API-first (later add React/Next/Flutter as just another API consumer).

## Second choice: Django (+ Django Admin + DRF)
Pick Django if the internal admin became the primary app, dozens of CRUD screens appeared, many business users logged in, or you wanted to lean on Django Admin heavily. But GoRefer is primarily API + events + integrations + redirect rather than forms-over-models, so FastAPI feels cleaner.

## Trade-off table (ChatGPT's ratings)
| Stack | Solo Python Maint. | Sprint 1 Speed | Redirect/Event Fit | Future SaaS | Future Rich UI | Typing | Overall |
|---|---|---|---|---|---|---|---|
| FastAPI + Jinja + HTMX | 5 | 5 | 5 | 5 | 4 | 5 | **Best** |
| Django + DRF | 5 | 5 | 4 | 5 | 4 | 4 | Excellent |
| Node + NestJS + React | 3 | 3 | 5 | 5 | 5 | 5 | Great team stack, weaker solo |
| Next.js full-stack | 2 | 3 | 4 | 4 | 5 | 4 | UI-first, not backend-first |
| Go | 2 | 2 | 5 | 4 | 2 | 4 | Performance you don't need |
| Ruby on Rails | 2 | 5 | 4 | 4 | 4 | 3 | Great if already Ruby |
| Laravel | 2 | 5 | 4 | 4 | 4 | 3 | Same as Rails |

## Risks of FastAPI + mitigations
1. **No built-in admin** → build the few admin screens you need.
2. **ORM learning curve** → use SQLAlchemy 2.0 only, don't mix styles.
3. **Auth batteries** → Sprint 1 only needs single admin + HTTP session + env bootstrap (small).
4. **Background jobs** → don't hand-roll a queue; use Celery/Dramatiq from day one.
5. **Event-sourcing discipline** → every state change creates an immutable event first; read models/rollups derive from the stream.

## Suggested architecture (one deployable app)
FastAPI → API · Redirect Service · Landing Pages (Jinja) · Admin (HTMX) · Event Store · Config Engine · Tenant Layer · Provider Adapters · Background Workers · Rollup Jobs · PostgreSQL.

## Final
Build **FastAPI + Jinja2 + HTMX + Tailwind + PostgreSQL + SQLAlchemy + Pydantic + Celery/Redis** — best balance of speed, maintainability, performance, and a clean path to multi-tenant SaaS without unnecessary complexity at this scale. When the customer-facing "My Referrals" experience grows highly interactive, add a React/Next frontend for that part only, on the same FastAPI API.
