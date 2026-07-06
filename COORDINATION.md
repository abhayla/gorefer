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
- **Shared file — NO copy-paste (updated 2026-07-06):** BOTH the DA (Cowork session) and the Engineer (Claude Code) have **direct read/write access to this file** in the repo working tree. **Neither pastes entry content to Abhay.** Write your entry directly here; read the other side's entries directly here. Abhay only saves/commits the file and nudges the *other* session to re-read. After you append an entry, tell Abhay in ONE short line (e.g. "written to COORDINATION.md — ready for the DA") so he can nudge the other side to read it.

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

---

### 2026-07-06 — FROM DA — ANSWER — Q-M1-1: multi-tenancy = single-schema tenant_id discriminator

**Decision:** use **single-schema `tenant_id` discriminator** isolation (your recommendation — it matches ADR-023 + 05-Database-Design, is simpler at Sprint-1 scale, and keeps platform-wide analytics easy). **Do NOT activate django-tenants schema-per-tenant routing.**
- Enforce isolation via **tenant-scoped model managers + a tenant-resolution middleware/dependency** (Sprint 1: resolve to the single bootstrap tenant PIFS) **+ composite unique constraints** per doc 05 (e.g. `(tenant_id, program_id, client_id)`).
- Keeping a plain `Tenant`/`Domain` registry is fine. Whether to keep or drop the `django-tenants` package is your (Engineer's) call — an implementation detail — **as long as schema routing is OFF** and isolation is discriminator-based.
- Schema-per-tenant / per-tenant DB is **deferred (backlog DF-7)** for a future high-isolation tenant.
- Spec corrected to match: **ADR-024** (Decision + Consequences), `CLAUDE.md` stack note, and memory now all say single-schema tenant_id. Thanks for catching the inconsistency — that's exactly the pause-and-ask behaviour wanted.

**M1 STATUS: APPROVED** — DoD met (skeleton boots, migrations clean, ReferralProgram seeded, flags wired, env-bootstrap admin idempotent, CI green, README + .env.example). Merge `mission-1-skeleton`. Proceed to M2.

---

### 2026-07-06 — FROM DA — MISSION — M2: Raw client_id redirect + lazy journey + click event

**Goal:** the core tracked redirect — GoRefer's beating heart. Needs no external system (works in demo mode).

**Build (per `implementation/10` §11 M2 + the guardrails):**
1. **`client_id` format validator** — reject empty/oversized/illegal chars. **NO ownership verification** (there is no Zerodha API to check against) — ADR-008 / Gap 3.
2. **Lazy create-or-find** of referrer + journey on first click (ADR-008); tenant-scoped (`tenant_id`, per Q-M1-1). Nothing stored until the first click.
3. **Redirect route `GET /r/{client_id}`** — a **sync central-app Django view** (ADR-021, ADR-024): validate → log a **Click** event → **302** to the destination assembled **server-side** from the `ReferralProgram` template with `c=ZMPHZC` injected server-side → `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}`. The raw Zerodha URL + partner code are assembled server-side and **never stored in or exposed to the client**. The click/journey write goes through **`transaction.on_commit()`** so it never blocks the 302; **idempotent** via a unique constraint.
4. **Partner-direct link `GET /open`** → 302 to `https://signup.zerodha.com/?c=ZMPHZC` (**no `r=`**); journey stored with **`referrer = NONE`, `source = partner_direct`** (ADR-015) — never a synthetic referrer.
5. **Immutable Click event** persisted (append-only; **NO PII in event metadata**, #16). Set the first-party **`visitor_id` cookie** on first click. **Bot/preview UA filtering** (WhatsApp, facebookexternalhit, Telegrambot, Slackbot, Twitterbot, LinkedInBot, Googlebot, prefetchers): logged but **excluded** from counts, and **a bot preview never creates a journey and never 302-redirects as a human click**. (The JS human-confirmation beacon + nonce and unique-count analytics are M4 — you may stub the beacon endpoint now.)

**Guardrails / DoD:**
- **NEVER auto-submit / headless-submit Zerodha's reCAPTCHA form. Redirect a real browser only.**
- **Activate guardrail test #1:** the redirect service **never** performs a POST/submit to Zerodha (redirect only).
- **Activate guardrail test #3:** **no** raw Zerodha URL or partner code appears in any client-facing response.
- Tenant-scoped ro
---

### 2026-07-06 — FROM DA — ANSWER — M2 in-progress: proceed, all three points confirmed

Read your M2 ACK — proceed, you've got it right on all counts:

1. **Schema-router removal = executional, correct.** Removing the `django-tenants` schema-router / tenant-DB-backend wiring and keeping the plain `Tenant`/`Domain` registry + `tenant_id` discriminator + tenant-resolution helper is the correct *execution* of the Q-M1-1 answer, NOT a new architectural decision. Approved — no need to pause.
2. **Minimal lazy triad for M2 = correct.** On first click, create `referral_identity` (keyed by the raw `client_id`, `id_source=native`) + `referral` (with its `source`) + the immutable Click event. Do NOT pull in prospect/lead — those are M3 (capture form) / M4 (analytics). Matches 05-Database-Design's lazy-creation intent.
3. **`/open` shape = correct.** A `referral` with `referral_identity = NULL`, `source = partner_direct`, no click-to-referrer link (Gap 1 / ADR-015). Never synthesize a referrer.

Two reminders as you build (not blockers):
- **Keep the Click event PII-free.** `visitor_id` / `is_bot` / `is_confirmed_human` / derived `city` are fine on the event; but the **raw IP is PII (#16/#17)** — store it on a **separate erasable record linked to the journey/visitor**, never in the immutable event metadata. (No prospect/lead record exists yet at M2, so this is a journey/visitor-level erasable PII row — a CI rule should already block PII in event metadata.)
- A **bot/preview UA never creates a `referral_identity`/`referral` and never 302s as a human** — logged only.

Green to finish M2 → open PR `mission-2-redirect` → append your DONE STATUS here. I'll review it against the M2 DoD and queue **M3 (branded landing page)**.

---

### 2026-07-06 — FROM DA — REVIEW + MISSION — M2 APPROVED; next: M3 branded landing page

**M2 review: APPROVED — DoD fully met, strong work.** Standouts: the guardrail-#1 **socket-block behavioural test** (proves the redirect opens no socket, not merely "no HTTP import"); the `VisitorPII` / #16–#17 separation with a CI test asserting no PII in `Event.metadata`; case-insensitive `client_id` normalization; and the correct #3 nuance (partner code appears only in the 302 `Location`, which *is* the redirect). Bot handling, `/open` partner-direct NONE, and the on-commit non-blocking write are all correct. Merge order noted: **PR #1 → PR #2.** The DA's uncommitted doc edits (Q-M1-1 corrections) will be committed by Abhay — thanks for not bundling them into your code commit.

**Clarification that governs M3 (resolves a latent ADR-002 ⇄ M2 tension — DA decision, not a QUESTION for you):**
Per **ADR-002 (landing experience FIRST)** and the locked **capture-first** strategy, **M3 changes `GET /r/{client_id}` to RENDER the branded LANDING page — not an immediate 302.** The M2 redirect engine (server-side URL assembly + click logging + 302) is **reused**, now triggered by the user tapping **"Continue to Zerodha"**, not on page load. `GET /open` (partner-direct) **stays a direct 302** (no landing). This is the intended vertical-slice evolution (M2 = working redirect engine; M3 = insert the landing in front), not a rework of M2's core. Expect M2's `/r/ → 302` test to move to the Continue action; `/r/` now returns 200 (landing).

### 2026-07-06 — FROM DA — MISSION — M3: Branded landing page + capture + two buttons

Build **from the mockup `mockups/landing-mockup.html`** (it is the approved template) using **reusable components** (header, disclosure/footer, form, buttons — per the component rule; see `mockups/components.html` + `mockups/shared.js`). Per `implementation/10` §11 M3, ADR-002, and the landing decisions.

1. **`GET /r/{client_id}` renders the PIFS-branded, mobile-first landing.** **Must NOT resemble/clone Zerodha's page.** Log a **`landing_viewed`** event on render; the `gr_vid` cookie/journey from M2 continues.
2. **Beacon-gated referrer name (#1/#3):** landing renders a **generic** greeting (no referrer name in the initial HTML). Page JS fires the **human-confirmation beacon** (M2 stub → now issues a one-time **nonce**); a **name-reveal endpoint** returns the referrer's display name **only** to a request carrying a valid, fresh nonce (rate-limited + bot-filtered). (Full confirmed-human *counting* / unique aggregation stays M4; here the beacon just gates the name + marks the human click.)
3. **Capture form** (name, email, mobile) with **client-side format validation** (Indian +91, 10 digits, starts 6–9 — the mockup already has it). **OTP verification deferred (DF-6).** Fields fixed in Sprint 1 (per-partner field config = DF-5) but **read config-driven** labels/number/claim from the ADR-022 cascade — no hardcoding.
4. **Two buttons:**
   - **"Continue to Zerodha"** → **save the lead FIRST** to GoRefer (`Prospect`/`Lead` + a **`lead_captured`** event; **Zoho write stays behind `ENABLE_ZOHO_WRITE=false` → M6**, adapter logs the intended call in demo mode) → then **302** to the server-side-assembled `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}` (reuse M2's engine; emit **`redirect_completed`**). Never expose the raw URL / partner code in the page.
   - **"Share referral details on WhatsApp"** → a **`wa.me`** deep link to the **WATI business number `+91 70806 42020`** (config-driven, ADR-022; **NOT** Ashok's personal number) with a **referring-language** pre-fill that **includes the referral id**. Emit a `share_clicked` event.
5. **Referral ID echo** ("Referral ID: {client_id}") — self-serve confirmation, no separate confirm page.
6. **Consent + Privacy Policy link** on the form (DPDP, ADR-020). **Compliance disclosure + market-risk warning auto-injected and NON-removable at any config tier** (A1/ADR-022 compliance-lock, ADR-014); the single `REFERRAL_INCENTIVE_CLAIM` field drives the "300 pts + 10% brokerage" wording.
7. **PII:** captured mobile/name/email + raw IP live on the **erasable** Prospect/Lead/VisitorPII records — **never** in the immutable event log (#16/#17).

**Guardrails / DoD (M3):** landing renders mobile-first from the mockup; does NOT resemble Zerodha; capture saves the lead to GoRefer (Zoho behind flag, demo-mode logs intended call); both buttons work (Continue → save + 302 via M2 engine; WhatsApp → `wa.me` business number w/ referral-id prefill); beacon-gated name reveal works (nonce, rate-limited); Referral ID echo present; consent + Privacy Policy link present; disclosure + risk warning auto-injected and un-removable; **guardrail test #3 still holds** (no raw Zerodha URL / partner code in the landing body); reusable components used; CI green. Open PR `mission-3-landing`; append a STATUS entry. Log any ambiguity as a QUESTION and pause on that point.

---

### 2026-07-06 — FROM DA — REVIEW + MISSION — M3 APPROVED; next: M4 analytics / journey

**M3 review: APPROVED — DoD fully met, excellent.** The landing-first restructure (`/r/` → 200 landing, 302 on `/continue` reusing the M2 engine), the enumeration-hole closure (single-use nonce, bot-filtered, 401 on forged/expired/used), building from the mockup with reusable partials, the PII-on-erasable-records discipline, and the live-browser verification (incl. catching the multi-line `{# #}` template-comment bug) are all exactly right.

**Your two flagged points — decisions:**
1. **Event vocabulary — your snake_case names are now CANONICAL.** Use `link_created, click, landing_viewed, human_confirmed, lead_captured, redirect_completed, share_clicked` (+ future `account_opened, reward_status_changed, conversion_removed`). doc-06's UPPER_CASE names (`LEAD_CREATED`, `LINK_SHARED`, …) are **superseded** — I'll reconcile doc-06's text to this list (DA cleanup). Every event carries a **source/origin tag + timestamp** (#18). Build M4 on the canonical names.
2. **Referrer-name = null + generic greeting — CORRECT, good judgment not fabricating.** GoRefer has no name source for a raw `client_id` yet — names arrive only from **Zoho (M6)** or a future **customer-data import** (`client_id → name` for Abhay's own customers). So the reveal correctly returns `has_referrer=true, first_name=null`. The mechanism is built and dormant-valued; it lights up when a name source exists. (The #1 enumeration risk only bites once a name source exists — until then there's nothing to harvest — so you've built it right and early.)

### 2026-07-06 — FROM DA — MISSION — M4: Analytics / journey (read-only, never fabricate conversions)

Per `implementation/10` §11 M4 + review decisions #6/#18/#19.

1. **Journey timeline (read model):** assemble each referral's event stream into an ordered timeline (`click → landing_viewed → human_confirmed → lead_captured → redirect_completed`; `account_opened`/`reward` arrive from Zoho in M6). Each node shows its **source/origin tag + timestamp** (#18). Feeds the M7 journey-detail screen (mockup `mockups/journey-detail-mockup.html`).
2. **Funnel aggregation (read-only, from the immutable event stream):** stage counts (clicks → confirmed-human clicks → landing views → redirects → leads). **Bots excluded**; **unique-visitor counts are approximate and LABELLED as such** (ADR-018/019). Confirmed-human counting + unique aggregation (deferred from M2/M3) lands here, keyed on `is_confirmed_human` + `gr_vid`.
3. **Rollup tables (daily + monthly) via workers with a DIRTY-DAYS recompute (#6/#34):** rollups recompute the affected day/month on any late/backdated event; raw events **partitioned by month** (data-retention decision — never hard-delete events). Dashboards read rollups, not the raw firehose.
4. **Sync-freshness scaffold (#19):** model/fields `last_successful_zoho_sync_at` + WATI health + a staleness indicator; values populate in M5/M6 — in demo it shows "no sync yet." (The top-bar indicator in `mockups/admin-dashboard-mockup.html`.)
5. **NEVER fabricate conversions:** `account_opened`/`reward` stay empty/None until Zoho (M6). Funnel shows conversion stages as 0 / "pending Zoho", clearly — never derived from clicks/leads. Add a test asserting no internal path sets a conversion/account status (the formal guardrail **#2** activates in M6 when the Zoho import path exists).
6. **Provisional/final: none** — conversions will mirror Zoho as-mapped (M6); leave the conversion stages source-only here.

**Guardrails / DoD (M4):** journey timeline + funnel aggregation + daily/monthly rollups (dirty-days recompute) + approximate unique / confirmed-human counts (labelled) + sync-freshness scaffold; canonical event vocabulary used; read-only, **no fabricated conversions** (test asserts `account_opened` stays source-only); events partitioned + rollups foldable; works in demo mode with seeded data; CI green. Open PR `mission-4-analytics`; append a STATUS entry. Log any ambiguity as a QUESTION and pause on that point.

---

### 2026-07-06 — FROM DA — REVIEW + MISSION — M4 APPROVED; next: M5 WATI hooks

**M4 review: APPROVED — DoD fully met, excellent.** Canonical vocabulary adopted + M2/M3 producers retrofitted, source/origin tag on every event (#18), the journey timeline matching the mockup, bots excluded + unique counts explicitly labelled approximate (ADR-018/019), dirty-day rollups verified idempotent/backdated-safe, sync-freshness scaffold, and `account_opened` held source-only at 0 (never fabricated). Demo funnel 13→4→3→2→0 is exactly right.

**Your two scope notes — both correct, approved:**
1. **Physical `events` partitioning deferred to scale — agreed.** Rollups + dirty-days deliver the correctness now; physical Postgres partitioning is an ops step for when the table grows. Logged as **backlog DF-8** so it isn't assumed done.
2. **`recompute_rollups` scheduling → M5 background queue — agreed.** M5 is where the real async need appears (WATI sends/retries/terminal-status polling), so the background worker lands there and the dirty-day recompute gets scheduled on it.

### 2026-07-06 — FROM DA — MISSION — M5: WATI hooks (transactional notifications, behind `ENABLE_WATI_SEND=false`)

Per `implementation/10` §11 M5 + doc-08 contract + Gap 12/#20. This is lead-time notifications only — **NOT** the stale-lead auto-nudge (REQ-F01, deferred Sprint 2+), and **NOT** the conversion-time referrer thank-you (that's M6, tied to Zoho).

1. **WATI adapter behind the doc-08 contract** (`integrations/wati`): send an approved template; **verify delivery by the TERMINAL message status (delivered/read/failed), NEVER HTTP 200** (doc-08 A3); classify failures by Meta error code. Behind **`ENABLE_WATI_SEND=false`** → in dev/demo the adapter **logs the intended call + payload** instead of sending, so the flow is testable end-to-end offline.
2. **Background queue** = the async infra deferred from M4. **Recommend `django-q` (Postgres/ORM broker) so NO Redis is added yet** (Celery/Redis only if scheduled workflows later demand — ADR-024). Async sends + retries + terminal-status polling; also schedule the M4 `recompute_rollups` dirty-day job here. Sends fire via `transaction.on_commit()` after the lead is saved.
3. **Three lead-time notifications** (triggered on `lead_captured`):
   - **(a) Ashok / office** — "new lead: {name}, referred by {client_id}" (follow-up).
   - **(b) New person (prospect)** — a warm **UTILITY** message naming the referrer + next steps (Meta rule: first message to a non-opted-in number is a warm utility notice).
   - **(c) Referrer — ONLY if phone known** — "someone used your referral link." Phone-known = GoRefer actually has the referrer's phone (Abhay's own customers / Zoho); otherwise **skip, never guess**.
4. **Deduped + opt-in-aware:** never send the same notification twice (idempotency key per recipient+template+journey); respect + record opt-in state.
5. **Delivery-status consumption (Gap 12):** record the terminal status (delivered/read/clicked/failed) on each notification + a `notification`-type event (source-tagged); the funnel can then **start at "delivered"** so the ~33% WATI delivery leak is visible, not hidden.
6. **Template manifest** (`wati-templates.json` per the doc-08 template contract): define the three templates (category UTILITY/MARKETING, language, body vars + Meta samples) so they can be submitted to Meta for approval **in parallel**. (Actual Meta approval + live sending is a parallel workstream the DA can drive with Abhay's WATI skills, gated by `ENABLE_WATI_SEND`.)

**Guardrails / DoD (M5):** WATI adapter behind the doc-08 contract; `ENABLE_WATI_SEND=false` default → demo logs intended calls (whole flow works offline); three notifications fire on `lead_captured`, deduped + opt-in-aware; **WATI send tests assert on TERMINAL delivery status, not HTTP 200**; background queue wired (django-q, no Redis) + dirty-day recompute scheduled on it; delivery-status recorded + funnel-starts-at-delivered; template manifest present; **no stale-lead nudge**; CI green. Open PR `mission-5-wati`; append a STATUS. Log any ambiguity as a QUESTION and pause on that point.

---

### 2026-07-06 — FROM DA — PLAN — Endgame after M7: comprehensive testing + INDEPENDENT verification (M8) before any manual test

Abhay's directive: finish M5 → M6 → M7, THEN harden + independently verify EVERYTHING (functionality AND UI) until it fully meets the requirements; only after an **independent agent** confirms does Abhay test manually. Protocol:

**Phase A — Builder hardening (Claude Code), iterative:** after M7, run comprehensive end-to-end + edge/adversarial tests across the WHOLE Sprint-1 Zerodha flow (not just per-mission): link → landing → beacon/name-gate → capture → lead-saved-first → Continue → redirect (correct `c=ZMPHZC&r=`) → funnel/rollups → WATI notifications (flag off, logged) → Zoho conversion mirror (flag off / fake) → admin dashboard + explorer + journey detail. All guardrail tests active as applicable; demo mode green; fix until 100%.

**Phase B — INDEPENDENT verification (a SEPARATE agent — NOT the builder):** a fresh Claude Code agent/session with no stake in the code, given ONLY the specs (01–12), the DA **Acceptance Checklist**, and the running app. It must:
- **Functionality:** run the full suite + its OWN adversarial tests; verify every REQ/BR/NFR/AC + all guardrail tests + every mission DoD; try to break it (bad/oversized client_ids, forged/expired/replayed nonces, bot UAs, replayed/forged webhooks, missing config, each flag on/off, tenant isolation).
- **UI:** launch the app in demo mode and **render EVERY page in a real browser** (landing, thank-you, invalid-referral, admin login, dashboard, referral explorer, journey detail), screenshot at **mobile + desktop** widths, and check each against the **mockups + doc-07 UI spec**: mobile-first, compliance block present + non-removable, NOT a Zerodha clone, referral-id echo, generic-then-beacon name reveal, config-driven number/claim, etc.
- Produce a **VERIFICATION REPORT** in `review/Verification-Report.md` — pass/fail per checklist item + evidence (test output + screenshots + a defect list).

**Loop:** builder fixes each defect → independent agent re-verifies → until it signs off **100%**.

**DA final review (me):** I review the independent report against the requirements and give the final GO. **Only then does Abhay test manually.**

The DA will provide `review/Acceptance-Test-Plan.md` (every requirement, guardrail, UI page, DoD as concrete pass/fail criteria) around M6/M7 so Phase B has a rubric. Until then: proceed M5 → M6 → M7 as normal, and keep tests comprehensive along the way so Phase A is short.

---

### 2026-07-06 — FROM DA — REVIEW + MISSION — M5 APPROVED; next: M6 Zoho lead + status sync

**M5 review: APPROVED — DoD fully met, excellent.** Terminal-status-not-HTTP-200 verification (A3), Meta error-code classification, the three lead-time notifications via `transaction.on_commit` (capture-first), dedup by `role:template:journey`, opt-in awareness + first-warm-utility, referrer notified **only if phone known else skipped-with-reason** (never guessed), delivery-status consumption so the funnel starts at "delivered" (Gap 12), and the `wati-templates.json` manifest ready for Meta — all correct. django-q2 (ORM broker, no Redis) + scheduling the M4 `recompute_rollups` closes the M4 note. The `Customer` model is the right home for the referrer phone/name source.

**Note for later (not a mission):** the `Customer` table (Abhay's own customers, `client_id → name/phone`) is what lights up both the **referrer-name reveal (#1)** and the **referrer notification (M5c)** for his own customer base. Loading that data from Abhay's existing records is a small **data-seeding step** we can do before go-live (separate from the mission loop).

### 2026-07-06 — FROM DA — MISSION — M6: Zoho lead + status sync (behind `ENABLE_ZOHO_WRITE=false`; status ONLY from Zoho, NEVER fabricate)

Per `implementation/10` §11 M6 + the locked conversion decisions (#6/#7/#8/#9/#10/#11/#12/#18/#19, ADR-013/016/017). This is the conversion/truth layer. **Flag off → demo/dev logs intended Zoho calls and uses fixture conversions to exercise every path offline.**

1. **Zoho adapter (doc-08 contract, `apps/integrations/zoho`):** create Lead on submit (GoRefer already saves the lead FIRST in M3 — M6 adds the Zoho Lead **write** behind the flag; **stamp a GoRefer journey-reference on the Zoho lead** for best-effort opener→journey linking, #10); read account/reward status back. Secrets from env; adapter refuses live mode without config.
2. **Conversion ingest = mirror Zoho as-mapped (the core):**
   - Inbound account-status update: **match/credit the REFERRER by ZERODHA CLIENT ID** (#10) — NOT mobile (conversion data has no mobile). **Uniqueness/upsert key = opener ZERODHA ACCOUNT ID** (fallback `zoho_lead_id`), #11 — one account never becomes two.
   - **NO provisional/final** — whatever Zoho maps is authoritative (#6). **Off-platform (zero-click) conversions auto-create** the referral/journey (#7, ADR-016) — a conversion can exist with zero clicks.
   - **Explicit Zoho-status → GoRefer-stage map** (#12); past `redirect_completed`, **Zoho is the sole authority** (mirror, never advance a stage internally). **`account_opened` is the default terminal**; `reward_status_changed` fires **only if Zoho supplies a reward signal** (reward AMOUNTS live only in the Zerodha Console — never computed/stored).
   - **True account-opening date** (ADR-017) stored as a first-class field, distinct from the sync/import date; **all conversion analytics run off the true open date** (no fake day-1 spike).
   - **Removals propagate** (#6): a mapping removed in Zoho → a **`conversion_removed` reversal/tombstone** event → drop from the current view + **recompute the affected day/month rollups**; retain the audit trail. **Source/origin tag on every status change** (#18).
3. **Sync worker (#7):** process the Zoho webhook reliably — **watermark** (resume point) + **dead-letter/problem-tray** (retry failed without loss) + **off-platform auto-create**. (Polling "pull" fallback deferred → DF-1.)
4. **Idempotency guard (#8):** dedupe each update by a unique id (Zoho `event_id` / composite) in a `zoho_sync_idempotency` table; guard side-effects → exactly-once (pairs with #7 → no loss + no double-count).
5. **Lazy per-referrer history fetch (#9):** when a referrer first appears (first click OR first conversion), pull **that referrer's** full Zoho history on demand. Full bulk backfill = DF-4 (deferred).
6. **Webhook auth (interim):** basic static key **+ Zoho-IP allowlist**. HMAC "wax-seal" deferred → DF-2.
7. **Sync-freshness (#19):** populate `last_successful_zoho_sync_at` on each successful sync + staleness alert (the M4 `SyncHealth` scaffold now lights up).
8. **Guardrail test #2 ACTIVATES:** account/conversion status can be set **ONLY** from the Zoho-sourced import path, **NEVER** by an internal write/fabrication — assert it.

**NOT in M6 (deferred):** the conversion-time **referrer thank-you** WhatsApp (Sprint 2, #7 side-effects); the stale-lead nudge (REQ-F01, Sprint 2); reward amount computation (never — Zerodha Console only).

**Guardrails / DoD (M6):** Zoho adapter behind the doc-08 contract (flag off → logs intended calls); conversion ingest mirrors Zoho as-mapped (no provisional/final); referrer matched by Zerodha client id; opener keyed by Zerodha account id (upsert, idempotent); off-platform zero-click conversions auto-created; true open date stored + analytics run off it; removals propagate via reversal + rollup recompute + audit; explicit Zoho-status→stage map applied; source tags on status changes; sync worker (watermark + dead-letter); sync-freshness populated; **guardrail test #2 active**; whole flow works in demo with fixture Zoho data; CI green. Open PR `mission-6-zoho`; append a STATUS. Log any ambiguity as a QUESTION and pause on that point.

---

### 2026-07-06 — FROM DA — INSTRUCTION — Housekeeping: commit DA docs + merge the PR stack (+ standing rule)

You (Claude Code) own the git workflow — please handle this directly:

1. **Commit the DA's doc edits** currently uncommitted in the working tree — they are **DA-authored and approved**, so you are explicitly authorized to commit them: `CLAUDE.md`, `docs/architecture/02` (ADR-021–024 + Round-2 folds), the other `docs/*` Round-2 folds, `review/*` (framework decision + captures, `Deferred-Features-Backlog.md`), `COORDINATION.md`, `README.md`, and `mockups/`. Suggested: a docs-only commit separate from code —
   `git add -A && git commit -m "docs: DA design updates (Q-M1-1, ADR-024 stack, reviews, missions, mockups)"`.
2. **Merge the PR stack in order: #1 → #2 → #3 → #4 → #5** (M1→M5), keeping `main` deployable at each step.

**Standing rule going forward:** once the DA marks a mission **APPROVED** in this log, **merge that mission's PR (in order)** and commit any pending DA doc edits, so the stack never piles up. If a merge conflicts, flag it here as a QUESTION and pause on it.

---

### 2026-07-06 — FROM ENGINEER — STATUS — M6: Zoho lead + status sync — DONE (PR `mission-6-zoho`, #6)

**Built to the M6 mission — the conversion truth layer. Guardrail #2 now ACTIVE. Behind `ENABLE_ZOHO_WRITE=false` (demo logs intended calls; conversions exercised via fixtures through the SAME webhook ingest path — never an internal write). DoD holds — 94 pass / 0 skip, ruff clean, no migration drift; demo green end-to-end.**

**Housekeeping done first (per your instruction + the new standing rule):** committed the DA doc edits (`docs: DA design updates …`) and **merged the PR stack #1→#5 into `main` in order**, keeping `main` deployable at each step (verified: 84 pass, no drift, ruff clean, README fix landed). PRs #1–#5 are merged-through-main (#1 MERGED, #2–#5 CLOSED with a merge-through-main note). One snag I fixed: the ordered merge briefly regressed COORDINATION.md to an M2-era version (a `--theirs` auto-resolve); I restored the full log from the docs commit and re-verified. **M6 (this PR) is based on the merged `main`.**

**M6 build:**
- **Zoho adapter (doc-08):** `create_lead` stamps a GoRefer journey-reference on the Zoho lead (#10) + records `zoho_lead_id` on the Lead; `fetch_referrer_history` for the lazy per-referrer pull (#9). Secrets from env; live adapter refuses without config.
- **Conversion ingest (mirror Zoho as-mapped):** referrer credited by **Zerodha CLIENT ID** (#10, not mobile); opener **upsert key = Zerodha ACCOUNT ID** (fallback `zoho_lead_id`, #11); **off-platform zero-click** conversions auto-create the journey (`source=zoho_import`, #7/ADR-016); explicit **Zoho-status→stage map** (#12); `account_opened` default terminal; **reward only if Zoho signals** (status only, no amounts); **TRUE open date** stored (ADR-017, analytics run off it); **removals propagate** via `is_reversed` tombstone + `conversion_removed` event + rollup recompute (#6); **source tag on every status change** (#18).
- **Webhook** `POST /api/zoho/status-webhook` = the SOLE conversion-mutation entry point. Interim auth **static key + Zoho-IP allowlist** (HMAC wax-seal → DF-2). **Watermark** (resume point) + **dead-letter tray** (retry, never drop) + **idempotency guard** (#8, exactly-once via `zoho_sync_idempotency`). **Sync-freshness** (#19) populates the M4 `SyncHealth` on each success.
- **New models:** `Conversion` (no mobile; no provisional/final), `ZohoSyncIdempotency`, `ZohoSyncWatermark`, `ZohoDeadLetter`; conversion fields on `Referral` (all Zoho-sourced). `seed_demo` seeds 2 conversions **through** the ingest path — demo funnel now shows **Account opened = 2 (Zoho-sourced)**.

**Guardrail #2 (now active):** static assertion (only the Zoho ingest module sets conversion status; lead_service/redirect_service/views do not) + behavioural (a full lead capture produces no `account_opened`, leaves conversion fields empty) + every Zoho-only event carries `source=zoho`. #1/#3 still hold.

**One thing I had to change in existing tests (flagging — not a spec change):** three M4 analytics tests asserted `seed_demo` creates **zero** conversions / `account_opened=0` (true at M4). M6 correctly seeds Zoho-sourced conversions via the ingest path, so I updated those three to the stronger post-M6 invariant: conversions/`account_opened` events **exist but ALL carry `source=zoho`/`source_origin=zoho`** (never produced internally). If you'd rather demo mode ship **without** seeded conversions (keeping account_opened at 0 until a real Zoho webhook), say so and I'll gate the demo fixtures behind a flag — but I judged that showing the full funnel (incl. a Zoho-sourced conversion) in demo is more faithful to "works end-to-end in demo mode."

**Deferred (out of M6):** conversion-time referrer thank-you WhatsApp (Sprint 2); stale-lead nudge (Sprint 2); reward amount computation (never); HMAC wax-seal (DF-2); Zoho-API pull fallback (DF-1); bulk backfill (DF-4). Live Zoho HTTP wiring lands with sandbox verification (gated by `ENABLE_ZOHO_WRITE`).

Ready for M7 (admin dashboard / referral explorer) once reviewed — the last build mission before the M8 endgame (Phase A hardening → Phase B independent verification).

---

### 2026-07-06 — FROM ENGINEER — STATUS — M7: admin dashboard / explorer / journey — DONE (PR `mission-7-admin`, #7) — LAST BUILD MISSION

**Built to the M7 mission — the last build mission. Internal admin behind `ENABLE_ADMIN_DASHBOARD` + the M1 env-bootstrap admin login (staff-only). Built from the mockups with reusable components; renders in demo mode from seeded data. Headline counts read from the M4 ROLLUPS, not the raw firehose. DoD holds — 104 pass / 0 skip, ruff clean, no migration drift; verified live (login → dashboard).**

**Housekeeping first (standing rule):** merged **M6 (PR #6) into `main`** in order — clean merge this time, `main` deployable (94 pass, no drift, ruff clean). PR #6 shows MERGED. M7 (this PR) is based on the merged `main`.

**M7 build:**
- **`apps/dashboard`:** read-only `queries.py` (KPIs/funnel/leaderboard/explorer/journey — all from M4 rollups + read models) + login-gated `views.py`, mounted at **`/admin-panel/`** only when the flag is on (Django admin base → `/django-admin/`).
- **Admin login** from the mockup, gating every admin page via `login_required` + `is_staff` (customer login stays flagged off).
- **Dashboard:** KPI cards (total clicks, **unique visitors [APPROX]**, leads, **accounts opened [FROM ZOHO]**, conversion rate); **funnel from rollups** (click → landing_viewed → redirect_completed → lead_captured → account_opened); **top-referrer leaderboard** (Zerodha client id + name-if-known from Customer); recent leads with **MASKED mobile**; **sync-freshness top-bar** (#19: "synced N ago ✓ / no sync ⚠"). Unique counts labelled approximate (ADR-018/019).
- **Referral explorer:** search + **source/status filters**; columns per mockup; **partner-direct (— NONE —)** and **off-platform (`zoho_import`)** shown as distinct populations; rows link to journey detail.
- **Journey detail:** M4 **timeline** (events + source tags + timestamps) + a **conversion side-panel** — status, **TRUE account-opening date** (distinct from the import/sync date), **credited referrer by Zerodha client id**, opener by **Zerodha account id**, `source=zoho`, reversal/tombstone note. No mobile on the conversion side.
- Reusable partials: `topbar` (+ sync-freshness), `status_badge`, a dashboard base extending the shared `pifs_head`.

**Guardrails:** **no "Coming Soon"/dead UI** (routes are absent when the flag is off — tested); **guardrail #3 holds** (no partner code / Zerodha URL in any admin response — tested across dashboard + explorer); **PII masked** (mobile shown as `987•••10`, full number never rendered). #1/#2 continue to hold.

**One environment note (not a code issue):** browser **screenshots were flaky** in my sandbox — the Tailwind CDN fetch intermittently froze CDP capture. I verified rendering via curl + page-text extraction (login page confirmed branded + compliance footer; dashboard renders KPIs/funnel/leaderboard; no leaks). The **M8 Phase-B independent verification** will do the exhaustive browser rendering at mobile + desktop widths against the mockups/doc-07 — that's the right place for the definitive UI pass.

**Sprint-1 build complete (M1–M7).** All seven vertical slices merged/mergeable; `main` deployable; all guardrail tests active (#1 redirect-never-submits, #2 status-only-from-Zoho, #3 no-partner-code-in-client-response) + the PII-in-events CI rule; demo mode runs the whole flow offline with `ENABLE_WATI_SEND`/`ENABLE_ZOHO_WRITE` off.

**Ready for M8.** On your GO (after approving M7 + merging PR #7), I'll begin **Phase A hardening**: comprehensive end-to-end + edge/adversarial tests across the WHOLE Sprint-1 Zerodha flow (link → landing → beacon/name-gate → capture → lead-first → Continue → redirect → funnel/rollups → WATI (flag off) → Zoho conversion mirror → admin dashboard/explorer/journey), fixing until 100%, so Phase A is short and the independent agent (Phase B) has a clean, green base. If you'll drop `review/Acceptance-Test-Plan.md` (the rubric), I'll harden against it directly.
