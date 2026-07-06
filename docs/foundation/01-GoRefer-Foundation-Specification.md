# GoRefer Foundation Specification
**Version 1.0 (Draft) — Document 1 of the GoRefer Architecture Repository**
_Being assembled incrementally; this is Part 1 (~first 10%)._

## Revision History
| Version | Date | Author | Remarks |
|---|---|---|---|
| 0.1 | Initial Draft | Abhay Kumar Maurya / Passive Income Financial Solutions (PIFS) — drafted with AI assistance | Foundation specification created |
| 1.0 | Pending | After Architecture Review | Frozen for implementation |

## Status
Working Draft. This document is the single source of truth for the GoRefer platform. Every future design decision, implementation, enhancement, integration, and architecture review shall reference this document.

## Purpose
Defines: Product Vision, Business Vision, Architecture Principles, Functional Requirements, Non-Functional Requirements, Business Rules, User Journeys, System Behaviour, Future Expansion Strategy. It intentionally avoids implementation details (those belong in later documents).

## Intended Audience
Product Owners, Architects, Software Engineers, Claude Code, Gemini, Grok, Future Contributors.

## What is GoRefer?
GoRefer is a Referral Management & Referral Intelligence Platform. It enables users to manage, share, and track referral links from multiple businesses using one unified platform. Unlike traditional referral systems that only generate links, GoRefer focuses on the complete referral lifecycle: referral creation, sharing, tracking, analytics, intelligence, conversion tracking, and future reward tracking.
GoRefer does NOT own referral programs — it integrates with existing referral programs offered by partner businesses. Examples: Zerodha, insurance companies, mutual fund platforms, property brokers, loan providers, credit card companies, affiliate programs, any future referral-enabled business.

## Vision Statement
To become the most trusted platform for managing, sharing, and analysing referral programs across multiple industries through one intelligent ecosystem.

## Mission Statement
Help every individual maximize the value of their referral relationships while providing businesses with a scalable and extensible referral management platform.

## Product Philosophy (5 core principles)
1. **Build once, scale forever** — every architectural decision today must support future referral programs without redesign.
2. **Expose only today's capabilities** — never show unfinished functionality; no "Coming Soon," placeholder menus, or disabled buttons; users only see features they can actually use.
3. **Measure everything possible** — capture every observable business event (link created, link shared, link clicked, landing page viewed, redirect initiated, lead created, contact converted). If GoRefer can observe it, record it.
4. **Never fabricate data** — GoRefer only reports facts it can verify. It CAN verify click timestamp and redirect timestamp. It CANNOT independently verify whether Zerodha completed KYC or account approval — those must originate from external systems (e.g. Zoho updates).
5. **Configuration over code** — adding a future referral program should require configuration wherever possible, not application code changes.

## Product Scope
**Sprint 1 scope:** only ONE referral program enabled — Partner: Zerodha. Although only Zerodha is active, the architecture shall support multiple future referral programs.
**Sprint 1 includes:** Public Website, Admin Dashboard, Referral Tracking, Referral Analytics, WATI Integration, Zoho CRM Integration, Referral Landing Pages, Redirect Tracking, Referral Journey Timeline.
**Sprint 1 explicitly excludes:** Customer Login, Public Registration, Self-Service Dashboard, Reward Calculations, Payment Integrations, Mobile Application, Multi-language Support.

## Business Goals
1. Increase Zerodha referrals.
2. Increase referral conversion rate.
3. Reduce manual follow-up.
4. Provide visibility into referral performance.
5. Create reusable architecture for future referral businesses.

## Success Metrics (Sprint 1 succeeds if)
Personalized referral links are generated correctly; WATI campaigns successfully distribute referral links; click tracking functions reliably; referral journeys are recorded; Zoho CRM synchronization works; admin dashboard displays meaningful analytics; architecture requires minimal changes to onboard a second referral partner.

## User Types (actors)
1. **Platform Administrator** — current: one bootstrap administrator (Abhay). Responsibilities: configure referral programs, monitor analytics, review referral journeys, manage integrations, review campaign performance.
2. **Existing Customer (Future)** — a customer who has joined one or more referral programs. NOT enabled in Sprint 1 (architecture only).
3. **Referral Visitor** — a person who clicks a referral link; no authentication required.
4. **External Systems** — WATI, Zoho CRM, Zerodha, future partners; interact with GoRefer via APIs, redirects, or synchronization.

## High-Level Product Flow
1. A referral program (e.g. Zerodha) is configured in GoRefer.
2. A unique referral link is associated with a participant for that program.
3. The participant shares the link (WhatsApp, social media, email, QR code).
4. A visitor clicks the referral link.
5. GoRefer records the click and starts a referral journey.
6. The visitor is shown an optional landing page (or redirected immediately, depending on configuration).
7. The visitor is redirected to the partner's official referral URL.
8. Subsequent business events (lead creation, account opening) are synchronized from Zoho CRM.
9. The admin dashboard displays the complete referral lifecycle.

---
_End of Part 1 (~10% of the Foundation Specification). Subsequent parts will cover the complete referral lifecycle, business rules, user journeys, and all functional requirements._

---

# Part 2 — Referral Lifecycle, Journeys, Requirements, Rules & Compliance

> _Part 1 above (Vision, Philosophy, Scope, Actors, High-Level Flow) is frozen. Part 2 completes the Foundation Specification. Requirement IDs (REQ-xxx), business-rule IDs (BR-xxx), non-functional IDs (NFR-xxx), and acceptance-criteria IDs (AC-xxx) are **stable**: once assigned they are never renumbered. New items get the next free number; retired items are marked `DEPRECATED`, never reused._

## 10. The Referral Lifecycle (Canonical State Model)

The referral lifecycle is the spine of GoRefer. Every downstream document (database, API, UI, analytics) derives from it. The lifecycle records **only what GoRefer can observe or receive from a trusted source**. It never infers or fabricates a state (Product Philosophy #4).

### 10.1 The states

| # | State | Meaning | Who/what sets it | GoRefer-verifiable? |
|---|-------|---------|------------------|---------------------|
| S0 | **Created** | A permanent referral link exists for a (user, program) pair. No visitor activity yet. | GoRefer, lazily on first need | Yes |
| S1 | **Shared** | The referrer distributed the link through a channel (WhatsApp, Status, social, email, QR). Recorded when a share action is observable. | GoRefer / channel event | Partially (only observable shares) |
| S2 | **Clicked** | A visitor opened the referral link. Every click is stored as a **separate event** with a confidence classification. | GoRefer redirect layer | Yes |
| S3 | **Landing Viewed** | The visitor was shown the GoRefer landing experience (if landing is enabled for the program). | GoRefer | Yes |
| S4 | **Redirected** | GoRefer handed the visitor off to Zerodha's official public lead URL. **This is the last state GoRefer can independently verify.** | GoRefer | Yes |
| S5 | **Lead Created** | A lead was captured (name + mobile) via GoRefer's own PIFS-branded capture form, or a lead record was created in Zoho. | GoRefer capture form / Zoho | Yes (for GoRefer-captured leads) |
| S6 | **Contact / Account** | The prospect became a Zoho Contact and/or a Zerodha account was opened. | **Zoho only** (synced) | **No — external truth** |
| S7 | **[Reward — FUTURE]** | Reward points / brokerage share credited to the referrer. Out of Sprint 1 scope; architecture-only. | **Zoho / Zerodha only** (synced) | **No — external truth** |

### 10.2 The critical verification boundary

```
   GoRefer verifies up to here ──────────────┐
                                             ▼
Created → Shared → Clicked → Landing Viewed → Redirected  │  Lead Created → Contact/Account → [Reward]
                                                          │
                          external truth (Zoho / Zerodha) ┴────────────────────────────────────►
```

**Account opening and reward come ONLY from Zoho and are NEVER fabricated by GoRefer.** GoRefer can prove a visitor was *redirected* to Zerodha; it cannot prove — and must never claim — that KYC completed, an account opened, or a reward was paid. Those states appear in GoRefer only after a trusted Zoho sync writes them (see REQ-021). This is a direct consequence of the live-tested fact that Zerodha's link is lead-capture-only, reCAPTCHA-gated, ends at "thanks," and is completed by a human (Ashok) off-platform.

### 10.3 State transitions and events

Every state change emits an immutable event (event-sourced; store events, not counters). Ordering is not strictly linear: a visitor may click without a landing page (S2→S4 when landing is disabled), may click many times (multiple S2 events on one journey), or may never proceed past S4. A lead (S5) can also originate from the GoRefer capture form *before* any redirect. The lifecycle is therefore a **directed graph with S4 as the verification frontier**, not a rigid pipeline.

| From | To | Trigger event |
|------|----|---------------|
| — | S0 Created | `ReferralLinkCreated` (lazy) |
| S0 | S1 Shared | `ReferralShared` (observable share only) |
| S0/S1 | S2 Clicked | `ReferralClicked` (one per click, with confidence) |
| S2 | S3 Landing Viewed | `LandingViewed` (only if landing enabled) |
| S2/S3 | S4 Redirected | `RedirectInitiated` |
| any | S5 Lead Created | `LeadCreated` (GoRefer form submit: name + mobile) |
| S5 | S6 Contact/Account | `ZohoContactSynced` / `ZohoAccountStatusSynced` (from Zoho only) |
| S6 | S7 Reward | `RewardSynced` (FUTURE, from Zoho/Zerodha only) |

---

## 11. Detailed User Journeys

### 11.1 Journey A — Managed customer (existing PIFS/Zerodha client), reached via WATI

1. PIFS sends a Meta-approved WATI WhatsApp template to an existing, opted-in client. The template carries the client's **personal referral link** and the **PIFS partner link** (both always present).
2. The client taps their personal referral link → GoRefer records a **click event** (confidence classified) and, if enabled, shows the landing experience.
3. The client shares the link with a friend (WhatsApp forward, Status, social) — recorded as a **Shared** event where observable.
4. Alternatively (and the **recommended primary path**), the client uses "Share Friend Name + Mobile": GoRefer captures the friend's name + mobile in a PIFS-branded form, saves the lead first, and alerts Ashok. The link path stays available as the **secondary** path.
5. GoRefer never depends on the client understanding referral-link mechanics; the assisted path always leads.

### 11.2 Journey B — Referral visitor (the friend / prospect)

1. Visitor opens a GoRefer referral link (`gorefer.in/r/{client_id}`). **No authentication is required.**
2. GoRefer creates the journey **lazily on this first click** (no tracking record existed before), stores the click as a separate event with a confidence classification (default `Unknown`), and captures available signals (timestamp, referer, user-agent, and IP handled per the DPDP rules in NFR-006).
3. If the program has a landing experience enabled, the visitor sees a PIFS-branded page ("Your friend invited you… Open your Zerodha account", benefits, "Open Account", "Need Help?"). The page is **not** a Zerodha look-alike.
4. On "Open Account", GoRefer records a **RedirectInitiated** event and redirects the real human browser to Zerodha's official public lead URL (`https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}`).
5. On "Need Help?" (or via the assisted flow), the visitor submits name + mobile → **LeadCreated** in GoRefer/Zoho → the three WATI messages fire (to Ashok, to the new person, and to the referrer only if the referrer's phone is resolvable from Zoho).
6. Ashok calls and helps complete Zerodha account opening (the human satisfies reCAPTCHA legitimately). GoRefer's view of this journey **stops at Redirected/Lead Created**; account status appears later only via Zoho sync.

### 11.3 Journey C — Administrator

1. Admin authenticates via the **admin-only login** (bootstrap admin credentials from environment variables; no public registration).
2. Admin lands on the dashboard: aggregate metrics (links, clicks by confidence, landing views, redirects, leads, and Zoho-sourced account status).
3. Admin opens the **Referral Explorer** to filter journeys by partner, date range, customer/referrer, and status; drills into a single journey's full event timeline.
4. Admin reviews campaign performance, configures the (single, Sprint-1) Zerodha program, and manages integrations (WATI, Zoho) — all behind **feature flags** so nothing half-built is exposed. There is **no "Coming Soon."**

---

## 12. Functional Requirements (REQ-xxx)

### 12.1 Referral links & identifiers

- **REQ-001** Each referrer has **exactly one permanent referral link per program**, carrying their **raw Zerodha `client_id`** in the path. The canonical public form is **`gorefer.in/r/{client_id}`** (e.g. `gorefer.in/r/RJ4521`). The link is stable for the life of the (referrer, program) relationship. There is **no opaque token and no token→id mapping table** (ADR-001).
- **REQ-002** The path segment **is** the referrer's Zerodha `client_id`. At redirect time GoRefer injects the partner code **server-side** and builds the official destination `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}`. The `client_id` is already public (it appears in Zerodha's own `r=` links); the **partner code `c=ZMPHZC` is never exposed** in the shared link and is added server-side (supports R6). _Note: for future non-Zerodha partners that expose no reusable native ID, GoRefer will generate a referral ID at referrer login — a forward-looking capability, not Sprint 1 (ADR-001)._
- **REQ-003** Link creation is **lazy**: GoRefer does **not** create a tracking/journey record until the **first click** on that link (or the first lead capture). No pre-provisioned empty journeys.

### 12.2 Click & event capture

- **REQ-004** Every click is stored as a **separate event** (never an incremented counter), with timestamp, the referrer `client_id` from the link, channel/UTM signals where present, user-agent, and IP (stored per NFR-006).
- **REQ-005** Every click event carries a **confidence classification** describing how reliably it maps to a real human referral click. Default classification is **`Unknown`**. Other classifications (e.g. `Likely-Human`, `Likely-Bot`, `Duplicate`) may be assigned by later logic; the schema must allow reclassification without data loss.
- **REQ-006** All observable business events are recorded (`ReferralLinkCreated`, `ReferralShared`, `ReferralClicked`, `LandingViewed`, `RedirectInitiated`, `LeadCreated`, and the Zoho-sourced `ZohoContactSynced` / `ZohoAccountStatusSynced`). Events are **append-only and immutable**.

### 12.3 Landing & redirect

- **REQ-007** For programs with landing enabled, GoRefer shows a **PIFS-branded landing experience** before redirect, recording a `LandingViewed` event. For programs with landing disabled, GoRefer redirects immediately after the click event.
- **REQ-008** On the visitor's explicit action ("Open Account"), GoRefer records `RedirectInitiated` and redirects the **real human browser** to Zerodha's **official public** `api/lead` URL with `c=ZMPHZC` and `r={client_id}`. GoRefer **never** auto-submits or programmatically completes Zerodha's form (see BR-005).

### 12.4 Lead capture & CRM

- **REQ-009** GoRefer provides its **own PIFS-branded capture form** ("Passive Income Financial Solutions — open your Zerodha account"). On submit of **name + mobile**, GoRefer creates a lead (`LeadCreated`) and saves it **first** in GoRefer's own store so the lead is never lost, even if the person abandons Zerodha. _Canonical lead schema (whether "City" is required) is an OPEN decision inherited from the source docs; the mandatory minimum is name + mobile._
- **REQ-010** On lead creation, GoRefer triggers the **three WATI messages** via Meta-approved templates: (a) alert to Ashok, (b) warm utility-style notice to the new person naming the referrer + a `r=`-bearing continue link, (c) thank-you to the referrer **only if** the referrer's phone is resolvable from Zoho. Message (b) must be utility-style, not a marketing blast (see BR-008).
- **REQ-011** GoRefer writes/reconciles the lead to **Zoho CRM** (lead destination — Zoho, WATI, or both — is an OPEN decision; the requirement is that a durable CRM record exists and Ashok is alerted instantly).

### 12.5 Admin, dashboard & explorer

- **REQ-012** GoRefer provides an **admin dashboard** showing aggregate lifecycle metrics: links created, clicks (broken down by confidence classification), landing views, redirects, leads, and Zoho-sourced account status.
- **REQ-013** GoRefer provides a **Referral Explorer** to list and filter referral journeys by **partner, date range, customer/referrer, and status**, with drill-down into a single journey's complete, ordered event timeline.
- **REQ-014** The dashboard **distinguishes GoRefer-verified states (≤ Redirected) from externally-sourced states (Contact/Account/Reward)** visually, so no one mistakes a redirect for an opened account.

### 12.6 Platform, access & configuration

- **REQ-015** GoRefer serves a **public marketing website** (no auth) and an **admin-only authenticated area**. There is **no public registration** and **no customer login** in Sprint 1.
- **REQ-016** The **bootstrap administrator** is provisioned from **environment variables** (no seed user in code, no public sign-up path to admin).
- **REQ-017** All not-yet-shippable capability sits behind **feature flags**; the UI exposes **only features that actually work**. **No "Coming Soon", no placeholder menus, no disabled buttons** (Product Philosophy #2).
- **REQ-018** Adding a **new referral partner** must be achievable through **configuration** (program record: name, display name, logo, theme, brand color, landing template, redirect strategy, reward description, T&C, active flag) — **no partner-specific application code** (Product Philosophy #5, "Engines not pages").

### 12.7 Zoho synchronization (external truth)

- **REQ-019** GoRefer **reads** account/contact status from Zoho and reflects it on the corresponding journey. GoRefer must **never** synthesize `Contact/Account` or `Reward` states from its own click/redirect data.
- **REQ-020** Zoho sync is **idempotent and auditable**: each sync records its source, timestamp, and the field(s) it changed; re-running a sync produces no duplicate state.
- **REQ-021** Externally-sourced states (S6, S7) are written **only** by the Zoho sync path and are clearly labelled in storage and UI as **externally sourced** (traceable to the sync that set them).

---

### 12.8 Future / Out-of-Sprint-1 requirements (DEFERRED — not in Sprint 1)

> _These requirements are **explicitly out of Sprint 1 scope**. They are recorded here so the architecture stays forward-compatible, but Claude Code / any implementer **must not** build them in Sprint 1. IDs in the `REQ-Fxx` range denote deferred/future requirements._

- **REQ-F01 Stale-lead auto-nudge (DEFERRED — Sprint 2+).** When a GoRefer-sourced lead ages without converting (e.g. approaching Zerodha's 60-day attribution window, see BR-003), GoRefer **automatically** sends a WhatsApp reminder to the prospect via **Wati** nudging them to complete account opening.
  - **Sprint 1 behaviour (locked):** stale-lead follow-up is **owned by Zoho** (Zoho is the source of truth for lead status and follow-up). GoRefer only shows a **read-only aging flag** derived from GoRefer's own timeline data. This aging flag is **GoRefer-derived, not a Zoho override** — GoRefer never writes lead status back to Zoho and never overrides Zoho (BR-006, REQ-019).
  - **Future behaviour (REQ-F01):** GoRefer moves from passive aging flag to an **active stale-lead WhatsApp nudge via Wati**.
  - **Dependencies / guardrails:** deferred until the **WATI opt-in / delivery-dedup fix** (the ~33% delivery-failure item) lands first. Any nudge **must respect Meta opt-in rules** — a warm, **utility-style** message, never a marketing blast (see BR-008). Zoho remains the source of truth; the nudge is additive and must never override or contradict Zoho lead status.

---

## 13. Non-Functional Requirements (NFR-xxx)

- **NFR-001 Mobile-first.** All visitor-facing surfaces (referral link redirect, landing experience, capture form) are designed mobile-first; the dominant channel is WhatsApp on phones. Landing/redirect must feel instant on a mid-range Indian Android device on 4G.
- **NFR-002 Performance.** The redirect path (click → event stored → redirect) must add negligible latency to the visitor's hop to Zerodha; event persistence must not block the redirect (write-through/async acceptable as long as no event is silently dropped).
- **NFR-003 Security.** Admin area protected by authentication; bootstrap admin from env vars (REQ-016). Secrets (WATI bearer token, Zoho credentials) live in a secret store / environment — **never hardcoded** (the current hardcoded WATI JWT in Zoho Deluge is a known debt to avoid repeating). No auto-submission of third-party forms.
- **NFR-004 Privacy / DPDP.** GoRefer processes personal data (name, mobile, click IP). Comply with India's DPDP Act: collect the minimum needed, state purpose, and **store IP carefully** — treat it as personal data (restrict access, define retention, avoid unnecessary exposure in logs/UI). Honour opt-out signals from Zoho where available.
- **NFR-005 Scalability.** Event-sourced, append-only design; multi-partner architecture from day one even though only Zerodha is active. Adding partners is configuration, not re-architecture.
- **NFR-006 IP handling (specific).** The click IP is captured for confidence classification and abuse detection only. It must be access-controlled, retained no longer than needed, and never displayed to non-admin users. Store the raw IP + city as PII in a separate erasable record (no hashing — hashing IPv4 is not real anonymization); keep it admin-only, purged with unconverted prospect PII after 12 months and erasable on request (see ADR-020 as amended).
- **NFR-007 Auditability.** Every state change and every external sync is traceable to its source and timestamp (immutable event log + sync audit). The admin can reconstruct any journey exactly.
- **NFR-008 Configuration-over-code.** New partners, landing templates, and redirect strategies are data/config; engines (Redirect, Landing, Campaign, Notification, Poster) contain no partner-specific branches.

---

## 14. Business Rules (BR-xxx)

- **BR-001 Dual-code attribution.** Every referral destination URL must carry **both** `c=ZMPHZC` (credits PIFS as AP for ongoing brokerage) **and** `r={client_id}` (credits the referring client under Zerodha Refer & Earn). A plain link with only `c=ZMPHZC` credits the partner alone.
- **BR-002 Referrer credit source.** The `r=` value is the **referrer's Zerodha client_id**, taken directly from the `gorefer.in/r/{client_id}` path (no lookup). `c=ZMPHZC` is constant for PIFS and injected server-side. The `client_id` is visible in the link (already public); `c=ZMPHZC` is never exposed in the shared GoRefer link.
- **BR-003 Attribution window.** A referred account must open **within 60 days** of the referral. GoRefer records timestamps but does not enforce Zerodha's window; it must not claim attribution it cannot prove.
- **BR-004 Prior-registration voids mapping.** If the prospect had already registered with Zerodha before using the link, the referral mapping does not apply. GoRefer must not assert a reward for such cases.
- **BR-005 reCAPTCHA reality — never auto-submit.** Zerodha's `api/lead` form is a **lead-capture form that ends at "thanks," is reCAPTCHA-gated, and has editable code fields.** GoRefer **must not** auto-submit or script it. The only compliant path is redirecting a **real human**, who is then assisted by Ashok to complete account opening. Code-swap on Zerodha's editable form is a residual, un-preventable risk (mitigated by a hidden default in our link).
- **BR-006 Verification boundary.** GoRefer independently verifies **only up to Redirected**. `Contact/Account` and `Reward` come **only** from Zoho sync and are never fabricated (see REQ-019/021).
- **BR-007 Lead-first.** On any capture, save the lead in GoRefer/Zoho **before** handing off to Zerodha, and alert Ashok instantly. The lead must survive Zerodha abandonment.
- **BR-008 Warm first contact.** The first WATI message to a lead who did **not** personally opt in (referrer submitted their details) must be a **warm, utility-style notice naming the referrer** — never a marketing blast — to protect the WhatsApp business number from Meta throttling.
- **BR-009 No clone.** GoRefer's forms and landing pages must be clearly **PIFS-branded** and must **not** clone or impersonate Zerodha's signup page (misrepresentation risk under NSE/COMP/55482).
- **BR-010 Referrer notification is best-effort.** The thank-you to the referrer fires **only** when the referrer's phone is resolvable from Zoho; for open-ended referrers known only by `client_id`, no message is sent.
- **BR-011 Single swappable incentive claim.** The "10% brokerage + 300 points" wording is kept in **one** configurable place so it can be pulled instantly if the regulatory position changes (see §15).

---

## 15. Compliance (MANDATORY)

> This section is a **hard gate**. Nothing publishes until it passes. (The origin ChatGPT doc omitted compliance entirely; it is mandatory here.)

### 15.1 Mandatory AP disclosure block

Must appear, verbatim, on **every owned channel and public asset** (website, landing pages, posters, WATI templates, emails, bios):

```
Zerodha Broking Ltd.: SEBI Registration no.: INZ000031633 | Passive Income Financial Solutions Private Limited | NSE AP reg. no.: AP2516003693
```

A market-risk warning (min font size 10) must accompany investment-related assets: "Investments in securities market are subject to market risks, read all the related documents carefully before investing." If brokerage rates are mentioned: "Brokerage will not exceed the SEBI prescribed limit."

### 15.2 Incentive claim — LIVE but REVOCABLE

The "**10% of brokerage + 300 reward points**" claim is **currently permitted but revocable**:

- **NSE/INSP/63425 (14-Aug-2024)** banned non-AP referrer brokerage-sharing.
- **NSE/INSP/66284 (24-Jan-2025)** put that ban **IN ABEYANCE** (paused, not repealed); interim regime reverts to **NSE/INSP/43824 (11-Mar-2020)**, which permits brokerage-sharing referral. Zerodha relaunched Refer & Earn on these terms.
- **Implication:** if NSE reinstates the ban, all content claiming 10% becomes non-compliant. Per **BR-011**, this wording lives in a single, swappable place.

### 15.3 Advertising gates

- All public assets must pass the **NSE Code of Advertisement (NSE/COMP/55482)** and the **SEBI Feb-2026 social-media disclosure circular** (HO/(79)2026-MIRSD-PODMMC, 26-Feb-2026, effective 1-May-2026).
- **Every public asset must pass Abhay's `zerodha-ap-social-media-compliance` skill review before publishing — this is a non-negotiable pre-publish gate.**
- **GoRefer's own forms and pages must NOT clone or impersonate Zerodha's signup page** (BR-009).
- Prohibited: superlatives (best/No.1/lowest/leading), income projections / assured returns, NSE logo, any MCX claim, PIFS-funded incentives on top of Zerodha's program, paid ads pointing at affiliate links, public-forum spam of affiliate links.

---

## 16. Acceptance Criteria (AC-xxx)

Sprint 1 is accepted when all of the following hold (mapped to the Success Metrics in Part 1 §Success Metrics):

- **AC-001** A permanent, correct personalized referral link (`gorefer.in/r/{client_id}`) is generated for a user and resolves to `signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}` with both codes intact. _(REQ-001, REQ-002; Metric: links generated correctly.)_
- **AC-002** A WATI campaign successfully distributes referral links to opted-in recipients, with delivery verified from WATI's terminal status (not just HTTP 200). _(Metric: WATI campaigns distribute links.)_
- **AC-003** Every click is recorded as a separate event with a confidence classification (default `Unknown`), reliably, before redirect. _(REQ-004, REQ-005; Metric: click tracking reliable.)_
- **AC-004** A complete referral journey (Created → … → Redirected, plus any Lead Created) is recorded and viewable as an ordered event timeline. _(REQ-006, REQ-013; Metric: journeys recorded.)_
- **AC-005** Zoho synchronization writes `Contact/Account` status onto the correct journey, clearly labelled as externally sourced; no such state is ever fabricated by GoRefer. _(REQ-019/021, BR-006; Metric: Zoho sync works.)_
- **AC-006** The admin dashboard and Referral Explorer display meaningful analytics and support filtering by partner, date, customer/referrer, and status. _(REQ-012/013; Metric: meaningful analytics.)_
- **AC-007** A second referral partner can be onboarded via configuration only, with no partner-specific application code. _(REQ-018, NFR-008; Metric: minimal change for partner #2.)_
- **AC-008** No unfinished capability is visible: no "Coming Soon", placeholder menus, or disabled buttons; admin is reachable only via env-bootstrapped login. _(REQ-015/016/017.)_
- **AC-009** Every public asset carries the AP disclosure block and has passed the compliance-skill review; no clone of Zerodha's page ships; the incentive claim is confined to one swappable location. _(§15, BR-009, BR-011.)_
- **AC-010** Zerodha's form is never auto-submitted; the flow redirects a human and hands off to Ashok. _(BR-005.)_

---

## 17. Cross-References (GoRefer Architecture Repository)

This Foundation Specification (doc **01**) is the source of truth for *what* and *why*. The *how* is elaborated in the sibling documents; each must trace back to the REQ/BR/NFR/AC IDs defined here.

| Doc | Title | Consumes from this spec |
|-----|-------|-------------------------|
| **02** | Architecture Decision Records (ADR) | ADR-001 raw Zerodha `client_id` in path — no token, no mapping DB (accepted); ADR-002 landing-before-redirect; ADR-003 mobile-first; ADR-005 single-domain `client_id` routing |
| **03** | GoRefer Constitution | Product Philosophy (§Part 1), governance rules, decision/tech-debt registers |
| **04** | System Architecture | Engines-not-pages (REQ-018), verification boundary (BR-006), redirect/capture service |
| **05** | Database Design | Event-sourced model (REQ-004/006), confidence classification (REQ-005), lazy creation (REQ-003) |
| **06** | API Specification | Redirect, capture, sync, and admin endpoints implementing REQ-007…021 |
| **07** | UI/UX Specification | Mobile-first surfaces (NFR-001), landing experience, admin dashboard + explorer (REQ-012/013), no "Coming Soon" (REQ-017) |
| **08** | Integrations (WATI + Zoho + Zerodha) | Three-message flow (REQ-010), Zoho sync (REQ-019/021), warm first contact (BR-008), compliance gate (§15) |

---

_End of Foundation Specification (Parts 1–2). This document is frozen for implementation once the Architecture Review closes the OPEN decisions (see Context Brief §7.2 and doc 02-ADR). Requirement IDs are stable and permanent._
