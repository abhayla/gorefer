# GoRefer — Coordination Log (Design Authority ⇆ Engineer)

> **Purpose.** The async communication channel between the **Design Authority (DA)** — Claude in the Cowork planning/advisory session that authored the specs — and the **Engineer** — Claude Code, implementing in the dev environment. The two never talk directly. **Abhay relays entries between the sessions and commits this file**, so both sides always read the latest state here.

## Protocol (read before acting)
- **Design Authority (DA)** posts: missions, decisions, answers to questions, spec clarifications.
- **Engineer (Claude Code)** posts: mission STATUS (what built / deferred), PR summary, and any **surfaced inconsistency or ambiguity** — logged as a QUESTION; if it blocks, **pause on that point and do NOT invent a resolution.**
- Entry format:
  `### [YYYY-MM-DD] — FROM {DA|ENGINEER} — {MISSION|DECISION|QUESTION|ANSWER|STATUS|BLOCKER} — <short title>`
  then the body.
- **Append-only.** Newest entries at the bottom. Never edit past entries; add a new one (e.g. an ANSWER referencing an earlier QUESTION).
- **Engineer, before each mission:** read `CLAUDE.md` → `implementation/10-Claude-Code-Implementation-Guide.md` → this file. **After each mission:** append a STATUS entry and open the mission PR.
- **Relay:** Abhay copy-pastes new entries between the two sessions and commits this file.

---

## Log

### 2026-07-06 — FROM DA — MISSION — M1: Repository / skeleton

**Goal:** stand up the deployable Django skeleton so every later mission is a vertical slice on a green base. Foundation only — **no referral/redirect logic yet** (that is M2).

**Stack (LOCKED — ADR-024):** Django + Django Ninja + HTMX + Tailwind + PostgreSQL; **django-tenants** for the multi-tenant boundary (ADR-023). Django ORM + Django migrations (NOT SQLAlchemy/Alembic). No React/SPA.

**Build (per `implementation/10` §11 M1 + §2 Django layout):**
1. **Django project + apps:** `referrals`, `events`, `config`, `tenants`, `integrations` (empty adapter stubs), plus `templates/` + `static/` (Tailwind) scaffolding and a mounted **Django Ninja** `api/` router (may be empty).
2. **Config + feature-flag module** (§4): loaded from env at startup, ONE module, no scattered literals. Defaults: `ENABLE_CUSTOMER_LOGIN=false`, `ENABLE_WATI_SEND=false`, `ENABLE_ZOHO_WRITE=false`, `ENABLE_ASSET_GENERATOR=false`, `ENABLE_ADMIN_DASHBOARD=true`, `ENABLE_DEMO_MODE=true`, `REFERRAL_INCENTIVE_CLAIM="300 reward points + 10% brokerage share"`. Scaffold the **3-tier config cascade** central→global→user (ADR-022); user tier dormant behind `ENABLE_CUSTOMER_LOGIN`.
3. **Env-bootstrap admin** (§5): first admin from `ADMIN_EMAIL` + `ADMIN_PASSWORD_HASH` (or one-time token), idempotent, hashed — **no seeded plaintext**. Admin-only; customer login behind the flag.
4. **Migrations harness** (Django migrations, §8): initial migrations boot clean; forward-only discipline.
5. **Seed the single `ReferralProgram`** (Zerodha, partner code `ZMPHZC`, destination-URL template `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}`) via a **separate seed script** (not a schema migration). Provider-agnostic model — **no `Zerodha*`-named** files/tables/routes.
6. **`tenant_id` from day one** on tenant-scoped tables/models (ADR-023), even with one bootstrap tenant.
7. **CI:** runs an empty-but-green test suite (pytest/Django test) + lint; red blocks merge. Stub the test structure (incl. placeholders for the three M2+ guardrail tests).
8. **README + `.env.example`:** how to run locally (env, migrate, seed, runserver); `.env.example` lists every flag + secret NAME, no values.

**Guardrails (from `CLAUDE.md` — must hold):** provider-agnostic naming; no secrets inline (env/secret store; `.env.example` updated); a single phone-normalization helper (strip spaces/`+`/`()`/`-`, prefix `91`); `REFERRAL_INCENTIVE_CLAIM` as the single compliance claim field; nothing half-built reachable in prod; **no "Coming Soon" / dead UI**.

**Definition of Done (M1):** skeleton boots; migrations apply clean; `ReferralProgram` seeded; feature flags wired from config; env-bootstrap admin works idempotently; CI green; README + `.env.example` updated; PR `mission-1-skeleton` opened with a summary.

**When done:** append a `STATUS` entry below (what built / deferred / any inconsistency surfaced as a `QUESTION`) and open the PR. If you hit any spec ambiguity, log a `QUESTION` here and **pause on that point** — do not guess.
