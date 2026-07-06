# 10 — Claude Code Implementation Guide (GoRefer · Sprint 1: Foundation)

> **What this is.** The operating manual for **Claude Code** implementing **Sprint 1 — GoRefer Foundation**: the complete referral flow end-to-end (customer → referral link → share → friend opens the branded form → analytics recorded → redirect to Zerodha). It defines the tech direction, repo structure, coding standards, testing, git workflow, migrations, the Definition of Done, demo mode, the build order, and the guardrails Claude Code must never cross.
>
> **Authority.** The spec set (docs 01–09) is **authoritative**. This guide tells Claude Code HOW to build, not WHAT to build differently. **Do not change the architecture. Report inconsistencies; do not invent solutions to them.**
>
> **Compiled:** 2026-07-04 (Cowork session). **Owner:** Abhay Kumar Maurya (PIFS, Zerodha Authorised Person).

---

## 0. Instructions to Claude Code (read first — non-negotiable)

1. **The spec is authoritative. Do not change architecture.** If the specs (docs 01–09) define a data model, flow, or contract, implement it as written. Architectural decisions belong to the Design Authority, not the implementation engine.
2. **Report inconsistencies rather than inventing.** The earlier OPEN decisions are now **RESOLVED and locked**: identifier = raw Zerodha `client_id` in the path (ADR-001); domain = bare `gorefer.in` + path (ADR-005); lead destination = `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}` (locked); runtime = **simple central app + one PostgreSQL DB, NO edge/distributed** (ADR-021; edge deferred to backlog DF-3). The Round-2 external-review decisions folded into docs 01/02/05/06/07/08/12 are also authoritative. If you find a **NEW** inconsistency or ambiguity, **stop and surface it** with options + a recommendation — do **not** silently pick one and build on it. Prefer a feature flag / config so a choice can be swung later.
3. **NEVER auto-submit Zerodha's reCAPTCHA form.** Zerodha's signup/lead form is reCAPTCHA-gated and lead-capture-only. Automated/background submission is bot-gated and prohibited (compliance + account risk). The ONLY compliant path is redirecting a **real human browser** to the pre-filled public URL. No headless submit, no bot, no exceptions.
4. **NEVER fabricate account-status or reward data.** Account-opening and reward events originate ONLY in Zoho (recorded as an "Imported Event" with a source). GoRefer reads that status back; it never computes, guesses, or invents it. A referral is "converted" only when Zoho says so.
5. **Compliance is a hard gate.** Every user-facing asset carries the AP disclosure block and market-risk warning; the "10%" claim lives in a single swappable config value; the branded form must NOT resemble Zerodha's page. Never expose raw Zerodha URLs or partner codes in the UI.
6. **When in doubt, ask — one decision at a time.** Do not batch-guess through ambiguity.

---

## 1. Tech direction

| Layer | Direction | Notes |
|---|---|---|
| **Frontend** | **Server-rendered Django templates + HTMX + Tailwind (ADR-024)** | Most users arrive from WhatsApp on a phone → mobile-first, light HTML (Constitution). **NO React/SPA in Sprint 1.** HTMX for form submit + dashboard interactivity; Tailwind for styling; reusable template components (partials); keep pages light for slow Indian mobile networks. |
| **Backend** | **Django + Django Ninja (ADR-024)** | API-first: every feature is a Django Ninja router (REST/JSON, Pydantic-typed schemas enforcing the strict Zoho/WATI + opener-vs-referrer contracts) before a UI. Django ORM + Django migrations; customized Django admin jump-starts the M7 dashboard; env-bootstrapped admin-only auth. |
| **Database** | **PostgreSQL** | Relational; the data model (Customer, ReferralLead, Click, ReferralJourney) maps cleanly. Use migrations (§9). |
| **Redirect service** | **Fast route inside the single central app (ADR-021)** | The `/r/{client_id}` redirect is the hottest path: keep it low-latency **inside the one central app — NO edge, NO Cloudflare Worker** (edge deferred, backlog DF-3; at ~4 redirects/sec peak a normal central route is far more than fast enough). It logs the click event, then 302s to the correct pre-filled Zerodha URL. It must NOT block on slow writes — log async / fire-and-forget where safe. |
| **Provider-agnostic core** | **"Referral Program" abstraction** | Sprint 1 has exactly ONE program (Name: Zerodha, Partner Code: ZMPHZC). Never hardcode "Zerodha" in DB/API/UI/analytics. Model a `ReferralProgram` with a partner code and a destination-URL template; Zerodha is row #1. |

**Key path contract (LOCKED, raw client_id — ADR-001):** `gorefer.in/r/{client_id}` → **format-validate** the raw `client_id` from the path (no token, no lookup) → **lazily create** referrer+journey+click on first click → log Click → `302` to `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r=<client_id>`. `c=ZMPHZC` is injected **server-side**; the raw Zerodha URL is assembled server-side from the program's destination template + the `client_id`; it is never stored in or exposed to the client.

> **LOCKED — do not reintroduce a token:** the identifier is the **raw Zerodha `client_id` in the path** (ADR-001) and the domain is `gorefer.in` bare-domain + path (ADR-005). Still implement the redirect resolver behind an interface so a **future non-Zerodha partner** (which may need a GoRefer-generated id minted at referrer login) can be wired without touching the WATI/Zoho contracts.

> **Stack (LOCKED — ADR-024):** Django + Django Ninja + HTMX + Tailwind + PostgreSQL, with `django-tenants` for the ADR-023 multi-tenant boundary. Background work via `transaction.on_commit()` + a light DB-backed queue (django-q / django-rq); Celery/Redis only when scheduled workflows demand it. The redirect is a sync Django view (validate → 302, click write on-commit). Full basis: [`review/Framework-Decision-Synthesis.md`](../review/Framework-Decision-Synthesis.md); decision record [`ADR-024`](../docs/architecture/02-Architecture-Decisions-ADR.md).

---

## 2. Repository / folder structure (suggestion)

```
gorefer/
├── backend/
│   ├── src/
│   │   ├── api/            # REST route handlers (thin)
│   │   ├── domain/         # ReferralProgram, Referral, Lead, Click, Journey
│   │   ├── services/       # link-gen, redirect-resolver, wati-adapter, zoho-adapter
│   │   ├── db/             # models, repositories
│   │   └── config/         # env loading, feature flags
│   ├── migrations/         # ordered, forward-only SQL migrations
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── pages/          # branded landing form, /rewards, /help, /track
│   │   ├── components/
│   │   └── lib/
│   └── tests/
│                            # NOTE: no separate redirect/ worker — the /r/{client_id} redirect is a fast route inside backend/ (api + services/redirect-resolver), per the central model (ADR-021). Edge worker deferred (DF-3).
├── docs/                   # 01–10 specs (this guide is 10)
├── infra/                  # deploy config, env templates
├── scripts/                # seed demo data, run migrations, submit WATI templates
├── .env.example            # every flag + secret name, no values
├── CLAUDE.md               # working instructions for Claude Code
└── README.md
```

Keep `api/` handlers thin — business logic lives in `domain/` and `services/`. The WATI and Zoho integrations are **adapters** behind interfaces (contract in doc 08), so they can be tested with fakes and swapped.

> **Concrete Django layout (ADR-024):** the tree above is conceptual. In practice this is a **Django project** — apps such as `referrals/`, `events/`, `config/`, `tenants/`, `integrations/` (Zoho/WATI adapters) — plus `templates/` (Django templates + reusable HTMX partial components), `static/` (Tailwind), and **Django Ninja** routers for the JSON API. Use the **Django ORM + Django migrations** (NOT SQLAlchemy/Alembic). The `/r/{client_id}` redirect is a sync Django view (validate → 302; click/journey write via `transaction.on_commit()`, idempotent by unique constraint).

---

## 3. Coding standards

- **One concept: "Referral Program."** No file, class, table, column, route, or analytics event named `Zerodha*` unless it is explicitly a plugin/adapter. `ReferralProgram` yes; `ZerodhaReferral` no.
- **Never expose internal logic** — no Zerodha URLs, partner codes, internal IDs, or DB IDs in any client response or URL. Users interact only with GoRefer.
- **Config over hardcode** — partner code `ZMPHZC`, the destination-URL template, the "10%" claim string, Ashok's alert number, and every feature flag come from config/env, never inline literals.
- **Secrets from a secret store** — the WATI bearer JWT and Zoho credentials load from env/secret store. Never inline (the current hardcoded WATI JWT is a known finding to avoid repeating).
- **Normalize phone consistently** — the canonical Mobile key: remove spaces / `+` / `()` / `-`, then prefix `91`. One shared helper; used everywhere (dedup, Zoho join, WATI send).
- **Small, precise commits and functions.** Clear names, typed boundaries, input validation on every external input (form submit, redirect `client_id`, webhook).
- **Bilingual-ready** — user-facing strings externalized (Hindi/English); no hardcoded copy in components.

---

## 4. Feature flags

Ship dormant capabilities behind flags so Sprint 1 stays lean and later sprints light up without a rebuild. Default the not-yet-built ones to `false`.

```
ENABLE_CUSTOMER_LOGIN=false      # customer dashboard/auth is a later sprint
ENABLE_WATI_SEND=false           # keep off until templates are Meta-approved
ENABLE_ZOHO_WRITE=false          # off until Zoho adapter verified against sandbox
ENABLE_ASSET_GENERATOR=false     # poster/PDF generator — later sprint
ENABLE_ADMIN_DASHBOARD=true      # Sprint 1 Mission 7
ENABLE_DEMO_MODE=true            # sample data, no external calls (see §10)
REFERRAL_INCENTIVE_CLAIM="300 reward points + 10% brokerage share"  # single swappable place (compliance)
```

- Flags are read from config at startup; no flag is checked by a string literal scattered across the code — one config module.
- `ENABLE_WATI_SEND` and `ENABLE_ZOHO_WRITE` stay `false` in dev/demo; when `false`, the adapters log the intended call instead of making it (so the flow is testable end-to-end without touching production systems).

---

## 5. Bootstrap admin from env vars

- The first admin user is **bootstrapped from environment variables** (`ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH` or a one-time bootstrap token) on first run — never a hardcoded credential, never a seeded default password in the repo.
- If the admin already exists, the bootstrap is a no-op (idempotent).
- Admin auth for Sprint 1 can be minimal (single admin) but must be real (hashed secret, no plaintext); customer-facing login stays behind `ENABLE_CUSTOMER_LOGIN=false`.

---

## 6. Testing expectations

- **Unit tests** for domain logic: `client_id` format validation, lazy create-or-find of the referrer/journey on first click, phone normalization, destination-URL assembly (with `c=ZMPHZC` injected server-side), dedup/suppression rules.
- **Integration tests** for the WATI and Zoho adapters against **fakes** implementing the doc-08 contract (no live calls in CI).
- **End-to-end happy path**: submit branded form → lead persisted → (flagged) notifications enqueued → redirect logs click → 302 to correct Zerodha URL.
- **Guardrail tests (must exist):** (a) a test asserting the redirect service **never** performs a POST/submit to Zerodha (redirect only); (b) a test asserting account-status can only be set from a Zoho-sourced import path, never from an internal write; (c) a test asserting no raw Zerodha URL or partner code appears in any client-facing response.
- **Verify delivery, not acceptance** — any WATI send test asserts on terminal message status, not HTTP 200 (doc 08 A3).
- CI runs the full suite; a red suite blocks merge and blocks "done."

---

## 7. Git workflow

- **Trunk-based with short-lived feature branches.** One mission (or a slice of it) per branch; branch name `mission-N-short-desc`.
- **Small commits**, imperative messages, referencing the mission/task.
- **PR per mission**, self-reviewed against the Definition of Done (§8) before requesting Abhay's review. Claude Code opens the PR with a summary of what was built, what was deferred, and any inconsistency surfaced.
- **No direct commits to main.** Main stays deployable at all times (vertical-slice principle: every sprint ships something usable end-to-end).
- **Claude Code never invents features** in a PR; scope stays within the mission. Suggestions go in the PR description for review, not into the code.

---

## 8. Migration strategy

- **Forward-only, ordered SQL migrations** in `backend/migrations/`, one file per change, numbered.
- Every schema change ships as a migration + a matching model change in the same PR; never edit a shipped migration — add a new one.
- Migrations run via a script (`scripts/migrate`) in CI and deploy; the app verifies the schema version on boot.
- Seed/demo data (§10) is a **separate** seed script, never mixed into schema migrations.

---

## 9. Definition of Done (every mission)

A mission is **done** only when ALL of these hold:

1. Implemented to the spec (docs 01–09); no architecture drift.
2. Feature flags correct; nothing half-built is reachable in production.
3. Unit + integration + the three guardrail tests pass; CI green.
4. Migrations included and reversible-by-forward-migration; schema boots clean.
5. No secrets inline; config/env used; `.env.example` updated.
6. No raw Zerodha URL, partner code, or internal ID exposed to any client.
7. Compliance surfaces (disclosure block, risk warning, swappable 10% claim) present on every user-facing asset touched.
8. Demo mode still works end-to-end with `ENABLE_WATI_SEND` / `ENABLE_ZOHO_WRITE` off.
9. PR opened with summary, deferrals, and any surfaced inconsistency.
10. README/docs updated for anything a human operator needs to run it.

---

## 10. Demo mode with sample data

- `ENABLE_DEMO_MODE=true` runs the **entire flow with no external calls**: WATI and Zoho adapters log their intended payloads instead of sending; the redirect resolves against seeded sample `client_id`s.
- `scripts/seed-demo` loads a handful of sample referrers (with fake `client_id`s), sample referral leads across statuses (New → Contacted → KYC Started → Account Opened), and sample click events — so the admin dashboard and analytics render with realistic data for a demo without touching production Zoho/WATI.
- Demo mode is the default for local dev and for any review/screenshot. It is the safety net that lets the whole vertical slice be shown working before any live template is approved or any real lead exists.

---

## 11. Build order — Sprint 1 (seven missions)

Build **vertical slices**, in order. Each mission is a slice that leaves main deployable.

| Mission | Deliverable | Notes / guardrails |
|---|---|---|
| **M1 — Repository / skeleton** | Repo structure (§2), config + feature-flag module (§4), env bootstrap incl. admin (§5), migrations harness (§8), CI running an empty-but-green test suite, README. | Foundation only. `ReferralProgram` seeded with the single Zerodha row (Partner Code `ZMPHZC`) — provider-agnostic from day one. |
| **M2 — Raw client_id redirect + lazy journey + click event** | `client_id` format validator; lazy create-or-find of referrer+journey on first click; the fast central-app redirect route (`/r/{client_id}` → log Click → 302 to Zerodha URL with `c=ZMPHZC` injected server-side; no edge worker, ADR-021); Click event persisted. | **Redirect only — never submit Zerodha's form.** Raw `client_id` in path, no token (ADR-001). Solves R3 (no click tracking today). Destination assembled server-side from the program template. |
| **M3 — Branded landing page** | PIFS-branded, mobile-first landing/capture form (fields: mobile, name, email; `c=`+`r=` baked in and hidden); "Open Account" (→ redirect) and "Need Help" (→ lead capture) paths. | **Must NOT resemble Zerodha's page** (misrepresentation rule). Disclosure block + risk warning present. |
| **M4 — Analytics / journey** | ReferralJourney + analytics: link created, link opened, landing viewed, redirect completed; funnel view data. | "Track everything" (Constitution). Read-only aggregation; no fabricated conversion events. |
| **M5 — WATI hooks** | WATI adapter behind the doc-08 contract: generate link into template, fire the three notifications (Ashok / new person / referrer-if-phone-known); deduped, opt-in-aware audience; terminal-status verification. | Behind `ENABLE_WATI_SEND=false` until templates are Meta-approved. First message to non-opted-in lead = warm UTILITY notice naming the referrer. |
| **M6 — Zoho lead + status sync** | Zoho adapter: create Lead on submit (save lead FIRST, stamp a GoRefer reference on the Zoho lead), read account status back, reflect removals (reversal/tombstone). | Behind `ENABLE_ZOHO_WRITE=false` until verified. **Status comes ONLY from Zoho; never fabricate.** Conversion matching: **referrer by Zerodha client ID**, **opener by Zerodha account ID** — **NOT by mobile** (conversion data has no mobile; #10/#11); upsert on opener account ID. "Rewarded" only if Zoho signals a reward, else terminal = account_opened (#12). Webhook: basic key + Zoho-IP allowlist now; wax-seal deferred DF-2, Zoho-API pull deferred DF-1. Lazy per-referrer history fetch, not bulk (bulk = DF-4). |
| **M7 — Admin dashboard / referral explorer** | Admin panel: search customers, view referral leads + statuses, funnel analytics, top-referrer view. | `ENABLE_ADMIN_DASHBOARD=true`. Renders correctly in demo mode with seeded data. |

**Sequencing logic:** M1–M4 need no external system, so they ship and demo immediately (works offline in demo mode). M5 (WATI) and M6 (Zoho) integrate the external systems behind flags, in parallel with template approval. M7 makes the whole slice observable. This is the exact Build-Spec order: form + capture first (works immediately), WATI templates submitted in parallel.

### 11.1 Explicitly NOT in Sprint 1 (deferred / future — do NOT build)

These are recorded so the architecture stays forward-compatible, but Claude Code **must not** implement them in Sprint 1. They are later-sprint work:

- **Customer login / self-service dashboard, public registration, reward calculations, payment integrations, mobile app, multi-language** — later sprints (Foundation Spec §Product Scope; `ENABLE_CUSTOMER_LOGIN=false`).
- **Poster / PDF asset generator** — later sprint (`ENABLE_ASSET_GENERATOR=false`).
- **Stale-lead auto-nudge via Wati (Foundation Spec REQ-F01) — DEFERRED, Sprint 2+.** When a GoRefer-sourced lead ages without converting (approaching Zerodha's 60-day window), GoRefer would automatically WhatsApp the prospect via Wati to nudge account completion. **Sprint 1 does NOT do this:** stale-lead follow-up is **owned by Zoho** (source of truth) and GoRefer shows only a **read-only aging flag** derived from its own timeline (GoRefer-derived, never a Zoho override). The active Wati nudge is deferred until the **WATI delivery-dedup + opt-in fix** (doc 08 §A3/A4, the ~33% delivery-failure item) lands, and must respect Meta opt-in rules (warm, utility-style message). **Do not build the active nudge in Sprint 1.**

---

## 12. Guardrail recap (pin this)

- Redirect a **human browser** to Zerodha; **never auto-submit** the reCAPTCHA form.
- Account/reward status **only** from Zoho; **never fabricate**.
- **No architecture changes**; surface NEW inconsistencies, don't resolve them silently (the earlier OPEN decisions are now locked — see §0.2).
- **No exposed** Zerodha URLs, partner codes, or internal IDs.
- **Compliance block + risk warning** on every asset; **10% claim** in one swappable place.
- **Secrets from config**, phone normalized one way, provider-agnostic naming.

---

*Session: Cowork, 2026-07-04. Specs 01–09 are authoritative. Ground truth: `GoRefer-Build-Spec-Cowork-Decisions.md`, `GoRefer-Context-Brief.md`, `GoRefer-Master-SourceOfTruth-from-ChatGPT.md`, `08-Zoho-WATI-Integration.md`.*
