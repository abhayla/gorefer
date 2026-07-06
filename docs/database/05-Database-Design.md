# GoRefer — 05. Database Design

> **What this is.** The production PostgreSQL schema for **GoRefer**, organized into the **12 bounded contexts** from the master source-of-truth. This is the system of record for GoRefer's referral intelligence — and deliberately *not* a customer master: no PAN, Aadhaar, KYC, or brokerage data lives here.
>
> **Read alongside:** [`04-System-Architecture.md`](./04-System-Architecture.md) (which components read/write these tables and the event/orchestrator model) and [`06-API-Specification.md`](./06-API-Specification.md) (the API contracts over this schema).
>
> **Grounded in:** `GoRefer-Master-SourceOfTruth-from-ChatGPT.md` (esp. Addition 10 "Production Database Design v1", Additions 8 & 18) and `GoRefer-Build-Spec-Cowork-Decisions.md`. **Date:** 2026-07-04.
>
> **Golden rule:** every table has exactly **one** responsibility. The `customers` table never stores analytics; the `events` table never stores business ownership. (`Master` Addition 10.)

---

## 1. Database Philosophy

GoRefer stores **workflow** data, not business **ownership** data. It tracks referral identities (raw `client_id`), campaigns, landing experiences, marketing assets, analytics, and lead assignments. It does **not** become the system of record for customer KYC, trading activity, reward calculation, brokerage, or holdings — those stay with Zerodha (or a future partner). This structurally minimizes security and compliance (DPDP) risk. (`Master` Addition 10; `04` §1, §7.5.)

Two principles drive the shape of everything below:

- **Event-driven, not counter-driven (ADR-004, approved).** Store business events (`ReferralLinkOpened`), never mutable counters (`clicks++`). Analytics are *derived* from the immutable `events` table; the aggregate tables in Context 12 are rebuildable rollups, not authoritative truth. (`Master` Additions 8, 10.)
- **Lazy journey creation.** Journey/analytics rows are created **only on the first click** of a referral link — never when a link is merely generated, and never per customer. Data volume tracks *actual activity*, not headcount. (`04` §8.)

---

## 2. Conventions (apply to every table)

**Naming.** (`Master` Addition 10.)
- Tables are **plural**: `customers`, `campaigns`, `referrals`, `referral_identities`, `events`.
- Columns are **snake_case**: `created_at`, `partner_id`, `client_id`.
- Primary key is always **`id`**.
- Foreign keys are **`<entity>_id`**: `customer_id`, `campaign_id`, `program_id`, `partner_id`.

**Soft-delete columns** — on every important table (nullable):
- `deleted_at TIMESTAMPTZ` · `deleted_by BIGINT` (→ `users.id`) · `delete_reason TEXT`.
- A row is "live" when `deleted_at IS NULL`. Nothing is hard-deleted from business tables.

**Audit columns** — on every important table:
- `created_by BIGINT` · `updated_by BIGINT` (→ `users.id`; null for system/edge writes) · `version INTEGER NOT NULL DEFAULT 1` (optimistic locking — bumped on every update).
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` · `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`.

**Imported-status → recorded source.** Any field whose truth originates in another system (chiefly **account-opening / conversion status imported from Zoho**) carries a companion **`*_source`** column (e.g. `source = 'zoho'`) and a **`*_synced_at`** timestamp, so every imported value is traceable to where it came from and when. GoRefer never fabricates these — they are set only from a verified partner source. (`04` §4.3, §11.)

**Lazy-creation rule (enforced in application logic, reflected here).** Nothing is pre-provisioned. On the **first click** of `gorefer.in/r/{client_id}`, GoRefer creates the `referral_identity` (keyed by the raw `client_id`), the `referral`, and the click `event` together — after format-validating the `client_id`. There is no link-generation step and no pre-loaded customer list. (`04` §8; ADR-001, ADR-008.)

**DPDP consent & retention (Gap 15).** Personal data is captured only with explicit **consent** (recorded on the lead). **Retention limit:** personal data on **unconverted** journeys is **anonymized after 12 months** (name/mobile/email stripped; aggregate event rows retained). **PII lives only on the erasable person/lead record — never in the immutable event log.** The **raw IP and derived city are both stored on that erasable record, unhashed**; they are retention-limited and erasable on request (not hashed, not dropped). These rules apply across `prospects` and `leads`; `events` carry **no PII** (see §12).

**Tenant scoping (multi-tenant boundary, ADR-023).** Every tenant-scoped table carries a **`tenant_id`** column (→ `tenants.id`). Sprint 1 runs a **single tenant (PIFS)**, but the boundary is designed now so a second tenant (e.g. AngelOne) is a data partition, never a rebuild. All queries filter by `tenant_id`; the column is part of every uniqueness constraint that must be per-tenant (e.g. `(tenant_id, program_id, client_id)`). Truly global reference rows (system roles/permissions) are tenant-null.

**Types.** `id` = `BIGINT GENERATED ALWAYS AS IDENTITY`. Timestamps = `TIMESTAMPTZ`. Free-form/extensible payloads = `JSONB`. Short codes/tokens = `TEXT` (or `VARCHAR` with a length) + unique index.

---

## 3. The 12 Bounded Contexts (map)

```
 1  Identity            users, roles, permissions, user_sessions, audit_logs
 2  Referral Programs   programs, program_settings, program_redirect_rules
 3  Partners            partners, partner_contacts, partner_branding, partner_domains
 4  Customers           customers  (minimal only — NO PAN/KYC/brokerage)
 5  Referral Identities referral_identities  (the heart)
 6  Referrals           referrals  (distinct from identities)
 7  Prospects           prospects
 8  Campaigns           campaigns
 9  Marketing Assets    marketing_assets  (one table, all asset types)
10  Landing Experiences landing_experiences
11  CRM linkage         leads, lead_notes, lead_assignments, lead_status_history, executive_calls
12  Analytics           events, sessions, devices, campaign_stats, daily_metrics
```
(`Master` Addition 10.)

---

## 4. ASCII ER Overview

```
 IDENTITY (1)                 PROGRAMS (2)                 PARTNERS (3)
 ┌─────────┐                  ┌──────────┐                 ┌──────────┐
 │ users   │                  │ programs │◄───────────────│ partners │
 │ roles   │                  └────┬─────┘   partner_id    └────┬─────┘
 │ perms   │                       │                            │
 └────┬────┘        program_settings·program_redirect_rules  partner_contacts
      │ created_by/updated_by (audit) on ALL tables          partner_branding
      │                              │                        partner_domains
      │                              │
      ▼                              ▼
                    CUSTOMERS (4)               PROSPECTS (7)
                    ┌───────────┐               ┌───────────┐
                    │ customers │               │ prospects │
                    └─────┬─────┘               └─────┬─────┘
                          │ customer_id               │ prospect_id
                          ▼                           │
   CAMPAIGNS (8)   REFERRAL IDENTITIES (5)             │
   ┌──────────┐    ┌──────────────────┐               │
   │campaigns │◄───│ referral_identities  │               │
   └────┬─────┘    │ (partner_id,     │               │
        │campaign_ │  program_id,     │               │
        │id        │  client_id,      │               │
        │          │  id_source,      │               │
        │          │  campaign_id)    │               │
        │          └────────┬─────────┘               │
        │                   │ referral_identity_id                │
        │                   ▼                          │
        │           REFERRALS (6)  ◄───────────────────┘
        │           ┌───────────┐   prospect_id
        │           │ referrals │  (created lazily, on first click)
        │           └─────┬─────┘
        │                 │ referral_id
        │  LANDING (10)    │            CRM LINKAGE (11)
        │  ┌────────────┐  │            ┌───────────────────┐
        └─►│  landing_  │  ├───────────►│ leads             │
           │experiences │  │            │ lead_assignments  │
           └────────────┘  │            │ lead_status_hist. │
   MARKETING ASSETS (9)    │            │ lead_notes        │
   ┌────────────────┐      │            │ executive_calls   │
   │marketing_assets│      │            └───────────────────┘
   └────────────────┘      │
                           ▼
                  ANALYTICS (12) — event-driven, LARGEST context
                  ┌─────────────────────────────────────────────┐
                  │ events (immutable) ── session_id ─► sessions │
                  │        └──────────── device_id  ─► devices   │
                  │ campaign_stats · daily_metrics  (rollups of  │
                  │ events; rebuildable, not authoritative)      │
                  └─────────────────────────────────────────────┘
```

**How to read it:** a `partner` runs one or more `programs`; a referrer's identity within a program is the raw `client_id` in their `gorefer.in/r/{client_id}` link; the **first click** lazily creates the `referral_identity`, a `referral` (linking identity → `prospect`), and a stream of immutable `events`; the CRM-linkage tables mirror the referral into Zoho's pipeline; the analytics context is derived from events.

---

## 5. Context 1 — Identity

**Purpose.** Authentication and authorization for **Admins and Executives only**. Customers do **not** log in in Sprint 1. Supports the bootstrap-admin and least-privilege model in `04` §7. Sprint 1 stays deliberately **simple / single-admin**: `users` (aka `admin_users`) and `user_sessions` (aka `admin_sessions`) hold one bootstrap super-admin — no self-service user provisioning UI, no multi-role management screen.

- **`users`** — id; email (unique); full_name; password_hash; role_id → roles.id; is_active; last_login_at; + audit + soft-delete. Indexes: `email` (unique), `role_id`.
- **`roles`** — id; name (unique: e.g. `super_admin`, `partner_admin`, `executive`); description; + audit. The seeded **bootstrap admin** is a `super_admin` forced to rotate credentials on first login (`04` §7.1).
- **`permissions`** — id; code (unique, e.g. `leads.view`, `campaigns.manage`); description. Join `role_permissions(role_id, permission_id)` for least privilege.
- **`user_sessions`** — id; user_id → users.id; token_hash; ip; user_agent; issued_at; expires_at; revoked_at. Indexes: `user_id`, `token_hash` (unique).
- **`audit_logs`** — id; user_id; action; entity_type; entity_id; before (JSONB); after (JSONB); ip; created_at. Append-only admin audit trail (distinct from Context 12 analytics events). Indexes: `user_id`, `(entity_type, entity_id)`, `created_at`.

**Relationships.** `users.role_id → roles.id`; `role_permissions` bridges roles↔permissions; every other table's `created_by/updated_by/deleted_by → users.id`.

---

## 6. Context 2 — Referral Programs

**Purpose.** A program is a company/product whose referrals GoRefer manages. Sprint 1: **Zerodha = exactly one row**. Provider-agnostic — no Zerodha-specific columns. (`Master` Addition 10, 8.)

- **`programs`** — id; partner_id → partners.id; name (e.g. `Zerodha`); display_name; status (`active`/`inactive`); logo_url; theme; brand_color; reward_description (the swappable "300 points + 10% brokerage" copy — single source, `04` §7.2/§7.6); terms_url; + audit + soft-delete. Indexes: `partner_id`, `status`, `name` (unique per partner).
- **`program_settings`** — id; program_id → programs.id; key; value (JSONB); + audit. Flexible per-program config (attribution window = 60 days, eligibility ≥3 referrals/12mo, feature toggles). Index: `(program_id, key)` unique.
- **`program_redirect_rules`** — id; program_id → programs.id; match_condition (JSONB); destination_url_template (e.g. `https://signup.zerodha.com/api/lead?c={partner_code}&r={referrer_client_id}`); priority; is_active; + audit. Drives the Redirect Engine's destination build (`04` §4.1). Index: `(program_id, priority)`.

**Configuration cascade (3-tier: central → global → user).** Config values resolve through three layers, each in its own table, most-specific-wins:
- **`config_central`** — id; key; value (JSONB); description; + audit. The product-wide baseline shipped with GoRefer (system defaults, immutable to tenants). Index: `key` (unique).
- **`config_global`** — id; tenant_id → tenants.id; key; value (JSONB); + audit. Per-tenant admin overrides of the central baseline. Index: `(tenant_id, key)` unique.
- **`config_user`** — id; tenant_id → tenants.id; user_id → users.id; key; value (JSONB); + audit. Per-user overrides of the global layer. Index: `(tenant_id, user_id, key)` unique.
A read resolves `config_user → config_global → config_central`, returning the first hit. Per-program tuning still lives in `program_settings`; the cascade governs cross-cutting config (compliance copy, feature flags, defaults).

**Relationships.** `programs.partner_id → partners.id`; `referral_identities.program_id`, `campaigns.program_id`, `landing_experiences.program_id`, `customers.program_id` all → `programs.id`.

---

## 7. Context 3 — Partners

**Purpose.** The external organization whose referral journeys GoRefer manages, and the home of the **Partner Credentials abstraction** (Client ID / Agent ID / Advisor Code). Sprint 1: **PIFS**, partner code `ZMPHZC`, NSE AP `AP2516003693`. (`Master` Additions 8, 15; `04` §10.)

- **`partners`** — id; name (`Passive Income Financial Solutions Pvt Ltd`); code (unique, e.g. `ZMPHZC`); credentials (JSONB — the Partner Credentials abstraction: `{ client_id, agent_id, advisor_code, nse_ap_no, sebi_reg_no }`, secrets referenced from a vault, not stored raw); website; status; + audit + soft-delete. Indexes: `code` (unique), `status`.
- **`partner_contacts`** — id; partner_id → partners.id; contact_type (`helpline`/`executive`/`billing`); name; mobile; email; is_primary; + audit. (Ashok's Prayagraj helpline lives here.) Index: `partner_id`.
- **`partner_branding`** — id; partner_id; logo_url; primary_color; secondary_color; footer_disclosure (the mandatory AP disclosure block, `04` §7.7); + audit. Index: `partner_id`.
- **`partner_domains`** — id; partner_id; domain (e.g. `gorefer.in`); is_primary; ssl_status; + audit. Supports the single-domain, `client_id`-in-path routing scheme (ADR-005) and future per-partner domains. Index: `domain` (unique).

**Relationships.** `partners` 1—* `programs`, `partner_contacts`, `partner_branding`, `partner_domains`.

---

## 8. Context 4 — Customers (minimal only)

**Purpose.** The existing Zerodha client who *refers* (the referrer). **Deliberately minimal** — GoRefer must not become a customer master. **NO PAN / Aadhaar / KYC / brokerage.** (`Master` Addition 10; `04` §1, §7.5.)

- **`customers`** — columns exactly:
  - `id`
  - `program_id` → programs.id
  - `partner_id` → partners.id
  - `client_id` (the referrer's Zerodha client ID, e.g. `DA1707`)
  - `mobile`
  - `email`
  - `first_name`
  - `last_name`
  - `eligibility_status` (referral eligibility, e.g. `eligible`/`not_eligible` — display only, source of truth is Zerodha)
  - `status` (`active`/`inactive`)
  - `last_sync` (TIMESTAMPTZ — when eligibility/status was last imported)
  - `eligibility_source` / `status_source` (`'zoho'` etc. — recorded source per §2)
  - + audit (`created_by`, `updated_by`, `version`, `created_at`, `updated_at`)
  - + soft-delete (`deleted_at`, `deleted_by`, `delete_reason`)
- **Indexes:** `(program_id, client_id)` unique (a client is unique within a program), `mobile`, `email`, `partner_id`, `status`.
- **Relationships.** `customers` 1—* `referral_identities` (optional link: a referral identity may have **no** customer, since referrers are open-ended and need not be one of Abhay's customers — ADR-001). A customer is an *external* person, **not** a GoRefer login (`users`). (`Master` Addition 8.)

---

## 9. Context 5 — Referral Identities (the heart)

**Purpose.** The identity of a referrer within a program, keyed by **`(partner, native-or-generated id, source)`**. For Zerodha the id **is the raw `client_id`** carried in `gorefer.in/r/{client_id}` — there is **no opaque token and no token→id mapping** (ADR-001). The row is **created lazily on the first click** (not pre-provisioned), after the `client_id` is format-validated. (`Master` Addition 10; `04` §4.1, §8.)

- **`referral_identities`** — columns exactly:
  - `id`
  - `partner_id` → partners.id  *(part of the identity key)*
  - `program_id` → programs.id
  - `client_id` (the referrer's **raw native id** — for Zerodha, the Zerodha `client_id` that appears directly in the path; **part of the identity key**)
  - `id_source` (`native` for Zerodha's `client_id`; `generated` for a future GoRefer-issued id — **part of the identity key**)
  - `token` (**nullable; FUTURE non-Zerodha partners only** — a GoRefer-generated referral id minted at referrer login when a partner exposes no reusable native id. **NULL for Zerodha**, which uses the native `client_id`. Not used in Sprint 1.)
  - `customer_id` → customers.id (nullable — set only if this referrer is also a known GoRefer customer; open-ended referrers may have none)
  - `campaign_id` → campaigns.id (nullable — which campaign delivered the link, when known)
  - `landing_page_id` → landing_experiences.id (nullable)
  - `status` (`active`/`disabled`)
  - `created_at` (the moment of first click — lazy creation)
  - + audit + soft-delete
- **Indexes:** **`(partner_id, client_id, id_source)` UNIQUE** (the identity key, resolved on every redirect), `program_id`, `campaign_id`, `customer_id`, `status`. (`token` UNIQUE partial index applies only to future non-null generated ids.)
- **Relationships.** `referral_identities` *—1 `partners`, `programs`; 0..1—1 `customers` (optional); *—1 `campaigns`, `landing_experiences`; 1—* `referrals`.

> **Identifier scheme — LOCKED (ADR-001).** Zerodha uses the **raw `client_id` in the path**; there is no opaque token and no `token → client_id` mapping table. The referrer record is created lazily on first click. The nullable **`token` column is reserved for FUTURE non-Zerodha partners** that need a GoRefer-generated id (minted at referrer login); it stays NULL for Zerodha.

---

## 10. Context 6 — Referrals (distinct from identities)

**Purpose.** The *act/instance* of a referral — one referral identity can generate many referrals over time. **Created lazily, on first click** (alongside the referral identity itself). (`Master` Addition 10; `04` §8.)

- **`referrals`** — id; referral_identity_id → referral_identities.id (**nullable** — a **partner-direct** journey and a **Zoho-imported off-platform conversion** may have no referrer identity, Gaps 1 & 3b); `source` (**enum: `referral_link` / `partner_direct` / `zoho_import`** — `partner_direct` is the `GET /open` no-`r=` path, Gap 1); prospect_id → prospects.id (nullable until the prospect identifies themselves); status (referral state machine: `created`→`shared`→`opened`→`landing_viewed`→`signup_started`→`signup_completed`→`confirmed`→`rewarded`); conversion_status (nullable — set only from a verified partner source); conversion_source (`'zoho'`); conversion_synced_at; **`credited_referrer`** (nullable — the single winning referrer's `client_id`; **set ONLY from Zoho**, never guessed from last redirect/click — single-winner, Gap 3); **`lead_disposition`** (nullable — the un/converted reason **mirrored from Zoho's disposition**, Gap 8); reward_status (nullable — **display only, Zerodha Console is the sole truth; no PIFS top-up / no GoRefer-computed reward**, Gap 4/7); **`first_click_at`** (nullable — first observed human click); **`lead_created_at`** (nullable — capture-first form submit); **`account_opened_at`** (nullable — the **true account-opening date from Zoho**, distinct from `conversion_synced_at`; **all conversion analytics run off this real date**, Gap 4b); created_at; completed_at (nullable); + audit + soft-delete.
- **Indexes:** `referral_identity_id`, `source`, `prospect_id`, `status`, `conversion_status`, `credited_referrer`, `account_opened_at`, `created_at`.
> **Zoho-imported conversions may have no click rows.** An off-platform account (walk-in / phone / Zerodha-direct later logged) arrives via the Zoho sync and **creates a `referral` with `source=zoho_import` and no `click`/`events` click rows** (Gaps 2, 3b). The opener→journey link is best-effort via the **GoRefer referral reference stamped on the Zoho lead**; single-winner credit is whatever **Zoho** names. **Attribution is never keyed by mobile** — the referrer is resolved/credited by **Zerodha client ID** (the raw `client_id`, ADR-001) and the opener by **Zerodha account ID** (see §12.3).
- **Relationships.** `referrals` *—1 `referral_identities`; *—1 `prospects`; 1—* `events` (via `referral_id`); 1—1/0..1 `leads` (CRM linkage).

---

## 11. Contexts 7–11 — Prospects, Campaigns, Marketing Assets, Landing Experiences, CRM

### 11.1 Context 7 — Prospects
**Purpose.** The person who may open an account (the "friend"). (`Master` Addition 10.)
- **`prospects`** — id; mobile; email; name; city; state; lead_source (`whatsapp_campaign`/`whatsapp_status`/`facebook`/`instagram`/`linkedin`/`direct_link`/`manual`); + audit + soft-delete. Indexes: `mobile`, `email`, `lead_source`.
> **Lead-schema conflict is OPEN.** Landing "Need Help" form captures Name/Mobile/**City** (3 fields); the WhatsApp bot captures Name/Mobile (2). `prospects` includes `city`/`state` as nullable to accommodate both — but decide the canonical required set before build. (`Master` §6.6 NOTE; `Build-Spec` §6.)

### 11.2 Context 8 — Campaigns
**Purpose.** An independent marketing initiative on any channel. (`Master` Addition 10.)
- **`campaigns`** — id; program_id → programs.id; channel (`whatsapp`/`status`/`facebook`/`instagram`/`linkedin`/`email`/`qr`/`poster`/`direct_link`); name; template (WATI/Meta template name for WhatsApp); status; starts_at; ends_at; + audit + soft-delete. Indexes: `program_id`, `channel`, `status`.

### 11.3 Context 9 — Marketing Assets (one table, all types)
**Purpose.** Every generated asset in a **single** table keyed by `asset_type` — no schema change to add a new type. (`Master` Addition 10.)
- **`marketing_assets`** — id; asset_type (`poster`/`qr`/`status`/`story`/`email`/`banner`/`flyer`/`video`); referral_identity_id (nullable); program_id; theme; language (`en`/`hi`); version; template; file_url; generated_by; + audit + soft-delete. Indexes: `asset_type`, `program_id`, `referral_identity_id`.

### 11.4 Context 10 — Landing Experiences
**Purpose.** The per-referral landing page shown before redirect (ADR-002: landing before redirect). "Experience," not "page" — may later be a WhatsApp Flow / PWA. (`Master` Addition 8, 10.)
- **`landing_experiences`** — id; program_id → programs.id; theme; headline; subheadline; cta; faq (JSONB); content_blocks (JSONB); status; + audit + soft-delete. Index: `program_id`, `status`.

### 11.5 Context 11 — CRM linkage
**Purpose.** Mirror the referral into the sales pipeline. **Zoho runs the pipeline** (`04` §3); these tables are GoRefer's *linkage/shadow* so the referral relationship stays joined to pipeline state, with account status imported from Zoho (recorded `source`). (`Master` Addition 10; `04` §4.3.)

**The erasable person/lead record.** `leads` (together with `prospects`, §11.1) is the **single erasable home of personal data** referenced by events (`events.person_ref_id`, §12.1). It holds name / phone / email and the visitor's **raw IP + derived city — both stored unhashed** (not hashed, not dropped), retention-limited and erasable on request. No PII copy exists anywhere in the immutable event log.
- **`leads`** — id; tenant_id; referral_id → referrals.id; prospect_id → prospects.id; zoho_lead_id (external key); raw_ip; city; status (`new`/`contacted`/`interested`/`kyc_started`/`account_opened`/`rejected`); status_source (`'zoho'`); status_synced_at; **`lead_disposition`** (nullable — the un/converted **reason mirrored from Zoho's disposition**, Gap 8); **`account_opened_at`** (nullable — **true open date from Zoho**, distinct from `status_synced_at`, Gap 4b); assigned_executive_id → users.id; + audit + soft-delete. Indexes: `referral_id`, `zoho_lead_id` (unique), `status`, `assigned_executive_id`.
- **`lead_assignments`** — id; lead_id → leads.id; executive_id → users.id; assigned_at; unassigned_at; + audit. Index: `lead_id`, `executive_id`.
- **`lead_status_history`** — id; lead_id → leads.id; from_status; to_status; changed_at; source; + audit. Append-only pipeline history. Index: `lead_id`, `changed_at`.
- **`lead_notes`** — id; lead_id → leads.id; author_id → users.id; note; created_at; + soft-delete. Index: `lead_id`.
- **`executive_calls`** — id; lead_id → leads.id; executive_id → users.id; called_at; outcome; duration_sec; notes; + audit. Index: `lead_id`, `executive_id`, `called_at`.

---

## 12. Context 12 — Analytics (event-driven; the largest context)

**Purpose.** Derive all analytics from **immutable events**, not counters (ADR-004). This context holds the biggest object in the system and is the storage expression of `04` §6, §8. Rows here are created **lazily, on first click**. (`Master` Additions 8, 10; `04` §8.)

### 12.1 `events` — the immutable event log (largest table)
Columns exactly:
- `id`
- `event_type` (e.g. `ReferralLinkOpened`, `LandingViewed`, `RedirectInitiated`, `PosterDownloaded`, `SignupCompleted` — vocabulary in `04` §6)
- `user_type` (`customer`/`prospect`/`executive`/`admin`/`anonymous`)
- `user_id` (nullable — polymorphic by `user_type`)
- `referral_id` → referrals.id (nullable)
- `campaign_id` → campaigns.id (nullable)
- `session_id` → sessions.id (nullable)
- `device_id` → devices.id (nullable)
- `country`
- `state`
- `person_ref_id` (nullable → the **erasable person/lead record**) — events reference a person **by id only**. **No PII** (name/phone/email/raw IP/city) is ever written to an event or its `metadata`; the raw IP and derived city live only on the erasable record (§11.5, unhashed and erasable), enforced by a **CI rule that fails the build on any PII field in event metadata**.
- `user_agent`
- **`visitor_id`** — the first-party **cookie** visitor identity (`gr_vid`) that stitches repeat hits into one journey (Gap 11). On lead submit, the **mobile becomes the authoritative** person key; unique visitor counts from this field are **approximate**, never asserted as exact humans.
- **`is_bot`** (BOOLEAN, default false) — set true when the **user-agent matches the known bot/preview list** at the edge (WhatsApp/facebookexternalhit etc.), Gap 16. Bot rows are stored for audit but **excluded from human counts**.
- **`is_confirmed_human`** (BOOLEAN, default false) — set true **only after the JS-confirmation beacon fires** (`POST /api/click/confirm`, `06` §4.3). A click counts as human **only** when this is true (Gap 16).
- `timestamp` (TIMESTAMPTZ, default now())
- `metadata` (**JSONB** — anything extra, no schema change; **must never contain PII** — CI-enforced)

**Click confidence — a binary gate, not a scale.** A click is either a **confirmed human** (`is_bot=false` AND `is_confirmed_human=true`) or it is not; there is **no three-level confidence field**. `is_bot` and `is_confirmed_human` together are the whole gate — bot/preview and unconfirmed hits are excluded from human counts so referrals are never over-reported. (`04` §7.6, §11.)

**Immutability:** append-only. No `updated_at`, no soft-delete — events are never edited or deleted; corrections are new events.
**Indexes:** `event_type`, `referral_id`, `campaign_id`, `session_id`, `device_id`, `visitor_id`, `person_ref_id`, `is_bot`, `is_confirmed_human`, `timestamp`, and a GIN index on `metadata`. Time-partitioned by `timestamp` for scale (`04` §8).

### 12.2 Supporting analytics tables
- **`sessions`** — id; session_key (unique); first_seen_at; last_seen_at; device_id → devices.id; entry_referral_id; country/state/city. Indexes: `session_key` (unique), `device_id`.
- **`devices`** — id; device_key (unique); device_type (`mobile`/`desktop`/`tablet`); os; browser; first_seen_at. Indexes: `device_key` (unique), `device_type`.
- **`campaign_stats`** — id; campaign_id → campaigns.id; stat_date; sent; delivered; read; clicked; leads; conversions (all rollups). **Rebuildable** from `events` (`04` §5.2, §6). Index: `(campaign_id, stat_date)` unique.
- **`daily_metrics`** — id; metric_date; program_id; links_created; links_opened; landing_views; redirects; leads; accounts_opened. Pre-aggregated so dashboards read cheap rows. Index: `(metric_date, program_id)` unique.

**Relationships.** `events` *—1 `sessions`, `devices`, `referrals`, `campaigns`. `campaign_stats`/`daily_metrics` are derived rollups, not authoritative — always reconstructable by replaying `events`.

**Rollups recomputed via a dirty-days set.** The rollup/summary tables (`campaign_stats`, `daily_metrics`, and the conversion rollups over §12.3) are **not** updated inline. Any add/fix/removal — a new event, a Zoho conversion upsert, a reversal/tombstone, a true-open-date correction — records the affected **day (and month)** into a **dirty-days set**; background workers recompute exactly those periods. This keeps rollups consistent after out-of-order or corrected data (e.g. a conversion landing in its true prior period) with no full rebuild.

### 12.3 Conversions, sharing, and sync-health

- **`conversions`** — the account-opening record mirrored from Zoho (an off-platform conversion may exist here with **zero clicks**). Columns: `id`; `tenant_id`; `program_id` → programs.id; **`opener_zerodha_account_id`** (the opener's Zerodha account ID — the conversion's natural key); `zoho_lead_id` (**fallback key** when the account ID is not yet present); `opener_name`; **`referrer_client_id`** (the credited referrer's raw Zerodha `client_id`, ADR-001 — how the referrer is resolved/credited); `referral_id` → referrals.id (nullable — best-effort link via the GoRefer referral reference); **`account_opened_at`** (the **TRUE Zoho open date**, distinct from `synced_at`; all conversion analytics run off this); `status`; **`source_origin`** (where each status value came from, e.g. `zoho`) and **`status_changed_at`** (recorded on **every** status change); `is_reversed` (BOOLEAN, default false — set by a reversal/tombstone, never by inline mutation); `synced_at`; + audit.
  - **Unique key = `opener_zerodha_account_id`** (falling back to `zoho_lead_id` when the account ID is absent); ingestion is **upsert-on-key** (idempotent re-imports update in place). Index: `opener_zerodha_account_id` (unique), `zoho_lead_id` (unique), `referrer_client_id`, `account_opened_at`, `(tenant_id, program_id)`.
  - **NO mobile** is stored on conversions. **NO provisional/final flag** — a conversion is what Zoho holds as-of-sync; a **removal is expressed as a reversal/tombstone event** (setting `is_reversed`, dirtying the affected day/month), never a silent delete.
- **`share_events`** — id; tenant_id; referral_id → referrals.id (nullable); referral_identity_id (nullable); **`channel`** (`whatsapp`/`facebook`/`instagram`/`linkedin`/`copy_link`/`qr`/`other`); shared_at; + audit. Records a share action and the channel it went out on. Index: `referral_id`, `channel`, `shared_at`.
- **`zoho_sync_idempotency`** — id; tenant_id; **`dedupe_key`** (unique — the Zoho payload/idempotency key); processed_at; result; + audit. Guards against double-processing the same Zoho record on retry/replay. Index: `dedupe_key` (unique). A **referrer-B attempt on a de-duplicated lead** (a second referrer trying to claim an already-captured lead) is **recorded as an event**, not a competing conversion row — single-winner credit stays with whatever Zoho names.
- **Sync health.** The last good Zoho sync and its state are tracked so operators can see staleness: a **`last_successful_zoho_sync_at`** timestamp plus a **sync-health state** (e.g. `healthy`/`degraded`/`stalled`), surfaced to the admin dashboard.

---

## 13. Cross-References

- **How these tables are used at runtime — orchestrator model, the click→event→landing→redirect flow, the Zoho→GoRefer status sync, the lazy-journey scaling argument, the event bus, and the security/DPDP posture:** [`04-System-Architecture.md`](./04-System-Architecture.md).
- **API contracts over this schema — `client_id` validation/resolution, redirect endpoint, lead creation into Zoho, WATI dispatch:** [`06-API-Specification.md`](./06-API-Specification.md).
- **Vision, locked decisions, and the OPEN identifier/domain/lead-schema questions this schema flags:** `GoRefer-Master-SourceOfTruth-from-ChatGPT.md`, `GoRefer-Build-Spec-Cowork-Decisions.md`.

---

*GoRefer — 05. Database Design. Compiled 2026-07-04. Owner: Abhay Kumar Maurya (PIFS, Zerodha Authorised Person). PostgreSQL, 12 bounded contexts, event-driven, workflow-not-ownership.*
