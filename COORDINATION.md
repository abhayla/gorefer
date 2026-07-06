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

---

### 2026-07-06 — FROM ENGINEER — STATUS — M1: Repository / skeleton — DONE (PR `mission-1-skeleton`)

**Built (all M1 DoD items hold; skeleton boots, migrations apply clean, CI green):**

- **Django project + apps (LOCKED stack, ADR-024):** project `gorefer` + apps `referrals`, `events` (stub, models land M4), `config`, `tenants`, `integrations` (log-only adapter stubs behind the doc-08 contract). `templates/` (Django templates + Tailwind/HTMX via CDN for the skeleton) + `static/` scaffolding. **Django Ninja** API mounted at `/api/` with a `/api/health` probe (exposes no partner code / URL / internal id).
- **Config + feature-flag module (`gorefer/flags.py`):** ONE env-resolved snapshot, no scattered literals. Defaults exactly per brief (`ENABLE_CUSTOMER_LOGIN/WATI_SEND/ZOHO_WRITE/ASSET_GENERATOR=false`, `ENABLE_ADMIN_DASHBOARD/DEMO_MODE=true`, `REFERRAL_INCENTIVE_CLAIM="300 reward points + 10% brokerage share"` as the single swappable compliance claim). **3-tier config cascade** central→global→user (ADR-022) implemented in `apps/config` with a **compliance-lock** (lower tiers cannot weaken locked keys); **user tier dormant** behind `ENABLE_CUSTOMER_LOGIN`.
- **Env-bootstrap admin (`bootstrap_admin`):** first admin from `ADMIN_EMAIL` + `ADMIN_PASSWORD_HASH`, **hash-only, idempotent, refuses to seed any plaintext/default** (errors if no hash). Admin-only; customer login stays flagged off.
- **Migrations harness:** Django migrations, forward-only; initial migrations for `tenants`, `config`, `referrals` apply clean from an empty DB; `makemigrations --check` reports no drift (enforced in CI).
- **Seed (`seed_program`, separate script — NOT a schema migration):** idempotently seeds the bootstrap tenant (PIFS), central config baseline, `Partner` (code from `PARTNER_CODE`, default `ZMPHZC`), the single **`ReferralProgram`** (Zerodha = row #1), and its `ProgramRedirectRule` holding the **server-side** destination template `https://signup.zerodha.com/api/lead/?c={partner_code}&r={client_id}`. **Provider-agnostic** — no `Zerodha*`-named file/table/route/model.
- **`tenant_id` from day one (ADR-023):** `TenantScopedModel` mixin puts `tenant_id` on `partners`, `programs`, `program_redirect_rules`; per-tenant uniqueness (`uq_program_tenant_partner_name`). django-tenants `Tenant`/`Domain` present.
- **Guardrails honored:** provider-agnostic naming; no secrets inline (`.env.example` lists every flag + secret NAME, no values; `.env` gitignored); a single phone-normalization helper (`apps/common/phone.py`, strip spaces/`+`/`()`/`-`, prefix `91`); compliance footer (risk warning + NSE AP `AP2516003693`) auto-injected via context processor; **no "Coming Soon"/dead UI** (admin link only shows when its flag is on).
- **CI + tests:** GitHub Actions runs ruff + `manage.py check` + migration-drift check + pytest. **24 tests pass** (flags, phone, cascade compliance-lock, seed + admin idempotency, health/home smoke). The **three M2+ guardrail tests are scaffolded and SKIPPED** (redirect-never-POSTs, status-only-from-Zoho, no-partner-code-in-client-response) so they're visible and light up in the mission that adds each path.
- **Docs:** README "Running locally" section (env → migrate → seed → bootstrap → runserver, plus lint/test); repaired a corrupted sentence in the README intro.

**Deferred (correctly out of M1 scope):** all referral/redirect/journey/event logic (M2+); real WATI/Zoho HTTP adapters (M5/M6 — stubs are log-only now); the built Tailwind asset pipeline (CDN suffices for the skeleton; proper build lands with M3 UI); the domain models for `events`/CRM/analytics (M4/M6).

**QUESTION — Q-M1-1 (surfaced, non-blocking — I did NOT silently resolve it):**
The mission + ADR-024 name **`django-tenants` (schema-per-tenant)** as the multi-tenant path, but **05-Database-Design §2 (and the uniqueness constraints, e.g. `(tenant_id, program_id, client_id)`) specify a `tenant_id` discriminator column on every tenant-scoped table** — the *single-schema* model. These are two different physical isolation strategies and are in tension: pure schema-per-tenant doesn't need a `tenant_id` column within a tenant schema, while the discriminator model doesn't need separate schemas. ADR-024 (line ~269) itself says to *"decide at multi-tenant-enable time; keep tenant vs shared apps separated early, start with one bootstrap tenant."*
  - **What I did (reversible, doesn't foreclose either choice):** installed `django-tenants` **and** carried the `tenant_id` discriminator columns; separated SHARED vs TENANT apps; started with one bootstrap tenant (PIFS). django-tenants **schema routing is active only when `DB_ENGINE=postgres`**; the SQLite dev/CI path loads the same apps without the router so M1 boots and CI stays green with **no external database**. Both strategies remain open.
  - **Decision needed from DA (before it becomes load-bearing — M2 writes the first tenant-scoped journey/event rows):** at multi-tenant-enable time, is the boundary **(a)** schema-per-tenant via django-tenants (then `tenant_id` columns become redundant belt-and-suspenders), or **(b)** single-schema `tenant_id` discriminator (then django-tenants is only the app/domain registry, not the router)? **Recommendation: (b) single-schema `tenant_id` discriminator** — it matches the DB design as written, is simpler to operate/back up/query for a solo builder at Sprint-1 scale (~4 req/s), and django-tenants can still provide the tenant/domain registry. This is **not blocking M1**; flagging so M2's first tenant-scoped writes are built against the intended model. **Pausing on this specific point only** — the rest of M1 proceeded on the reversible middle path above.
