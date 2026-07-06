# GoRefer — 04. System Architecture

> **What this is.** The system architecture for **GoRefer**, the referral-management platform PIFS (Passive Income Financial Solutions Pvt Ltd) is building on top of its Zerodha Authorised-Person relationship. This document defines the components, how they talk, the runtime flows, the background jobs, the event model, the security posture, scalability, deployment, and the multi-partner future.
>
> **Read alongside:** [`05-Database-Design.md`](./05-Database-Design.md) (the PostgreSQL schema this architecture assumes) and [`06-API-Specification.md`](./06-API-Specification.md) (the API layer described here). This document is the "shape of the system"; 05 is "where the data lives"; 06 is "how the pieces talk."
>
> **Grounded in:** `GoRefer-Master-SourceOfTruth-from-ChatGPT.md` (esp. Additions 10, 15, 16, 18), `GoRefer-Build-Spec-Cowork-Decisions.md`, and `GoRefer-Context-Brief.md`. Where those docs leave a decision open, this document marks it **OPEN** rather than silently resolving it.
>
> **Date:** 2026-07-04.

---

## 1. Architectural North Star

GoRefer is an **orchestrator**, not a monolith and not a bag of scripts.

- **GoRefer owns the referral intelligence.** The referral *relationship* — who referred whom, through which campaign, which landing page, how many clicks, what state the journey is in — is data that **no other system owns**. WATI knows only messages. Zoho knows only "this is a lead." Neither understands that Abhay referred Rahul. That relationship is GoRefer's core value, and it lives in **GoRefer's own PostgreSQL database**. (`Master` Addition 18.)
- **Zoho CRM is the sales pipeline.** Lead created → assigned to executive → called → documents pending → KYC → account opened. GoRefer *creates* the lead in Zoho; Zoho *runs* the sales process. (`Master` Addition 18.)
- **WATI is messaging only.** Campaigns, templates, WhatsApp conversations, delivery status, read receipts, inbound messages. Nothing else. (`Master` Addition 18.)
- **GoRefer has its own API layer, and everything flows through it. WATI and Zoho never talk to each other directly.** All coordination is centralized in GoRefer's business logic — which means one place to debug, one place for analytics, and the freedom to add Groww / insurance / properties later without touching the WATI or Zoho integrations. (`Master` Addition 18; ADR-006.)

This is the load-bearing decision of the whole system. If you remember one thing: **GoRefer sits in the middle; the two SaaS tools hang off it; they never wire to each other.**

---

## 2. Component Diagram (ASCII)

```
                        ┌──────────────────────────────────────────┐
                        │             END USERS / CHANNELS          │
                        │  Existing Zerodha customer · Friend/       │
                        │  prospect · Executive (Ashok) · Admin     │
                        │  via WhatsApp · web browser · social       │
                        └───────────────┬──────────────────────────┘
                                        │  (HTTPS / short links / WA)
                                        ▼
   ┌───────────────────────────────────────────────────────────────────────────┐
   │                          E D G E   L A Y E R                                │
   │  ┌───────────────────────────┐   ┌────────────────────────────────────┐    │
   │  │  Redirect / Link Service  │   │  Web App (landing experiences,     │    │
   │  │  gorefer.in/r/{client_id}     │   │  customer referral wizard,         │    │
   │  │  FAST · edge-friendly ·   │   │  PIFS-branded capture form,        │    │
   │  │  rate-limited · logs a    │   │  admin portal)                     │    │
   │  │  click event, then 302    │   │                                    │    │
   │  └────────────┬──────────────┘   └───────────────┬────────────────────┘    │
   └───────────────┼──────────────────────────────────┼─────────────────────────┘
                   │                                  │
                   ▼                                  ▼
   ┌───────────────────────────────────────────────────────────────────────────┐
   │                    G o R e f e r   A P I   L A Y E R                        │
   │          (the orchestrator — ALL business logic lives here)                │
   │                                                                            │
   │  Referral Engine │ Landing Engine │ Redirect Engine │ Kit/Poster Engine    │
   │  Campaign Engine │ CRM Sync Engine │ Analytics Engine │ Notification Engine │
   │  Identity/Auth   │ Admin Engine    │ (AI Engine — later)                    │
   └───────┬───────────────────┬───────────────────────┬───────────────────────┘
           │                   │                       │
           │ writes/reads      │ emits/consumes        │ integrations (outbound only,
           ▼                   ▼                       │ GoRefer initiates every call)
   ┌────────────────┐  ┌────────────────────┐          │
   │  PostgreSQL    │  │   Event Bus /      │          │
   │  (system of    │  │   Event Store      │          │
   │  record for    │  │  (immutable        │          │
   │  referral      │  │   domain events)   │          │
   │  intelligence) │  │        │           │          │
   │  see doc 05    │  │        ▼           │          │
   └────────────────┘  │  Background Jobs:  │          │
                       │  · Event ingestion │          │
                       │  · Zoho sync worker│          │
                       │  · Share-event cap │          │
                       │  · Analytics rollup│          │
                       └────────────────────┘          │
                                                        ▼
        ┌───────────────────────────────┬───────────────────────────────┐
        │            WATI               │             Zoho CRM          │
        │  (messaging only:             │  (sales pipeline only:        │
        │   templates, sends,           │   leads, executives,          │
        │   delivery/read, inbound)     │   follow-ups, KYC status)     │
        └───────────────────────────────┴───────────────────────────────┘
                       ▲                                 │
                       │  webhook (inbound WA replies,   │  account-status
                       │  delivery status) → GoRefer     │  sync → GoRefer
                       └─────────────────────────────────┘

        ┌───────────────────────────────────────────────────────────────┐
        │  DESTINATION (external, not owned): Zerodha public lead URL     │
        │  https://signup.zerodha.com/api/lead?c=ZMPHZC&r={client_id}     │
        │  reCAPTCHA-gated · lead-capture-only · ends at "thanks"         │
        └───────────────────────────────────────────────────────────────┘
```

**Key reading of the diagram:** WATI and Zoho both sit on the *bottom* row and there is **no line between them** — every arrow to/from either passes through the GoRefer API layer. The Zerodha URL is a *destination*, reached only by handing a real human browser to it; GoRefer never posts to it.

---

## 3. The Orchestrator Model (responsibilities)

| System | Owns | Does NOT own | Notes |
|--------|------|--------------|-------|
| **GoRefer + PostgreSQL** | Referral identities (raw `client_id`), referrer↔prospect relationship, campaign attribution, landing experiences, click/share/redirect history, referral state machine, analytics, reward *eligibility* display | KYC, PAN/Aadhaar, brokerage math, trading data, reward *calculation* | The brain. System of record for everything no one else owns. (Addition 18; ADR-006.) |
| **Zoho CRM** | Lead lifecycle, executive assignment, follow-ups, call logs, KYC/account-opening status | The referral relationship; analytics on kits/posters/QR; leaderboards | GoRefer creates the lead; Zoho runs the sale. (Addition 18.) |
| **WATI** | WhatsApp template sends, campaigns, delivery/read receipts, inbound messages | Any business logic, any referral state | Messaging pipe only. (Addition 18.) |
| **Zerodha (external)** | Account opening, KYC, reward crediting, brokerage | Anything GoRefer models | Reached only via the public lead URL, by a human. (`Build-Spec` §3–4.) |

**Why all three, not one:** forcing this into WATI or Zoho alone breaks the moment you need leaderboards, kit-download analytics, per-poster A/B tests, or a second partner. Forcing it into PostgreSQL alone means re-building lead assignment, reminders, call logs, and pipelines that Zoho already does well. GoRefer coordinates; it does not replace. (`Master` Addition 18.)

**GoRefer's own API layer is the only integration hub.** Concretely: when a friend clicks a link, GoRefer — not WATI — decides to create a Zoho lead; when Zoho marks an account opened, Zoho calls GoRefer, and GoRefer — not Zoho — decides to fire the "congrats" WhatsApp via WATI. Centralized logic, single audit trail, swappable partners.

---

## 4. Sequence Flows

### 4.1 Referral click → log event → optional landing → redirect

This is the hot path and the reason the redirect service must be fast (§8, §9).

```
Friend taps  gorefer.in/r/{client_id}
        │
        ▼
Redirect/Link Service (edge)
  1. Format-validate {client_id} from the path; lazily create-or-find the referral_identity
        │  (partner=Zerodha + ZMPHZC from config; no ownership check — no Zerodha API)
        │  (empty/oversized/illegal-char id → friendly error page, still logs an event)
        ▼
  2. Emit immutable event: ReferralLinkOpened
        │  (event carries session_id, device_id, geo, ip*, user_agent, confidence=Unknown)
        ▼
  3. Decide next hop by program/landing rule:
        ├── Landing experience configured  → 302 to gorefer.in landing page
        │        │  (ADR-002: landing before redirect — trust, benefits, "Need help?")
        │        │  user taps "Open Account"
        │        ▼
        │      Emit event: LandingViewed → then RedirectInitiated
        │        ▼
        └── No landing (direct)            → straight to step 4
        ▼
  4. Build destination URL from the Program plugin:
        https://signup.zerodha.com/api/lead?c=ZMPHZC&r={referrer_client_id}
        │  (r= preserved — Decision Option A, referrer stays credited)
        ▼
  5. 302 the REAL HUMAN BROWSER to Zerodha. GoRefer never submits the form.
        │
        ▼
  Zerodha lead-capture form (reCAPTCHA) → "thanks" → Zerodha follow-up / Ashok completes KYC
```

\* IP/PII handling per DPDP — see §7.5.

### 4.2 PIFS capture-first flow (branded form → lead saved → WhatsApp fan-out)

The team-assisted path locked in the build session (`Build-Spec` §4).

```
Friend/referrer submits PIFS-branded GoRefer form (mobile, name, email; c= & r= hidden)
        │
        ▼
GoRefer API: SAVE LEAD FIRST (PostgreSQL prospect + referral rows)   ← never lost
        │
        ├── create Lead in Zoho CRM (CRM Sync Engine)
        │
        └── enqueue 3 WhatsApp sends via WATI (each a Meta-approved template):
              a) → Ashok:    "new lead [name, mobile, referred-by], call now"
              b) → new person:"[Referrer] referred you to PIFS… continue: [link with r=]"
              c) → referrer:  "Your referral for [name] is registered — thank you"
                              (ONLY if referrer phone resolvable from Zoho)
        │
        ▼
Ashok calls, helps complete Zerodha account opening (human satisfies reCAPTCHA legitimately)
```

Opt-in caution (§7) applies to message (b): the first message to a lead who did **not** opt in themselves must be a warm, utility-style notice naming the referrer — not a marketing blast.

### 4.3 Zoho → GoRefer account-status sync

Zoho owns the pipeline, so account-opening truth originates there and is imported back.

```
Executive in Zoho advances lead:  Contacted → KYC Started → Account Opened
        │
        ▼
Zoho notifies GoRefer (webhook or polled by the Zoho sync worker — see §5.2)
        │
        ▼
GoRefer maps Zoho lead → referral row, updates referral status / conversion_status
        │  records SOURCE = "zoho" on the imported status field (05 §audit)
        ▼
Emits event: SignupCompleted / ReferralConfirmed
        │
        └── Notification Engine → WATI "congratulations" to the referrer (if phone known)
```

**Fabrication rule (hard):** account-opening and reward events come **only** from Zoho (or a future partner's system of record). GoRefer **never fabricates unverifiable events**. The Zerodha lead URL ends at "thanks" and tells us nothing about whether an account actually opened — so `ReferralLinkOpened` / `RedirectInitiated` are the *most* we can assert from a click; `SignupCompleted` must be imported. (`Build-Spec` §3; `Context-Brief` §3.)

---

## 5. Services & Background Jobs

GoRefer is a set of **engines** (each could become its own API/service) plus a small set of **background workers**. Engines are named for behaviour, never for Zerodha. (`Master` Additions 6, 7, 10.)

### 5.1 Engines (request-path services)

- **Referral Engine** — a referrer's link **is** `gorefer.in/r/{client_id}` (their raw Zerodha `client_id`; no mint step). On the **first click** it lazily creates the `referral_identities` row (05 §9), the journey, and the click event; subsequent clicks continue the same journey.
- **Redirect Engine** — format-validate the `client_id` → identify program from config (Sprint 1 = Zerodha) → log analytics → emit event → build destination URL with `c=ZMPHZC` injected server-side → 302. Knows nothing about Zerodha internals; the Program plugin supplies the destination. (`Master` Addition 8 §7.)
- **Landing Engine** — serve per-referral landing experiences (headline, benefits, FAQ, CTA) before redirect.
- **Kit / Poster Engine** — one click → personalized referral kit (poster, WhatsApp Status image, QR, ready-made messages). Receives Title/Subtitle/Link/QR/Logo/Theme/CTA and generates output; program-agnostic. (`Master` Addition 6.)
- **Campaign Engine** — model Channel/Message/Variables/CTA/Media; WhatsApp/Facebook/Email are connectors, not hard-coded.
- **CRM Sync Engine** — create/update leads in Zoho, resolve referrer phone from Zoho `client_id`.
- **Notification Engine** — dispatch via WATI (WhatsApp primary), email fallback later.
- **Analytics Engine** — answer questions from events (not counters): which poster/campaign/executive/city converts.
- **Identity/Auth + Admin Engine** — admins & executives only in Sprint 1; customers do NOT log in. (`Master` Addition 10, context 1.)

### 5.2 Background jobs (off the request path)

- **Event ingestion worker** — durably persists emitted domain events into the event store; the hot redirect path emits fast and returns, ingestion happens asynchronously so a slow write never delays a redirect.
- **Zoho sync worker** — reconciles lead/account status from Zoho into referral rows (webhook-driven where available, polled as a fallback), recording the `source` on imported fields.
- **Share-event capture worker** — captures share signals (kit downloaded, WhatsApp/Status/social share) into events; some arrive from the client and are validated/normalized here.
- **Analytics rollup worker** — periodically folds raw events into `campaign_stats` / `daily_metrics` aggregate tables (05 §12) so dashboards read cheap pre-computed rows instead of scanning the events table.

---

## 6. Event-Driven Architecture

**Store business events, not counters.** Instead of `referral.clicks++`, GoRefer records an immutable `ReferralLinkOpened` event; instead of a poster-download counter, a `PosterDownloaded` event. (`Master` Additions 8, 10; **ADR-004 approved**.)

- **Events are immutable and append-only.** They are never updated in place; they are the ground truth.
- **Analytics are *derived* from events, never stored as authoritative counters.** Counts and rates in `campaign_stats` / `daily_metrics` are rollups (§5.2) that can always be rebuilt by replaying events. If we ever want to answer a question we never anticipated — "which landing page converts best for referrals that arrived after a 15-day gap?" — the raw events already hold the answer, no schema change needed. (`Master` Addition 8 §4.)
- **Modules communicate through the event bus, not by calling each other.** `Referral Created → Event Bus → Analytics / CRM / Notifications / Reports`. Loose coupling means adding a consumer (e.g. a future AI insights engine) never touches the producer. (`Master` Addition 8 §5.)
- **The referral state machine emits an event on every transition:** `Created → Shared → Opened → Landing Viewed → Signup Started → Signup Completed → Confirmed → Rewarded`. Every state change is stored forever. (`Master` Addition 7 §9.)

The canonical event vocabulary (from `Master` Addition 7 §5): `CustomerRegistered, ReferralLinkCreated, ReferralLinkOpened, LandingViewed, WhatsAppClicked, PosterDownloaded, ReferralShared, LeadCreated, ExecutiveAssigned, ExecutiveCalled, SignupStarted, SignupCompleted, ReferralConfirmed, RewardReceived`. The physical `events` table that stores them (columns, indexes, the click-`confidence` field) is specified in [`05-Database-Design.md`](./05-Database-Design.md) §12.

---

## 7. Security Model

### 7.1 Bootstrap admin & identity
Sprint 1 has no customer login; only **Admins and Executives** authenticate. (`Master` Addition 10.) The system ships with a single **bootstrap admin** created at deploy time (seeded, then forced to rotate its credential on first login); all other users are created by that admin. This avoids an open registration surface on a system that touches lead PII.

### 7.2 Feature flags
Every non-core capability (kit generator, social share, AI copy, multi-program) sits behind a **feature flag** so it can be dark-launched and killed without a deploy. The **10%-brokerage claim wording is itself flag-/single-source-controlled** (§7.6) so it can be pulled instantly if NSE reinstates the ban.

### 7.3 Least privilege
Executives see only their assigned leads and the operational surface they need; admins get configuration and analytics; the redirect/edge service holds only the credentials it needs to validate a `client_id`, lazily create-or-append the journey, and log an event — it cannot mutate referral business state. Service credentials (WATI bearer token, Zoho tokens) live in a secrets store / connection manager, **never inline in code** — a direct lesson from the existing hardcoded-JWT finding in the Zoho Deluge functions. (`Context-Brief` §4.3.)

### 7.4 Rate limiting on the redirect endpoint
`gorefer.in/r/{client_id}` is public and unauthenticated, so it is the prime abuse target (click-flooding to pollute analytics). The `client_id` is a raw, already-public identifier (ADR-001), so there is nothing to "enumerate" that Zerodha's own links do not already expose; the defense is **rate-limiting at the edge** (per-IP and per-`client_id`), not obscurity. Abusive spikes are absorbed at the edge and still logged (with low click-confidence) rather than trusted.

### 7.5 Careful IP / PII storage per DPDP
The `events` table can capture `ip`, `user_agent`, and coarse geo. Under India's DPDP Act this is personal data, so: collect the minimum needed for fraud/analytics, treat raw IP as sensitive (truncate/anonymize where full precision isn't required, apply retention limits), and keep PII out of the referral *intelligence* tables that don't need it. GoRefer deliberately does **not** store PAN / Aadhaar / KYC / brokerage — it stores *workflow* data, not *ownership* data, which structurally shrinks the compliance blast radius. (`Master` Addition 10; §1.)

### 7.6 Click confidence (anti-fabrication)
Every click event carries a **confidence** field — default **`Unknown`**, or **`Authenticated Owner`** / **`Internal Test`** when we can prove the origin. This lets analytics separate "a real, attributable open" from "a bot/preview/warm-up hit" and from "our own test traffic," so we never over-report referrals. It is the storage-level expression of the *never fabricate unverifiable events* rule (§4.3). Column defined in [`05-Database-Design.md`](./05-Database-Design.md) §12.

### 7.7 No spoofing, compliance gate
The PIFS capture form must **not resemble Zerodha's** (misrepresentation risk under NSE/COMP/55482), and every public asset passes the `zerodha-ap-social-media-compliance` gate before publishing. Security here is also *regulatory* security. (`Build-Spec` §7; `Context-Brief` §6.)

---

## 8. Scalability

- **The `events` table is the largest object in the system, by a wide margin.** Every click, landing view, share, redirect, and status change is a row. It is append-only, time-ordered, and read mostly in aggregate — so it is a natural fit for time-based partitioning and for being rolled up (§5.2) rather than scanned live.
- **Lazy journey creation keeps volume proportional to real activity, not customer count.** A referral journey / analytics rows are created **only on the first click** of a link — not for every customer, and not when a link is merely generated. So load scales with *actual clicks*, not with the size of the customer base. A campaign blasted to 20,000 contacts that gets 400 clicks creates ~400 journeys, not 20,000. (This is the architectural payoff of the lazy-journey rule specified in 05.)
- **Read/write split by nature:** the redirect hot path is write-light (one lazy upsert + one append event) and read-light (one indexed `client_id` lookup); dashboards read pre-aggregated rollups. Neither competes with the other.
- **Stateless edge:** the redirect/link service holds no session state, so it scales horizontally and can run at the edge (§9).

---

## 9. Deployment

**Status: TBD / not locked.** The build spec *recommends* a simple managed stack for a one-person operation and flags the redirect layer as latency-critical. (`Build-Spec` §9; `Context-Brief` §7.)

Recommended shape (not yet a locked ADR):

- **Redirect / link service must be fast and edge-friendly.** The original recommendation was a **Cloudflare Worker** that logs the click and forwards to the correct pre-filled Zerodha URL — precisely because a redirect must feel instant and because the edge gives global low latency and built-in rate limiting. (`Build-Spec` §9.) Keep this tier thin: validate the `client_id`, lazily create-or-append the journey, emit event, 302.
- **Simple managed stack for the rest:** a managed PostgreSQL, a managed container/app host for the API engines, and a managed queue for the background workers. For a solo founder, prefer managed services over self-hosted infra (simpler DNS/SSL/ops) — the same reasoning that favours a bare domain over per-partner subdomains (§10).
- **Build order (from the spec):** ship the **form + CRM capture first** (works immediately, no template approval needed), and submit the three WATI templates for Meta approval **in parallel** (hours to ~2 days). (`Build-Spec` §9.)
- **Deployment-adjacent decisions** (see 05 and the build spec): domain scheme is locked to `gorefer.in/r/{client_id}` (raw `client_id`, ADR-005); lead destination (Zoho / WATI / both).

---

## 10. Future Multi-Partner Expansion

GoRefer is "a platform, not a project": Sprint 1 supports only Zerodha, but **no component is named or designed as Zerodha-only**. (`Master` constitution §8; Additions 14–16.)

- **Partner as configuration.** Adding Groww, Upstox, insurance, mutual funds, properties, or loans is a **data/config change, not a code change**. The Referral, Redirect, Landing, Kit, Campaign, and Analytics engines already operate on `program_id` / `partner_id`, never on a hard-coded "Zerodha." (`Master` Additions 6, 8, 15.)
- **Partner Credentials abstraction.** The partner-specific secrets — **Client ID / Agent ID / Advisor Code** (for Zerodha: partner code `ZMPHZC`, the referrer's Zerodha `client_id`, NSE AP `AP2516003693`) — are modelled as a *Partner Credentials* structure attached to the partner/program, so a new partner is "fill in its credentials + destination URL template + landing theme," and the Redirect Engine's Program plugin supplies the destination. (`Master` Additions 8, 15; `Build-Spec` §3.)
- **Single-domain routing (ADR-005, approved & locked 2026-07-04).** Referral URLs are `gorefer.in/r/{client_id}` — the raw referrer id in the path, with the program resolved from config — plus `gorefer.in/{partner}` as the marketing page. This avoids accumulating `zerodha./groww./upstox.…` subdomains (DNS/SSL sprawl at ~100 partners) and means the *same* engine serves every partner with no routing changes. **Future non-Zerodha partners** that expose no reusable native ID will use a GoRefer-**generated** referral id created at referrer login (ADR-001 note); Zerodha uses its native `client_id`. (`Master` Additions 15, 16.)

The platform stays the same; only the partner changes.

---

## 11. The Cowork Reality (guard-rails that constrain every design above)

These are verified, non-negotiable facts from the 2026-07-04 live test (`Build-Spec` §3–5; `Context-Brief` §3). They are why this architecture is "capture-first, human-assisted" rather than "automated funnel":

1. **Zerodha's `api/lead?c=ZMPHZC&r={client_id}` is a reCAPTCHA-gated, lead-capture-only page that ends at a "thanks / we'll contact you" screen.** It does **not** proceed into PAN/KYC/account opening. The `/?c=…&r=…` variant behaves identically.
2. **Account opening and reward crediting come ONLY from Zoho** (the pipeline system of record), imported back into GoRefer with a recorded `source`. They are never inferred from a click or a redirect.
3. **GoRefer never fabricates unverifiable events.** A click proves `ReferralLinkOpened`, at a stated confidence level — nothing more. `SignupCompleted` / `ReferralConfirmed` are only ever set from a verified partner source.
4. **Never auto-submit Zerodha's form** (reCAPTCHA + compliance + account risk). The only compliant path is redirecting a real human browser. A human (Ashok) satisfies reCAPTCHA and completes KYC on a call, preserving both the `c=` (partner) and `r=` (referrer) mappings.
5. **The partner/referrer codes are pre-filled but editable on Zerodha's own page**, so code-swap (R7 revenue leakage) is mitigated by a hidden default in our link but **cannot be fully prevented** — it is Zerodha's page, not ours. Residual risk accepted.

---

## 12. Cross-References

- **Data model / every table, column, index, the `events` table, the click-`confidence` field, soft-delete & audit columns, the lazy-journey rule, and the Zoho-`source` note:** [`05-Database-Design.md`](./05-Database-Design.md).
- **API endpoints, request/response contracts, the redirect contract, the Zoho and WATI integration APIs:** [`06-API-Specification.md`](./06-API-Specification.md).
- **Vision, decisions, and open questions this architecture implements:** `GoRefer-Master-SourceOfTruth-from-ChatGPT.md`, `GoRefer-Build-Spec-Cowork-Decisions.md`, `GoRefer-Context-Brief.md`.

---

*GoRefer — 04. System Architecture. Compiled 2026-07-04. Owner: Abhay Kumar Maurya (PIFS, Zerodha Authorised Person, NSE AP AP2516003693).*
