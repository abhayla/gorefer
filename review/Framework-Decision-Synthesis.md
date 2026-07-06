# GoRefer — Framework Decision Synthesis (3-LLM cross-check + recommendation)

> Consolidates `ChatGPT-Framework.md`, `Grok-Framework.md`, `Gemini-Framework.md` (prompt: `Framework-Evaluation-Prompt.md`). 2026-07-06.

## Vote
| LLM | 1st choice | 2nd choice |
|---|---|---|
| ChatGPT | **FastAPI** | Django (DRF) |
| Grok | **Django** (DRF/Ninja) | FastAPI |
| Gemini | **FastAPI** | Django + Ninja |
| DeepSeek | **Django** (+django-tenants) | FastAPI |

**Tally: FastAPI 2 · Django 2 — a dead tie.** Both finalists are Python; the whole decision narrowed to FastAPI vs Django, and the vote no longer breaks it.

## Unanimous across all three (locked regardless of backend)
- **Language: Python** (one language for a solo Python-fluent founder).
- **Frontend: server-rendered templates (Jinja/Django) + HTMX + Tailwind. NOT React/Next/SPA** for Sprint 1 — WhatsApp → slow Android → light HTML wins; landing <15–100KB.
- **Database: PostgreSQL**, single central app (no edge) — trivially handles ~4 req/s and few-M rows/yr.
- **Event stream: plain append-only Postgres table (JSONB payload), no Kafka/CQRS**; rollups via cron/BackgroundTasks/worker.
- **Redirect: non-blocking** — validate + 302, hand the click/event write to a background task; idempotent via unique constraints.
- **Adapters** behind interfaces for partners/CRM/WhatsApp; **Pydantic** for strict typed contracts.
- **Multi-tenancy: `tenant_id` discriminator column on every non-global table from day 1**; keep single DB.
- **API-first** so a richer customer "My Referrals" SPA (React/Next) can be added later on the same API.
- Keep infra minimal at this scale; no microservices/K8s/edge.

## The only open question: FastAPI vs Django
- **FastAPI case (ChatGPT, Gemini):** GoRefer's core is API + events + integrations + redirect (not forms-over-models); async redirect via `BackgroundTasks` needs no Celery/Redis day 1; native Pydantic = best contract safety for the strict Zoho/opener-vs-referrer fields; lean, low cognitive load. Cost = "setup tax": assemble ORM (SQLAlchemy 2.0), migrations (Alembic), auth, admin yourself (mitigate: SQLAdmin/Piccolo for instant admin; env-based admin auth).
- **Django case (Grok):** batteries = fastest Sprint-1 velocity; built-in admin jump-starts the M7 dashboard; auth/ORM/migrations free; mature multi-tenancy (django-tenants). **Django Ninja** adds FastAPI-style Pydantic typing + async inside Django (best-of-both). Cost = heavier/opinionated; admin can accumulate logic; schema-per-tenant has operational nuance.

## Recommendation (Claude, as advisor) — after the 2–2 tie
The four-way cross-check is split **2–2**, so the *vote* no longer decides; the *reasoning* does. Both finalists are Python + server-rendered + Postgres, and both are **non-regrettable** — frontend, DB, and architecture are identical either way. The choice hinges on ONE question:

**Do you want the admin dashboard + auth + multi-tenancy essentially free out of the box (→ Django), or a lean, explicitly-typed API core you assemble/generate (→ FastAPI)?**

Given Abhay's specific priorities — a **part-time solo** builder, an **admin/CRUD-heavy** app, and the **multi-tenant SaaS ambition (A2)** he raised himself — the batteries case edges it. django-tenants is a mature single-DB answer to A2; Django's admin nearly gives M7 for free; auth is built-in. FastAPI's remaining unique edge is leanness — its typing edge is closed by **Django Ninja**, and its async edge is moot at ~4 req/s where sync + `transaction.on_commit()` is fine.

**Slight lean: Django + Django Ninja + HTMX + Tailwind + PostgreSQL + django-tenants** (background via `transaction.on_commit` + a light DB-backed queue; add Celery/Redis only when scheduled workflows demand). **FastAPI + SQLAlchemy/Alembic + Pydantic + SQLAdmin** is the equally-safe alternative for a leaner, API-purist core.

**This is close enough that further debate has near-zero ROI — pick one and we scaffold today.** Decision rule: Django(+Ninja) for batteries + multi-tenancy out of the box (the lean, given the SaaS goal); FastAPI for a lean typed core you're happy to assemble.

**Update — 5th input (general framework analysis):** doesn't add a vote but makes one decisive point: *for the server-rendered Jinja/templates + HTMX route (which we've already locked unanimously), Django is the more natural home* — its templating, forms, ORM, and admin are purpose-built for server-driven rendering; FastAPI + HTMX means hand-assembling those. It also frames the split as "server-rendered/CRUD/admin → Django" vs "API-first + React/ML-serving → FastAPI"; GoRefer is squarely the former. Since the frontend approach is settled, this tips the coin-flip toward **Django**. **Recommendation firmed: Django + Django Ninja (or DRF) + HTMX + Tailwind + PostgreSQL + django-tenants.**

---

## Decision status: LOCKED (2026-07-06)
Encoded as **[ADR-024](../docs/architecture/02-Architecture-Decisions-ADR.md)** (technology stack) and in the build guide **[`implementation/10` §1](../implementation/10-Claude-Code-Implementation-Guide.md)**. Per-LLM captures: `ChatGPT-Framework.md`, `Grok-Framework.md`, `Gemini-Framework.md`, `DeepSeek-Framework.md`. Neutral source prompt: `Framework-Evaluation-Prompt.md`.
