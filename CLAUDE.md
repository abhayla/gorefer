# CLAUDE.md — GoRefer Operating Manual (Sprint 1: Foundation)

> **Read this first, before writing any code.** This is the entry point for Claude Code. It is a map + rulebook, **not** a re-spec. For depth, follow the pointers into `docs/` — the spec is authoritative, this file is not.
>
> **Owner:** Abhay Kumar Maurya / PIFS (Passive Income Financial Solutions), a Zerodha Authorised Person. **Compiled:** 2026-07-04. **Sprint:** 1 (Zerodha only).

---

## 1. What GoRefer is

GoRefer is a **Referral Management & Referral Intelligence platform**: users manage, share, and track referral links from partner businesses through one unified system, and GoRefer records the complete referral lifecycle (create → share → click → landing → redirect → lead → account/reward) as an immutable event stream. GoRefer does **not** own any referral program — it integrates with programs run by partners. **Sprint 1 enables exactly ONE program: Zerodha** (Partner Code `ZMPHZC`), but the architecture is **provider-agnostic and extensible** to future partners (Groww, insurance, mutual funds, properties, loans) via configuration, never a rebuild. **There is NO Zerodha API.** Account-opening and reward status originate **only in Zoho CRM**, which is the authoritative source of truth for referral credit and account status; GoRefer verifies only what it observes (clicks, redirects) and never fabricates downstream status.

---

## 2. How to use this repo

**The spec is authoritative.** Read the relevant doc before coding. If docs conflict or a decision is ambiguous or marked OPEN, **STOP and ask** — do not invent a resolution and build on it. Prefer to build behind a feature flag or config so a choice can be swung later.

Document map (start at `README.md` for the index):

| Location | What it holds |
|---|---|
| `docs/foundation/01-GoRefer-Foundation-Specification.md` | Vision, scope, actors, lifecycle state model (S0–S7), REQ/BR/NFR/AC. |
| `docs/foundation/03-GoRefer-Constitution.md` | The 16 non-negotiable engineering principles. Every PR is checked against it. |
| `docs/architecture/02-Architecture-Decisions-ADR.md` | ADR-001…ADR-024 — the locked, hard-to-reverse decisions (incl. ADR-021 central runtime, ADR-022 config cascade, ADR-023 multi-tenant boundary, **ADR-024 tech stack: Django + Django Ninja + HTMX + Tailwind + Postgres**). |
| `docs/architecture/04-System-Architecture.md` | Orchestrator model, sequence flows. |
| `docs/database/05-Database-Design.md` | Referral identity, journeys, events, dates. |
| `docs/api/06-API-Specification.md` | `GET /r/{client_id}`, `GET /open`, `POST /api/leads`, `POST /api/share`. |
| `docs/ui-ux/07-UI-UX-Specification.md` | Landing page, disclosure rendering. |
| `docs/integrations/08-Zoho-WATI-Integration.md` | Zoho sync + WATI delivery-status contract (adapters implement this). |
| `docs/workflow/11-Referral-Workflow-and-Edge-Cases.md` | End-to-end workflow. |
| `docs/workflow/12-Resolved-Gaps-and-Edge-Case-Decisions.md` | **Authoritative edge-case decisions** (16 gaps, locked → ADR-015…020). |
| `implementation/10-Claude-Code-Implementation-Guide.md` | **The build guide**: tech direction, standards, tests, git, DoD, build order. |
| `review/` | LLM review pack (`09`) + review bundle. |
| `_source-archive/` | Historical source-of-truth captures (context only). |

When docs 11 and 12 both speak to an edge case, **doc 12 (resolved gaps) wins**.

---

## 3. Your role

You are the software **ENGINEER**, not the architect. Implement **exactly** what the spec says. **Never invent features, and never change the architecture.** Architectural decisions belong to the Design Authority. If you find an inconsistency, an OPEN decision, or a source conflict, **report it** (surface options + a recommendation) — do not guess and build on a silent pick.

---

## 4. Non-negotiable guardrails (the hard rules)

**Tech stack (LOCKED — ADR-024)**
- Build on **Django + Django Ninja + HTMX + Tailwind + PostgreSQL**, with **`django-tenants`** for the ADR-023 multi-tenant boundary. Server-rendered Django templates with **reusable HTMX partial components** — **NO React/SPA in Sprint 1**. **Django ORM + Django migrations** (not SQLAlchemy/Alembic). Background via `transaction.on_commit()` + a light DB-backed queue (django-q/django-rq); Celery/Redis only when scheduled workflows demand it. The `/r/{client_id}` redirect is a sync Django view (validate → 302, click write on-commit). Basis: [`review/Framework-Decision-Synthesis.md`](./review/Framework-Decision-Synthesis.md); record: ADR-024 in `docs/architecture/02` and tech direction in `implementation/10` §1.

**Referral link & redirect**
- Referral link identifier = the **RAW Zerodha `client_id` in the path**: `gorefer.in/r/{client_id}` (e.g. `gorefer.in/r/RJ4521`). **NO token, NO token→id mapping DB** (ADR-001). The `client_id` is already public (it appears in Zerodha's own `r=` links).
- Partner code `ZMPHZC` is **injected SERVER-SIDE** into the redirect and **never appears in the shared URL**. The destination is assembled server-side from the program's URL template: `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}`.
- **Partner-direct link** `gorefer.in/open` → redirect to `https://signup.zerodha.com/?c=ZMPHZC` (**no `r=`**). Its journey is stored with **`referrer = NONE`, `source = partner_direct`** — never a fake/synthetic referrer (ADR-015). The Referral Explorer filters referral vs partner-direct as separate populations.

**Source of truth — Zoho only, never fabricate**
- **Zoho is the SINGLE authoritative source of truth** for referral credit + account-opening/reward status. GoRefer **never infers, overrides, or fabricates** conversion/referrer/reward data (ADR-013, ADR-016, Constitution §8).
- **Single-winner attribution**: one account = exactly one credited referrer, exactly as Zoho holds it. **No last-redirect / last-click fallback.** If Zoho shows no referrer, GoRefer credits **no one**. Referrer is credited/matched by the **Zerodha client ID** (the raw `client_id` in the link, ADR-001); conversion data carries **no mobile**. The opener→journey link is best-effort via a GoRefer journey-reference stamped on the Zoho lead (Round-2 amendment #10).
- **Off-platform conversions** (account opened with a referrer but no GoRefer click) are **ingested from Zoho** and still shown; a converted journey can exist with **zero clicks**. Referrer identity is created lazily on **first click OR first Zoho-imported conversion**.
- **NO Zerodha API, ever.** Account/reward status comes only from Zoho. **Reward AMOUNTS live only in the Zerodha Console** — GoRefer never computes or stores rewards, and there is **no PIFS-funded top-up**.
- Store the **TRUE Zoho account-opening date** as a first-class field, distinct from the sync/import date; **all conversion analytics run off the true opening date** so imports land in their real period with no fake day-1 spike (ADR-017).

**Never auto-submit Zerodha**
- Zerodha's signup/lead form is **reCAPTCHA-gated and lead-capture-only** (ends at a "thanks" screen; does not proceed into PAN/KYC). **NEVER auto-submit, headless-submit, or bot-submit it.** The ONLY compliant path is redirecting a **real human browser**; a human (Ashok) completes KYC on a call.

**Landing page (branded, config-driven)**
- The landing page is **per-partner CONFIG (not hardcoded)**, clearly **PIFS-branded**, and must **NOT resemble/clone Zerodha's page** (misrepresentation risk).
- Two buttons: **(1) "Continue to Zerodha"** → a short name/email/phone form that **saves the lead FIRST** (GoRefer + Zoho), then redirects to `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}`. (Auto-filling Zerodha's own fields is an **OPEN POC, NOT a dependency** — do not block on it.) **(2) "Share referral details on WhatsApp"** → a `wa.me` deep link to the **WATI BUSINESS number `+91 70806 42020`** (NOT Ashok's personal `73888 82020`) with a referring-language pre-fill that **includes the referral id**.
- Show a small **"Referral ID: X"** echo line for self-serve visual confirmation (no separate confirm page).

**Lazy journey creation**
- Nothing is stored until the **first click**. On first click, create the referrer (if new) + journey + click event — after **format-validating the id only** (reject empty/oversized/illegal chars). **NO ownership verification** (there is no Zerodha API to check against) (ADR-008, Gap 3).

**Visitor identity (best-effort)**
- First-party cookie **`visitor_id`** set on first click (same cookie = same journey). A **JS-confirmation beacon** marks a **"confirmed human click"**. Filter **bot/preview user-agents** (WhatsApp, `facebookexternalhit`, Telegrambot, Slackbot, Twitterbot, LinkedInBot, Googlebot, prefetchers) — logged but excluded from counts; a bot preview never creates a journey or a redirect. **Unique-visitor counts are approximate and must be labelled as such.** Promote to a **mobile-keyed identity on form submit** and merge cookie-journeys sharing that mobile (lead-side only). **Conversions are keyed by the opener's Zerodha account ID, and the referrer by Zerodha client ID — NOT mobile** (Round-2 amendments #10/#11) (ADR-018, ADR-019).

**Compliance (hard gate)**
- The **SEBI/NSE AP disclosure block + market-risk warning + reward wording** are **per-partner CONFIG, AUTO-INJECTED into every page and baked into every generated asset** — they **cannot be omitted**. NSE AP reg. no. `AP2516003693`.
- The **"10% brokerage" wording lives in ONE editable config field** (`REFERRAL_INCENTIVE_CLAIM`, e.g. `"300 reward points + 10% brokerage share"`).
- Run the **`zerodha-ap-social-media-compliance` review before publishing anything public.** **Never impersonate or clone Zerodha** (ADR-014, Gap 15).

**Privacy / DPDP**
- **Consent + Privacy Policy link on the form**; **purpose limitation** (referral / account-opening only); **anonymize/purge UNCONVERTED prospect PII after 12 months**; **store the raw IP + city as PII in a separate erasable record (no hashing)** (Round-2 amendment #17; reverses earlier hash/drop); **PII kept OUT of the immutable event log** (Round-2 amendment #16); **manual erasure on request** in Sprint 1 (ADR-020).

**Auth & configuration**
- **Admin-only in Sprint 1**; bootstrap the admin from **ENV VARS** (`ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH` / one-time token), idempotent, hashed — never a seeded plaintext credential. Customer login stays behind `ENABLE_CUSTOMER_LOGIN=false`.
- **Feature flags gate all disabled features.** **NEVER show "Coming Soon", placeholder menus, disabled buttons, or dead UI** (Constitution §4).
- **Configuration over code** for adding future partners — no `Zerodha*`-named file/table/route/event; model a `ReferralProgram` with a partner code + destination-URL template (Zerodha = row #1).

---

## 5. Sprint 1 build order (seven vertical slices)

Build in order; each slice leaves `main` deployable (see `implementation/10` §11).

1. **M1 — Repo / skeleton**: structure, config + feature-flag module, env bootstrap (incl. admin), migrations harness, CI green, README. Seed the single `ReferralProgram` (Zerodha, `ZMPHZC`).
2. **M2 — Raw `client_id` redirect + lazy journey + click event**: format-validate the id; lazy create-or-find referrer + journey on first click; fast/edge redirect `/r/{client_id}` → log Click → 302 with `c=ZMPHZC` injected server-side. **Redirect only — never submit.**
3. **M3 — Branded landing page**: PIFS-branded, mobile-first capture form; two buttons (Continue to Zerodha / Share on WhatsApp); disclosure block + risk warning present; must not resemble Zerodha.
4. **M4 — Analytics / journey**: ReferralJourney + funnel events (link created, opened, landing viewed, redirect completed); read-only aggregation, no fabricated conversions.
5. **M5 — WATI hooks**: WATI adapter behind the doc-08 contract; three notifications (Ashok / new person / referrer-if-phone-known); deduped, opt-in-aware; terminal-status verification. Behind `ENABLE_WATI_SEND=false` until templates are Meta-approved.
6. **M6 — Zoho lead + status sync**: Zoho adapter; create Lead on submit (save lead FIRST); resolve referrer from `client_id`; read account/reward status back. Behind `ENABLE_ZOHO_WRITE=false`. **Status only from Zoho.**
7. **M7 — Admin dashboard / referral explorer**: search customers, view leads + statuses, funnel analytics, top-referrer view. Renders in demo mode with seeded data.

M1–M4 need no external system (work offline in demo mode); M5/M6 integrate behind flags in parallel with template approval; M7 makes the slice observable.

---

## 6. Explicitly NOT in Sprint 1 (do NOT build)

The architecture supports these, but **do not implement** them in Sprint 1 — they stay off behind feature flags, never shown as dead UI:

- **Customer login / "My Referrals" self-service dashboard** (`ENABLE_CUSTOMER_LOGIN=false`).
- **WATI stale-lead auto-nudge (REQ-F01)** — deferred to Sprint 2+; stale-lead follow-up is owned by Zoho; GoRefer shows only a read-only aging flag. Gated on the WATI delivery-dedup + opt-in fix.
- **Reward computation / calculations / payment integrations** (rewards live only in Zerodha Console).
- **Multi-partner UI** (architecture is provider-agnostic; UI exposes only Zerodha).
- **Public self-service registration**, **mobile app**, **poster/PDF asset generator** (`ENABLE_ASSET_GENERATOR=false`), **multi-language**.

---

## 7. Definition of Done + expectations

Reference `implementation/10-Claude-Code-Implementation-Guide.md` (§3 standards, §6 tests, §7 git, §8 migrations, §9 DoD, §10 demo mode). A mission is **done** only when all hold:

- Implemented to spec (docs 01–09); **no architecture drift**; inconsistencies surfaced, not silently resolved.
- **Feature flags** correct; nothing half-built reachable in production; no "Coming Soon".
- Unit + integration tests **plus the three guardrail tests** pass; CI green:
  1. the redirect service **never** POSTs/submits to Zerodha (redirect only — never auto-submit reCAPTCHA);
  2. account-status can be set **only** from a Zoho-sourced import path, **never** fabricated by an internal write;
  3. **no** raw Zerodha URL or partner code appears in any client-facing response.
- Migrations included (forward-only, ordered); schema boots clean; demo/seed data is a separate script.
- **No secrets inline** — config/env only; `.env.example` updated. Phone normalized one canonical way (strip spaces/`+`/`()`/`-`, prefix `91`).
- **Compliance surfaces** (disclosure block, risk warning, single swappable 10% claim) present on every user-facing asset touched.
- **Demo mode still works end-to-end** with `ENABLE_WATI_SEND` / `ENABLE_ZOHO_WRITE` off (adapters log intended calls instead of sending).
- WATI send tests assert on **terminal delivery status**, not HTTP 200.
- PR opened per mission with a summary, deferrals, and any surfaced inconsistency; README/docs updated for anything an operator must run.

---

*Grounding: `docs/foundation/01`, `docs/foundation/03`, `docs/architecture/02` (ADR-001…020), `docs/workflow/12`, `implementation/10`. The spec is authoritative; when in doubt, STOP and ask — one decision at a time.*
