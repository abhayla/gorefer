# GoRefer — Framework Evaluation: Gemini response

> External review of the tech-stack question (prompt: `Framework-Evaluation-Prompt.md`). Captured 2026-07-06.

## Recommendation: FastAPI + HTMX + PostgreSQL
Optimise for **cognitive load and payload size**, not novelty. At ~4 req/s and a few million rows/year, Postgres won't notice; the true bottlenecks are **network latency on cheap Android** and **your limited hours**.

### Why it fits
- **Redirect hot path (`GET /r/{id}`):** FastAPI is ASGI/async — fetch config, trigger a native **`BackgroundTasks`** worker to write the immutable event log async, and return the 302 immediately. Redirect latency <20ms **without needing Celery or Redis on day one.**
- **Contract & config safety:** the 3-tier config cascade + strict CRM/WhatsApp payloads match **Pydantic** flawlessly — eliminates runtime KeyErrors on polymorphic fields across brokers.
- **Zero-JS landing pages:** Jinja2 + HTMX → landing under ~15KB, no JS runtime to parse on a low-end phone.

## Second choice: Django + Django Ninja
Pick Django if you don't want to choose your own components (SQLAlchemy, Alembic, Auth) and prefer a framework that decides for you — production-ready ORM, migrations, secure session auth out of the box. **Django Ninja** brings FastAPI-style Pydantic typing + async into Django (best of both). You forfeit a tiny bit of raw async perf — invisible at 4 req/s. Trigger: if you'd spend more than a weekend fighting Alembic/session lifecycle.

## Trade-off matrix (Gemini)
| Dimension | FastAPI + HTMX (Winner) | Django + Ninja | Node/TS (Next.js) |
|---|---|---|---|
| Solo maintainability (Python dev) | Highest (low abstraction) | High (opinionated) | Low (context switch) |
| Sprint 1 velocity | High (rapid API, thin UI) | Highest (admin+auth instant) | Medium |
| Redirect performance | Excellent (async non-blocking) | Good (async views) | Excellent but heavy DB client |
| Slow-network mobile UI | Excellent (<15KB) | Excellent (templates) | Poor (JS hydration) |
| Multi-tenant fit | Explicit (column isolation) | Excellent (django-tenants) | Good (manual) |
| Contract/API safety | Highest (native Pydantic) | Highest (Ninja Pydantic) | High (TS) |

## Frontend: server-rendered HTMX, NOT React/SPA
WhatsApp → slow Indian cellular → budget Android; a JS framework forces download+parse+execute before the form shows → big conversion drop-off. Plan: (1) branded Jinja2+Tailwind landing with the compliance/risk block in the layout; (2) lead capture via HTMX `hx-post`; (3) admin dashboard = HTML tables + HTMX polling (`hx-trigger="every 10s"`) for leaderboard/sync-freshness. Keep the door open: Pydantic schemas decouple logic from delivery — a future React/Next SPA hits the same core under `/api/v1/`.

## Solo-founder risks + mitigations
1. **Setup fatigue (Alembic & Auth tax):** for Sprint 1 use admin-only auth via a secure cookie / env `ADMIN_SECRET_KEY`; don't roll full JWT yet. Use **SQLAdmin** or **Piccolo Admin** for an instant Django-like DB UI over SQLAlchemy models with zero frontend code.
2. **Over-engineering the event stream:** keep it purely relational in Postgres — an append-only `journey_events` table (id, journey_id, tenant_id, event_type, payload JSONB, created_at) + index on (tenant_id, journey_id). At 3M rows/yr Postgres aggregates leaderboards/rollups in ms; run aggregations via cron Python scripts or BackgroundTasks — no worker infra needed yet. (No Kafka/CQRS.)
3. **Multi-tenancy lock-in:** implement discriminator-column isolation from day 1 — `tenant_id` on every non-global table; a FastAPI dependency extracts tenant_id from host/path and injects it into the query context automatically. Prevents cross-tenant leaks while staying single-DB.
