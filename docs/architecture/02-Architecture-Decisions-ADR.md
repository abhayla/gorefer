# GoRefer — Architecture Decision Records (ADRs)

**Document 02 of the GoRefer Architecture Repository.**
**Owner:** Abhay Kumar Maurya / PIFS (AI-assisted). **Status:** Working draft. **Last updated:** 2026-07-04.

> Each record captures one significant, hard-to-reverse decision. Format for every ADR: **ID · Title · Status · Context/Problem · Alternatives Considered · Decision · Reasoning · Consequences.** ADR-001..ADR-012 originate in the master capture doc (`GoRefer-Master-SourceOfTruth-from-ChatGPT.md`); ADR-013 and ADR-014 encode the ground truth added in the 2026-07-04 Cowork session (`GoRefer-Build-Spec-Cowork-Decisions.md`).

---

## ADR-001 — Raw Zerodha `client_id` in the path `gorefer.in/r/{client_id}` (no token, no mapping DB)

- **Status:** Accepted (locked, 2026-07-04). **Reverses** the earlier opaque-token decision. The partner code `ZMPHZC` is injected **server-side** into the redirect and never appears in the shared link.
- **Context / Problem:** A referral link must credit both the partner (`c=ZMPHZC`) and the referring client (`r=<client_id>`). The earlier design used an opaque token resolved through a `token → client_id` mapping table. But GoRefer's referrers are **open-ended** — anyone with a Zerodha client ID can refer, not just Abhay's existing customers — so **no token→id mapping can pre-exist** for a stranger. A person who is not in Abhay's data must be able to refer simply by putting **their own** Zerodha client ID in the link. A mint-a-token-per-customer scheme cannot serve a referrer GoRefer has never seen.
- **Alternatives Considered:**
  1. **Opaque token** (`gorefer.in/r/{token}`) — requires a pre-created `token → client_id` mapping row per referrer. Fails the open-ended-referrer test: a stranger has no pre-existing token, so they cannot self-form a link. Rejected.
  2. **Raw Zerodha `client_id` in the path** (`gorefer.in/r/RJ4521`) — no mapping table, no mint step; any referrer self-forms their own link from their own known client ID.
- **Decision:** Put the **raw Zerodha `client_id` directly in the path**: `gorefer.in/r/{client_id}` (e.g. `gorefer.in/r/RJ4521`). There is **no opaque token and no token→id mapping table**. The partner code `ZMPHZC` is added **server-side** at redirect time and is never in the shared URL. For Abhay's own customers, a WATI campaign simply sends each of them their pre-formed `gorefer.in/r/{their_client_id}` link (built from data Abhay already has — this is *not* an import step). Non-customers self-form the link with their own Zerodha client ID.
- **Reasoning:** Referrers are open-ended, so there is no pre-existing data from which to mint or map a token. The raw `client_id` is the only identifier that both Abhay's customers **and** strangers can produce without an onboarding step. The `client_id` is not a secret — it is **already public in Zerodha's own `r=` referral links**. A wrong or mistyped id only fails to credit that one referrer; `c=ZMPHZC` is injected server-side and **always** credits PIFS regardless.
- **Consequences:** The `client_id` is **visible in the link** (accepted — it is already exposed in Zerodha's own referral URLs). There is **no per-link revocation/rotation** (accepted — a raw public identifier has none). No `token → client_id` mapping table is built or maintained for Zerodha; the redirect handler format-validates the `client_id` and uses it directly. See ADR-008 for lazy creation on first click.
- **Note for future partners:** Partners **other than Zerodha** (properties, mutual funds, loans, etc.) may not expose a reusable native ID like Zerodha's `client_id`. For those, GoRefer will **generate a referral ID when the referrer logs in** (a future capability). So the *generated-ID* concept returns for future partners — but **Zerodha uses its native `client_id`**. This is a forward-looking note, **not** a Sprint-1 feature.

---

## ADR-002 — Landing experience before redirect

- **Status:** Accepted.
- **Context / Problem:** When a friend clicks a referral link, GoRefer can either bounce them straight to Zerodha or first show its own page. An immediate redirect is a pure URL-shortener; it forfeits trust-building, value explanation, analytics, and any chance to offer human help.
- **Alternatives Considered:** (1) Immediate redirect to Zerodha. (2) A branded GoRefer landing page ("Your friend Rahul invited you — open your free Zerodha account, benefits, need help?") shown first, redirecting only when the visitor chooses to continue.
- **Decision:** Every referral link resolves to a **landing experience first**; redirect to Zerodha happens only after the visitor chooses to continue.
- **Reasoning:** The landing page builds trust, explains the value proposition, captures analytics (landing-page view as a distinct event), enables an offer of assistance, and allows A/B testing. This is the shift from "URL shortener" to "conversion platform."
- **Consequences:** GoRefer owns a real page per referral (configurable per program). One extra step before Zerodha, justified by higher conversion and richer data. Requires the landing-page-view event in the event model.

---

## ADR-003 — Mobile-first UI

- **Status:** Accepted.
- **Context / Problem:** The overwhelming majority of referral traffic originates from WhatsApp on a phone. A desktop-first design that is merely "responsive" degrades the primary experience.
- **Alternatives Considered:** (1) Desktop-first, responsive down to mobile. (2) Mobile-first, designed for the phone as the primary surface.
- **Decision:** Design **mobile-first** — for the phone as the primary device, not merely responsive.
- **Reasoning:** Most referrals start on WhatsApp; the majority of clicks and shares happen on mobile. Optimising for the real device raises conversion.
- **Consequences:** All screens, wireframes, and share affordances are designed for mobile first; desktop is the adaptation. One-tap Share/Open is preferred over copy-paste or same-phone QR scans.

---

## ADR-004 — Event-driven analytics (store events, not counters)

- **Status:** Accepted.
- **Context / Problem:** Analytics can be stored as running counters (e.g. a `clicks` integer) or as an append-only log of individual events. Counters are cheap but lossy — they cannot answer questions not anticipated when the counter was created.
- **Alternatives Considered:** (1) Counter-based analytics (increment aggregates). (2) Event-driven model (store each observable event as an immutable row; derive all aggregates from events).
- **Decision:** Use an **event-driven analytics model**. Every observable event (link created, shared, clicked, landing-page viewed, redirect initiated, lead created, …) is stored as its own record; all reporting is computed from the event stream.
- **Reasoning:** Unlimited reporting flexibility, easier debugging, a complete audit trail, and support for future AI-driven insights. "Collect everything now, visualise it later." Counters throw away exactly the data future questions need.
- **Consequences:** More storage and a query/aggregation layer are required. Events are immutable (see ADR-007 and the Constitution). Any new metric is a query over existing data, not a schema migration or a backfill.

---

## ADR-005 — Single-domain routing (`gorefer.in/r/{client_id}` + `gorefer.in/{partner}`)

- **Status:** Approved & locked (2026-07-04). Supersedes the earlier `z.gorefer.in` subdomain scheme. Updated to carry the **raw `client_id`** in the path (ADR-001), not an opaque token.
- **Context / Problem:** The origin doc initially assumed a per-context subdomain (`z.gorefer.in`). Subdomains multiply DNS records, SSL certificates, and operational surface — heavy for a one-person operation and awkward to extend per partner.
- **Alternatives Considered:** (1) Per-partner/subdomain scheme (`z.gorefer.in`, `groww.gorefer.in`, …). (2) Single bare domain with path-based routing: referral journeys at `gorefer.in/r/{client_id}`, marketing pages at `gorefer.in/{partner}`.
- **Decision:** Use a **single-domain, path-routed** architecture. Canonical URLs: referral journey `gorefer.in/r/{client_id}` (the raw Zerodha `client_id`, per ADR-001); public/marketing page `gorefer.in/{partner}` (e.g. `gorefer.in/zerodha`, future `gorefer.in/groww`, `gorefer.in/insurance`, `gorefer.in/properties`). The partner/program for a referral path is resolved from **config** (Sprint 1 = Zerodha); the path segment carries the referrer's `client_id`.
- **Reasoning:** Simpler infrastructure, easier SSL/DNS management, cleaner analytics, shorter links (better UX), and painless future expansion — a new partner is a new path, not a new subdomain and certificate. Migrating URL structures later is expensive, so this is locked before code is written.
- **Consequences:** One domain and one certificate to manage. Partner pages and referral journeys share a routing layer that dispatches by path. No subdomain dependency. The `{client_id}` segment is the raw referrer id (ADR-001), not a token.

---

## ADR-006 — PostgreSQL + Zoho CRM + WATI, with GoRefer as orchestrator

- **Status:** Accepted (locked recommendation).
- **Context / Problem:** GoRefer needs a home for its own entities (referrals, referral identities, journeys, analytics, configuration) while a mature CRM (Zoho) already owns leads and sales, and WATI already owns WhatsApp messaging. Duplicating any of these invites drift and conflict.
- **Alternatives Considered:** (1) Store everything inside Zoho custom modules. (2) Use a document store (e.g. MongoDB) for GoRefer data. (3) A dedicated relational database for GoRefer entities, integrating with Zoho and WATI as systems of record for their domains.
- **Decision:** **PostgreSQL** is the primary store for all GoRefer-specific entities; **Zoho CRM** owns lead management, executive workflow, and the sales pipeline; **WATI** owns WhatsApp messaging, templates, and campaigns; **GoRefer** is the orchestration layer integrating all three.
- **Reasoning:** GoRefer's data is highly relational (links → journeys → events) and analytics-heavy — PostgreSQL fits far better than a document store or CRM modules. Keeping each system as the authority for its own domain avoids duplication and keeps GoRefer's logic separate from CRM and messaging logic.
- **Consequences:** Clear ownership boundaries: business/referral logic in GoRefer, CRM logic in Zoho, messaging in WATI. GoRefer must maintain integration adapters and reconcile state pulled from Zoho. No partner or messaging logic leaks into the core schema.

---

## ADR-007 — Every referral link is a first-class entity with a full lifecycle

- **Status:** Accepted (core feature, not an enhancement).
- **Context / Problem:** A referral link can be treated as a throwaway string, or as an entity with identity, ownership, and history. Treating it as a string makes per-link intelligence impossible and loses data forever.
- **Alternatives Considered:** (1) Links as opaque strings; track only aggregate program-level stats. (2) Links as first-class entities, each with its own lifecycle and analytics.
- **Decision:** Every referral link is a **first-class entity** with a unique identifier, an owner (the referring customer), a creation timestamp, and a complete chronological timeline: share events, click events, visitor details (where available and privacy-compliant), landing-page visits, redirects, lead-creation status, account-opening status, and reward status.
- **Reasoning:** Per-link intelligence (who shares, on what channel, converting how well) is a core differentiator, not an add-on. Even in Sprint 1 the events must be captured so historical data is never lost — "collect everything now, visualise it later."
- **Consequences:** The schema models links, journeys, and events explicitly. Analytics and the future "My Referrals" dashboard are derived from this per-link history. Storage and event volume grow with usage, accepted as the cost of intelligence.

---

## ADR-008 — Lazy journey creation (no record until the first click)

- **Status:** Locked.
- **Context / Problem:** Every referrer can form a referral link, but most links are never clicked. Eagerly creating a tracking record for every possible referrer wastes storage and clutters analytics with empty journeys. Because referrers are open-ended (ADR-001), there is no fixed customer list to pre-load anyway.
- **Alternatives Considered:** (1) Eagerly create a journey per known customer up front. (2) Create the referrer record **and** the journey only when the link is first clicked (lazy creation).
- **Decision:** **Lazy creation on first click.** Nothing is pre-loaded. On the **first click** of `gorefer.in/r/{client_id}`, GoRefer creates the **referrer record** (keyed by that raw `client_id`), the **Referral Journey**, and the first **click event** — all in that moment, after format-validating the `client_id`. Every subsequent event is appended to the same journey. Zoho CRM enriches the journey with lead/contact information; WATI is used only for communication.
- **Reasoning:** Keeps the system lightweight and scalable and mirrors how the business actually operates — a referral only "exists" operationally once someone acts on it. Avoids millions of empty rows.
- **Consequences:** Journey count reflects real activity, not headcount. A link with no journey simply means "shared but not yet clicked." The event pipeline must create-or-append on the first inbound event.

---

## ADR-009 — Role-based dashboards (admin now, "My Referrals" architected)

- **Status:** Locked.
- **Context / Problem:** GoRefer serves two very different audiences — the operator (Abhay/team) who needs cross-partner operational intelligence, and the individual referrer who wants to see their own performance. One dashboard cannot serve both well.
- **Alternatives Considered:** (1) A single dashboard for everyone. (2) Distinct, role-based dashboards from the beginning.
- **Decision:** **Role-based dashboards from the start.** (a) **Admin Dashboard** (Abhay + team): cross-partner analytics, customer performance, campaign analytics, referral intelligence, lead and account status via Zoho. (b) **Referrer Dashboard ("My Referrals")**: personal referral link, share tools, click history, unique visitors, landing-page and account-page visits, accounts opened (synced from Zoho where applicable), progress toward milestones, recent-activity timeline. In Sprint 1 only the admin dashboard is exposed; the "My Referrals" role is architected but disabled (see ADR-011).
- **Reasoning:** "My Referrals" gives customers a reason to return, share more, and stay engaged; the admin view gives the operator the intelligence to grow referrals across Zerodha now and other partners later. Designing both roles up front avoids a rebuild when self-service switches on.
- **Consequences:** Authorization and data-scoping are role-aware from day one. Sprint 1 ships only the admin surface; enabling the referrer view later requires no redesign.

---

## ADR-010 — One permanent link per user per program; channel analytics via share events

- **Status:** Proposed (recommended to lock).
- **Context / Problem:** To measure which channel (WhatsApp, Facebook, Status, email) drives referrals, one option is to mint a separate link per channel. That multiplies links per user and fragments a single person's referral identity.
- **Alternatives Considered:** (1) Multiple links per user, one per channel (channel encoded in the link). (2) One permanent link per user per program, with the channel captured on the **share event** instead.
- **Decision:** A GoRefer user may participate in **multiple referral programs**; each program has **one permanent referral link** for that user; each program has its own dashboard, analytics, and landing experience. **Channel-level analytics are achieved through share events**, not by creating multiple permanent links for the same program. A future public profile (`gorefer.in/u/{username}`) may showcase all programs but is not used for campaign referrals.
- **Reasoning:** One stable link per program is simpler for the user to remember and share, and keeps their referral identity singular. Recording the channel on the share event preserves channel analytics without link proliferation.
- **Consequences:** The share event must carry a channel attribute. Channel breakdowns are derived from share events joined to subsequent clicks. No per-channel link management burden.

---

## ADR-011 — Admin-only login, bootstrap admin, feature flags (Sprint 1)

- **Status:** Proposed (recommended to lock).
- **Context / Problem:** Sprint 1 needs authentication for exactly one operator without building a full customer identity system, and it must avoid exposing half-built capabilities.
- **Alternatives Considered:** (1) Build full customer auth (OTP/magic-link/passwordless) now. (2) Admin-only login for Sprint 1, with the customer-auth architecture present but disabled and unfinished capabilities hidden behind feature flags.
- **Decision:** **Sprint 1 = admin login only.** The bootstrap admin is created from environment variables. The customer-authentication architecture exists but is **disabled**. **Feature flags** control unfinished capabilities. There are **no "Coming Soon" screens or inaccessible menu items.**
- **Reasoning:** Minimises Sprint-1 complexity and security surface while keeping a clean upgrade path — the same login flow later supports customers without a redesign. Feature flags let architecture exist without exposing it.
- **Consequences:** Only Abhay can authenticate in Sprint 1; anyone else is turned away by design. Enabling customer auth later flips flags and configuration, not a rebuild. No dead UI is ever shown.

---

## ADR-012 — Public marketing site + login at `gorefer.in`

- **Status:** Locked.
- **Context / Problem:** `gorefer.in` could be the app itself or a public marketing site. Making the root the dashboard hides the product story and forces auth on every visitor.
- **Alternatives Considered:** (1) Root domain is the dashboard (auth wall at `/`). (2) Root domain is a public marketing site explaining GoRefer, with login gated separately.
- **Decision:** **`gorefer.in` is a public marketing website, not the dashboard.** It explains GoRefer, its purpose, benefits, and supported programs. A **Login** button appears top-right. In Sprint 1 only the bootstrap admin (Abhay) can authenticate; anyone else sees "Access is currently by invitation only." The dashboard stays behind authentication. The same login flow later supports customer authentication without redesigning the application.
- **Reasoning:** A public site positions the product and supports future self-service signups, while keeping the operational dashboard private. Reusing one login flow avoids a later rebuild.
- **Consequences:** Two surfaces on one domain: public marketing (open) and dashboard (authenticated). Non-admins can read about GoRefer but cannot enter. Customer login is a later configuration change, not a new system.

---

## ADR-013 — No Zerodha API/integration ever; Zoho is the only source of downstream truth

- **Status:** Locked (2026-07-04 Cowork session, grounded in live testing).
- **Context / Problem:** GoRefer needs to report whether a referred account was actually opened and whether a reward is due. It is tempting to integrate with Zerodha to fetch this — and tempting to auto-submit Zerodha's signup form to reduce friction. Live testing (July 2026) showed why neither is possible: `signup.zerodha.com/api/lead?c=ZMPHZC&r=DA1707` lands on a **lead-capture-only** form that ends at a "thanks / we'll contact you" screen (it does **not** proceed into PAN/KYC), the partner and referrer codes are **editable text boxes**, and the form is **Google reCAPTCHA-gated**.
- **Alternatives Considered:** (1) Integrate with a Zerodha referral/account API. (2) Automate/background-submit Zerodha's form to complete signups. (3) Treat Zerodha as an external, human-driven endpoint and source all downstream status from Zoho.
- **Decision:** **No Zerodha API or integration, ever.** Account-opening and reward status come **only from Zoho** (updated operationally by the team). GoRefer **never fabricates unverifiable events**. Because the Zerodha `api/lead` endpoint is a reCAPTCHA-gated lead-capture form ending at "thanks," GoRefer performs **no automated submission** — the only compliant path is redirecting a real human browser, after which a human (Ashok) completes KYC on a call.
- **Reasoning:** There is no Zerodha API to integrate; the public endpoint is bot-gated and lead-capture-only, so automation is both impossible and non-compliant (account + compliance risk). GoRefer can verify what it observes (clicks, redirects) but cannot verify KYC/approval — those must originate externally. Fabricating them would violate the "never fabricate data" principle.
- **Consequences:** GoRefer's verified events stop at "redirect initiated." Account-opening and reward status are enrichments synced from Zoho, clearly attributed to Zoho, never asserted by GoRefer independently. The flow is capture-first and human-assisted by design (see the Build Spec flow). This reconciles the origin doc's "lazy journey / no Zerodha integration" stance (ADR-008) with the verified reality of Zerodha's form.

---

## ADR-014 — Compliance is a hard, non-negotiable gate

- **Status:** Locked (2026-07-04 Cowork session).
- **Context / Problem:** The origin vision doc omitted compliance entirely. As a Zerodha Authorised Person, PIFS is bound by NSE/SEBI advertising and disclosure norms; a single non-compliant public asset is a regulatory and relationship risk. The headline "10% of brokerage" incentive also sits on shifting regulatory ground.
- **Alternatives Considered:** (1) Treat compliance as a manual afterthought before each post. (2) Make compliance a hard, non-negotiable gate baked into the system.
- **Decision:** Compliance is a **hard, non-negotiable gate**, now **genuinely enforced by construction**: the SEBI/NSE AP disclosure block, market-risk warning, and reward wording are **auto-injected into the render/asset path** so a page or generated asset **cannot render without them**, and a **HARD blocking pre-publish gate** refuses to publish or generate any public asset unless the compliance review is complete.
- **Reasoning:** As a Zerodha Authorised Person, PIFS is bound by NSE/SEBI advertising and disclosure norms; a single non-compliant public asset is a regulatory and relationship risk. A manual afterthought is bypassable; making injection intrinsic to the render/asset path and gating publish behind a completed review makes omission structurally impossible rather than merely discouraged.
- **Consequences:** Every user-facing page and generated asset carries the disclosure/risk block automatically. The publish/generate path is blocked until compliance review passes. The "10% brokerage" claim lives in one swappable config field; compliance cannot be weakened or removed by lower config tiers (see ADR-022 compliance lock).

> **AMENDED 2026-07-20 (ADR-038):** *The locked text above is unchanged and still governs. This annotation records its scope in a multi-AP world.*
>
> **The hard gate STANDS, unamended, for (a) platform-rendered surfaces (`gorefer.in` pages) and (b) platform-generated assets.** Auto-injection remains intrinsic to the render/asset path; a page or asset still cannot render without the disclosure block + market-risk warning, and that injection is **never bypassable by acknowledgment**.
>
> **For AP-authored content** — an Authorized Partner's own copy, sent from the AP's own number/identity — the pre-publish gate becomes **ADVISORY with an acknowledged, immutably audited bypass** (ADR-038). GoRefer verdicts the content and recommends a fix; the AP retains the final call and may proceed only via an explicit first-person acknowledgment that is recorded (tenant, user, timestamp, content hash, rule id + rule-text version shown, verdict, recommendation, action taken).
>
> **The boundary runs inside a single artifact** (ADR-038 DA Ruling 1): where GoRefer renders an artifact containing AP copy, **GoRefer's injected block is HARD** and **the AP's own claims within it are ADVISORY**. Also unaffected and still hard (ADR-038 DA Ruling 2): the platform behaviours (never auto-submit a partner form; never impersonate/clone a partner) and DPDP consent/opt-out enforcement — **no acknowledgment can authorize messaging someone who opted out.**

---

## ADR-015 — Partner-direct link + partner-direct journey (referrer=none, source=partner-direct)

- **Status:** Locked (2026-07-04 Cowork session). Encodes Gap 1 in [`12-Resolved-Gaps-and-Edge-Case-Decisions.md`](./12-Resolved-Gaps-and-Edge-Case-Decisions.md).
- **Context / Problem:** Not every prospect arrives through a referrer, but PIFS still earns **partner brokerage** on those accounts and needs them tracked. The referral path `gorefer.in/r/{client_id}` (ADR-001/ADR-005) always assumes a referrer id. There is no clean, honest way to record a referrer-less prospect on that path.
- **Alternatives Considered:** (1) Route referrer-less traffic through the referral path with a synthetic/house referrer id. (2) Add a distinct **partner-direct** link type and a distinct journey source. (3) Don't track referrer-less traffic at all.
- **Decision:** Add a **second link type `gorefer.in/open`** that redirects to `signup.zerodha.com/?c=ZMPHZC` **with no `r=` parameter**. The journey is stored with **`referrer = NONE`** and **`source = partner-direct`**, and is explicitly **not modelled as a fake referrer**. The **Referral Explorer filters referral journeys vs partner-direct journeys** as separate populations.
- **Reasoning:** A synthetic referrer would pollute referrer leaderboards, conversion rates, and per-referrer analytics with traffic no human referred. A dedicated source keeps partner-direct volume countable for brokerage purposes while keeping the referrer population pure. Not tracking it at all would lose visibility into a real revenue stream.
- **Consequences:** Two link types exist (`/r/{client_id}` and `/open`). The journey model carries a `source` that includes `partner-direct`. Analytics and the Referral Explorer must treat `referrer=NONE / source=partner-direct` as a first-class, filterable class rather than an error or a referral.

---

## ADR-016 — Zoho is the single authoritative source for conversion + referrer credit; single-winner attribution; off-platform conversions ingested from Zoho

- **Status:** Locked (2026-07-04 Cowork session). Encodes Gaps 2, 3, 3b, 7, 10 in [`12-Resolved-Gaps-and-Edge-Case-Decisions.md`](./12-Resolved-Gaps-and-Edge-Case-Decisions.md). Extends ADR-008 and ADR-013.
- **Context / Problem:** A prospect may click two different referrers' links, or be referred entirely off-platform (no GoRefer click at all). GoRefer needs one deterministic answer to "who is credited?" that never contradicts the money, and it must be able to represent conversions it never observed a click for. GoRefer has no Zerodha API (ADR-013) and cannot independently verify credit.
- **Alternatives Considered:** (1) Last-redirect (last-click) attribution decided by GoRefer. (2) First-click attribution decided by GoRefer. (3) **Zoho (synced from Zerodha) as the sole authority**, with GoRefer mirroring exactly one winner and never inferring or overriding.
- **Decision:** **Zoho is the single authoritative source** for both **conversion** and **referrer credit**. GoRefer credits **exactly one journey** — the **Zerodha-credited referrer**, matched by the **Zerodha client ID** (the raw `client_id` that forms the referral link, per ADR-001), **NOT by mobile**. Conversion data received (via Zoho, from Zerodha) = **opener name + opener Zerodha account ID + referrer Zerodha ID**; there is **NO mobile in conversion data** (mobile is used only on GoRefer's own lead-capture side, best-effort via a GoRefer journey-reference stamped on the Zoho lead). There is **NO last-redirect fallback**; if Zoho shows **no referrer**, GoRefer credits **no one**. **Off-platform (no-click) conversions are ingested from Zoho**: a referrer identity is created lazily on **first click OR first Zoho-imported conversion**, and **a conversion can exist with zero GoRefer clicks**. GoRefer **never assumes or overrides** Zoho.
  - **No provisional/final states.** GoRefer **mirrors Zoho's current mappings**; whatever is mapped is final. The batch around the **5th–6th of the next month** is a reconciliation/cleanup pass (fills missing mappings, fixes gaps), **not** a promotion from provisional to final.
  - **Removals propagate.** A mapping removed in Zerodha→Zoho is removed in GoRefer via a **reversal/tombstone event** (drop from the current view + recompute rollups; retain the audit trail).
  - **Lazy per-referrer history.** Historical mappings load **lazily per referrer on first appearance** (first click OR first conversion), not via a fixed bulk backfill. A full bulk backfill is an optional deferred one-off (backlog **DF-4**).
  - **Conversion uniqueness key = the opener's Zerodha account ID** (fallback `zoho_lead_id`); **upsert** on it so one account never becomes two journeys.
  - **Explicit Zoho-status → GoRefer-stage map** (published in 06/08). Past the "Redirected" stage, **Zoho is the sole authority** — mirror, never advance internally. The "Rewarded" stage is reachable **only if Zoho supplies a reward signal**; the **default is to stop at `account_opened`** (reward amounts live only in the Zerodha Console).
  - **Source/origin tag on every status change** (system/event + timestamp).
  - **Sync worker:** a reliable Zoho-status ingestion worker with a **watermark + dead-letter/retry** and **off-platform auto-create**; an **idempotency guard** keyed on a unique update id / composite; and a **sync-freshness indicator + staleness alert**.
- **Reasoning:** The reward flows through Zerodha to whoever Zerodha credited; any GoRefer-invented heuristic (last/first click) would routinely disagree with the actual payout and mis-state the winner. Making Zoho authoritative guarantees GoRefer's narrative matches the money, keeps attribution deterministic, and lets real off-platform referrals be counted without fabricating click events. Matching on the Zerodha client ID (not mobile) aligns credit with the exact identifier Zerodha itself uses; mirroring Zoho's current mappings with no provisional/final split keeps the record honest and lets removals propagate cleanly.
- **Consequences:** Conversion and credit are enrichments synced from Zoho, never asserted by GoRefer. Referrer numbers = everything Zoho credits + click detail for the link-sourced subset only. The data model must support a converted journey with zero clicks and upsert on the opener's Zerodha account ID. When Zoho is silent on referrer, GoRefer shows no credit rather than guessing.
- **Deferred:** the **Zoho-API "pull" (polling)** alternative to the webhook → backlog **DF-1** (webhook stays for now); a stronger HMAC "wax-seal" auth on the webhook → backlog **DF-2** (interim minimum when live: static key + Zoho-IP allowlist).

---

## ADR-017 — Store the true Zoho account-opening date; analytics run off it, not the import date

- **Status:** Locked (2026-07-04 Cowork session). Encodes Gap 4b in [`12-Resolved-Gaps-and-Edge-Case-Decisions.md`](./12-Resolved-Gaps-and-Edge-Case-Decisions.md).
- **Context / Problem:** Off-platform conversions (ADR-016) are imported from Zoho in bulk, often long after the accounts were actually opened. If analytics keyed off the import/sync date, every historical account would stack onto the import day and produce a false spike, corrupting every trend and cohort.
- **Alternatives Considered:** (1) Use the sync/import timestamp as the conversion date (simplest). (2) Store the **true account-opening date** from Zoho as a distinct field and drive all analytics from it.
- **Decision:** Store the **TRUE account-opening date from Zoho** as a first-class field, **distinct from the sync/import date**. Also retain **click date(s)**, **lead date**, and **sync date**. **All conversion analytics and timelines run off the true opening date**, so historical and off-platform imports sit in their **real period** with **no fake day-1 spike**.
- **Reasoning:** The economically and analytically meaningful moment is when the account actually opened, not when GoRefer learned about it. Separating the two dates keeps history honest and makes cohort/period analysis trustworthy, while retaining the sync date for operational/audit purposes.
- **Consequences:** The journey/conversion schema carries multiple dated fields (click, lead, true opening, sync). Reporting layers must default to the true opening date. Imports must map Zoho's opening-date field, not fall back to `now()`.

---

## ADR-018 — Best-effort visitor identity (first-party cookie), mobile-authoritative on submit; unique counts labelled approximate

- **Status:** Locked (2026-07-04 Cowork session). Encodes Gap 11 in [`12-Resolved-Gaps-and-Edge-Case-Decisions.md`](./12-Resolved-Gaps-and-Edge-Case-Decisions.md).
- **Context / Problem:** GoRefer needs to distinguish returning visitors and count uniques, but has no reliable cross-session identifier before a prospect submits their details. Cookies are frequently cleared or blocked; IP/device/UA are noisy. Over-claiming precise unique counts would be dishonest.
- **Alternatives Considered:** (1) Claim exact unique counts from IP/device fingerprinting. (2) **First-party cookie as the primary signal**, secondary signals as hints, uniques labelled approximate, and mobile promoted to authoritative identity on form submit.
- **Decision:** Set a **first-party cookie `visitor_id` on the first click**; **same cookie = same journey**, **new/absent = new journey**; **IP/device/UA are secondary**. **Unique-vs-total counts are BEST-EFFORT / approximate and labelled as such.** On **form submit**, promote to a **mobile-keyed identity** and **merge cookie-journeys that share that mobile** (lead-side only). **Conversions are keyed by the opener's Zerodha account ID, not by mobile** (see ADR-016). The **GET landing endpoint returns NO referrer name on initial load**; the referrer name is revealed **only after the JS human-confirmation beacon completes** and **only to a request carrying a valid, fresh server-issued one-time nonce** (plus rate-limiting / bot-filtering). The short link is kept; enumeration is made economically impractical.
- **Reasoning:** Cookies are the best available client-side signal but are lossy, so honest labelling beats false precision. Mobile is a strong, real identifier the moment it appears, which is why conversions (which always carry a mobile) are deterministic even when raw click-uniques are only approximate.
- **Consequences:** Unique metrics are surfaced with an "approximate" label. The identity layer supports promotion and merge on mobile. Conversion counting is mobile-keyed and reliable; pre-submit click-uniques are explicitly best-effort.

---

## ADR-019 — Bot/preview click filtering (UA list + JS-confirmation beacon)

- **Status:** Locked (2026-07-04 Cowork session). Encodes Gap 16 in [`12-Resolved-Gaps-and-Edge-Case-Decisions.md`](./12-Resolved-Gaps-and-Edge-Case-Decisions.md).
- **Context / Problem:** The instant a link is shared, messaging/preview bots (WhatsApp, Facebook, Telegram, Slack, Twitter, LinkedIn) fetch the URL to render a preview. Counted naively, every share would generate phantom clicks, fake uniques, and spurious journeys.
- **Alternatives Considered:** (1) Count every hit as a click. (2) Filter known bot user-agents and require a JS-executed confirmation beacon to count a "human" click. (3) Rely on server heuristics alone.
- **Decision:** Maintain a **UA bot-list** (WhatsApp, `facebookexternalhit`, Telegrambot, Slackbot, Twitterbot, LinkedInBot, Googlebot, prefetchers). Bot hits are **logged but EXCLUDED** from click / unique / journey counts. A **JS-confirmation beacon** marks a **"confirmed human click"** (preview bots don't run JS); the **click-confirmation beacon is bound to a server-issued one-time nonce**, so forged beacons are rejected. A **bot preview never creates a journey and never counts as a redirect.** A **"preview" mode requires a valid logged-in admin session** (not merely a present Authorization header).
- **Reasoning:** UA filtering catches the known offenders cheaply; the JS beacon is a robust positive signal for a real human because preview bots don't execute JavaScript. Logging-but-excluding preserves auditability and tunability without polluting headline counts.
- **Consequences:** Two-tier click record: raw (incl. bots, for audit) and confirmed-human (for analytics). A small client-side beacon is required on the landing/redirect path. The bot list is a maintained artifact that will need occasional updates. Underpins the best-effort counts in ADR-018.

---

## ADR-020 — DPDP baseline (consent, purpose limitation, 12-month retention on unconverted PII, IP minimization, manual erasure)

- **Status:** Locked (2026-07-04 Cowork session). Encodes Gap 15 in [`12-Resolved-Gaps-and-Edge-Case-Decisions.md`](./12-Resolved-Gaps-and-Edge-Case-Decisions.md).
- **Context / Problem:** GoRefer collects real prospect PII (name, mobile, email) and tracking data. India's DPDP regime requires consent, notice, purpose limitation, and data minimization. Retaining prospect PII indefinitely — especially for prospects who never converted — is unnecessary risk and liability.
- **Alternatives Considered:** (1) Collect and retain PII indefinitely with a generic privacy note. (2) Adopt a **DPDP-aligned baseline** from Sprint 1: explicit consent/notice, purpose limitation, bounded retention, IP minimization, and an erasure path.
- **Decision:** **Consent + notice + Privacy Policy link on the form**; a **cookie/privacy notice** for tracking; **purpose limitation** (data used for **referral / account-opening only**); **retention = anonymize/purge UNCONVERTED prospect PII after 12 months**; **STORE the raw IP + city as PII in a separate ERASABLE person/journey record (no hashing)**, with **PII kept OUT of the immutable event log** (events reference the person by id; a CI/code rule blocks PII in event metadata); the **raw IP inherits the same rules** (12-month purge of unconverted PII, erasure-on-request, admin-only access); **manual erasure-on-request** in Sprint 1.
- **Reasoning:** A DPDP-aligned baseline is mandatory given real PII, not optional. Purpose limitation and a 12-month purge of unconverted PII minimise both regulatory risk and stored liability. The raw IP is treated as PII and stored plainly rather than hashed, because hashing an IPv4 address is false privacy — the space is small enough to brute-force — so honest handling under DPDP (bounded retention + erasability) beats a hash that only looks private. Keeping PII out of the immutable event log and in a separate erasable record satisfies both immutability and DPDP erasure. Manual erasure is acceptable at Sprint-1 volumes and avoids over-building.
- **Consequences:** The form must render consent/notice and link a Privacy Policy. A retention job anonymizes/purges unconverted PII at 12 months. The raw IP + city are stored as PII in a separate, erasable record — never in the immutable event log, which references the person by id; a CI rule enforces that no PII leaks into event metadata. An erasure-on-request process exists (manual in Sprint 1; a candidate for automation later).

---

## ADR-021 — Runtime model: SIMPLE CENTRAL (one app + one DB)

- **Status:** Locked (2026-07-06, added after the external-review walk; authoritative decision log `review/Review-Matrix-v1.md`, new deferrals `review/Deferred-Features-Backlog.md`).

Decision: GoRefer runs as a single logical application + a single relational database (PostgreSQL). No edge/distributed deployment in Sprint 1.
Rationale: measured volume ~= 250-1,000 clicks/day, ~= 4 inserts/sec peak, ~= 0.5-3M rows/yr — about 0.1% of a single Postgres instance's capacity; central holds even at 100x, and keeps event ordering trivially correct and "never fabricate" easy.
Reliability (not edge): managed DB + automated backups + standby + health check.
Deferred: edge/distributed model -> backlog DF-3 (revisit only past ~1M clicks/month). Resolves review item #5 (04 section 8 vs 06 section 4.1 contradiction — central wins).

---

## ADR-022 — Configuration: 3-tier cascade (central -> global/admin -> user)
Decision: every configurable value resolves through CENTRAL (platform default) -> GLOBAL (admin/PIFS instance-wide) -> USER (per-user). Precedence: user -> global -> central.
Sprint 1: central + global(admin) live; USER tier designed-in but DORMANT behind ENABLE_CUSTOMER_LOGIN (Sprint 2+).
COMPLIANCE LOCK: SEBI/NSE disclosure + market-risk warning are locked at CENTRAL and cannot be weakened or removed by global or user overrides (enforces ADR-014 by constr
---

## ADR-023 — Multi-tenant boundary: single-schema `tenant_id` discriminator (NOT schema-per-tenant)

- **Status:** Locked. Originally decided as doc 12 §A2 ("Multi-tenant boundary now, SaaS later"), then the isolation *mechanism* was pinned down in `COORDINATION.md` Q-M1-1 (2026-07-06 DA answer) and restated as the ADR-024 basis note (`docs/architecture/02` ADR-024 Context/Consequences) and `CLAUDE.md` §4. No new decision is made here — this entry backfills the numbered ADR-023 slot that every other doc already cites (`ADR-023 multi-tenant boundary` in `CLAUDE.md` document map, doc 12 §A2, doc 13, `05-Database-Design.md`, `06-API-Specification.md`, S2-01/S2-03).
- **Decision:** GoRefer bakes a **`tenant_id` boundary into the data model from day one** — every tenant-scoped row carries `tenant_id` — but runs **single-tenant (PIFS only) in Sprint 1**; multi-tenancy is a later feature-flip, not a rebuild. The isolation mechanism is **single-schema `tenant_id` discriminator** — a plain `Tenant`/`Domain` registry (`apps/tenants/`) + `TenantResolutionMiddleware` + tenant-scoped model managers + composite unique constraints — **NOT** Postgres schema-per-tenant, and **NOT** `django-tenants` schema routing (that package's schema-router / tenant-DB-backend wiring is explicitly not activated; only its plain registry shape is used). This resolves `COORDINATION.md` Q-M1-1.
- **Rationale:** simpler at Sprint-1 scale, keeps platform-wide analytics easy, and gives sufficient isolation without the operational cost of physical per-tenant schemas (doc 12 §A2; Q-M1-1 answer). When multi-tenancy activates: hard cross-tenant isolation, per-tenant compliance (each AP's own NSE AP registration + disclosures, compliance-lock per tenant), and pricing/monetization become live; the config cascade's global tier becomes per-tenant-admin.
- **Consequences:** the mechanism is now machine-enforced, not just convention — `TenantQuerySet.for_tenant()` is the required choke point for every tenant-scoped query, and rail E-7 (`tests/test_architecture_rails.py`) fails CI on a raw, unscoped tenant filter (T-049, 2026-08-06). Schema-per-tenant / a per-tenant DB is **deferred** (backlog **DF-7**), revisited only if a future tenant demands physical isolation. `ADR-024`'s tech-stack decision depends on this entry for its multi-tenancy mechanism; `ADR-036`/`ADR-040` (multi-AP hierarchy, multi-AP messaging) depend on this tenant boundary, unchanged.
- **Known numbering debt:** `ADR-028` is used twice in this file — a "(base)" entry (`?s=` share-channel tag) and a later "(extended, B1)" entry (URL path prefix). Both are intentionally kept at their historical PR-time numbers; do **not** renumber either, or any ADR after them, to close this gap — it is recorded debt, not an error to silently fix.

---

## ADR-024 — Technology stack: Django + Django Ninja + HTMX + Tailwind + PostgreSQL (single-schema tenant_id)

- **Status:** Locked (2026-07-06). Chosen after a neutral external cross-check (prompt: `../../review/Framework-Evaluation-Prompt.md`) run past **ChatGPT, Grok, Gemini, DeepSeek** plus a supplementary framework analysis. Full basis + trade-offs: **[`review/Framework-Decision-Synthesis.md`](../../review/Framework-Decision-Synthesis.md)** and the per-LLM captures `review/ChatGPT-Framework.md`, `review/Grok-Framework.md`, `review/Gemini-Framework.md`, `review/DeepSeek-Framework.md`. Encoded into the build guide `implementation/10` §1.
- **Context / Problem:** GoRefer needs a concrete stack. Constraints: a **part-time solo, Python-fluent** builder who must read/debug/extend the whole codebase alone; **mobile-first, WhatsApp-driven traffic on slow Indian networks** (light pages matter); the **simple central app + one PostgreSQL** runtime (ADR-021); an **event-sourced** model; **strict typed contracts** for Zoho/WATI payloads; the **3-tier config cascade** (ADR-022); and a **multi-tenant SaaS future** (ADR-023).
- **Alternatives Considered:** (1) **Django + Django Ninja** — batteries: admin, auth, ORM, migrations, forms, templates + mature multi-tenancy (`django-tenants`); Django Ninja adds FastAPI-style Pydantic-typed async APIs. (2) **FastAPI** (+ SQLAlchemy/Alembic + Pydantic + Jinja/HTMX + SQLAdmin) — lean, async-first, native Pydantic; you assemble ORM/migrations/auth/admin yourself. (3) Node/TS + React/Next — one language front+back but a second runtime and not the founder's language. (4) Next.js full-stack. (5) Go. (6) Rails/Laravel. Options 3–6 rejected (new language and/or wrong shape for a solo Python founder / server-rendered app).
- **Decision:** Build on **Django** with **Django Ninja** for the JSON/API layer, **server-rendered Django templates + HTMX + Tailwind CSS** for the UI (NO React/SPA in Sprint 1), **PostgreSQL** (ADR-021), and **single-schema `tenant_id` discriminator isolation** as the multi-tenancy mechanism for the ADR-023 boundary (matching ADR-023 + 05-Database-Design; **NOT** schema-per-tenant — resolves COORDINATION Q-M1-1). Background work starts with `transaction.on_commit()` + a light DB-backed queue (django-q / django-rq); add Celery/Redis only when scheduled workflows demand it. The **customized Django admin** jump-starts the M7 internal dashboard; **admin-only auth is env-bootstrapped** (ADR / REQ-016). Typed contracts use **Pydantic (via Django Ninja) schemas** for Zoho/WATI payloads.
- **Reasoning:** The external cross-check was **unanimous** on the parts that matter structurally — Python; **server-rendered templates + HTMX + Tailwind, not React/SPA** (light on cheap Android over slow networks); PostgreSQL; an **append-only event table** (no Kafka/CQRS); a **non-blocking redirect** (validate + 302, background-write the click, idempotent via unique constraints); the adapter pattern; **`tenant_id` from day one**; and **API-first** so a richer customer SPA can come later on the same API. The only split was FastAPI vs Django, which tied **2–2** (ChatGPT/Gemini → FastAPI; Grok/DeepSeek → Django). Two things break the tie toward Django: (a) for the **already-locked server-rendered + HTMX** route, Django is the more natural home — its templating, forms, ORM, and admin are purpose-built for server-driven rendering, whereas FastAPI + HTMX means hand-assembling those; and (b) the founder's own priorities — **part-time solo, admin/CRUD-heavy app, multi-tenant SaaS ambition** — favour batteries (admin/auth/migrations + mature multi-tenancy tooling). **Django Ninja preserves FastAPI's one real edge** (Pydantic-typed async APIs) inside Django, and async is moot at ~4 req/s (sync + `transaction.on_commit()` is ample). FastAPI is the recorded, equally-safe close second.
- **Consequences:**
  - The repo is a **Django project** (apps such as `referrals`, `events`, `config`, `tenants`, `integrations`, plus `templates/` + `static/` for Tailwind and Django Ninja API routers). Uses the **Django ORM + Django migrations** (NOT SQLAlchemy/Alembic).
  - The `/r/{client_id}` **redirect is a sync Django view**: format-validate → 302, with the click/journey write handed to `transaction.on_commit()` (or the light queue) so it never blocks; idempotency via unique constraints (ADR-021, review #11).
  - The **admin dashboard** leverages a customized Django admin + HTMX (per ADR-022/ADR-014, the compliance block is injected via middleware + a template tag and is non-removable).
  - **Multi-tenancy = single-schema `tenant_id` discriminator (DECIDED; resolves Q-M1-1):** every tenant-scoped row carries `tenant_id` (matches ADR-023 + the 05-Database-Design composite keys). Isolation is enforced by **tenant-scoped model managers + a tenant-resolution middleware + composite unique constraints**, NOT by Postgres schema-per-tenant. `django-tenants` / schema routing is NOT the mechanism (a plain `Tenant`/`Domain` registry suffices). Schema-per-tenant or a per-tenant DB is DEFERRED (backlog **DF-7**), an option only if a future tenant demands physical isolation. Start with one bootstrap tenant (PIFS).
  - **Revisit trigger:** if GoRefer ever pivots to an API-first customer SPA, or hits scale/physical-isolation limits that single-schema `tenant_id` cannot serve, revisit FastAPI (the recorded, equally-safe close second) and/or schema-per-tenant (backlog DF-7). Until then, Django + Django Ninja + HTMX + Tailwind + Postgres with `tenant_id` isolation stands.

---

> **Note (DA, 2026-07-09):** the ADR-024 truncation is fixed above, and ADR-025–030 are now written up below (they were previously only grounded in the S2-01/S2-02 specs + COORDINATION/commit history). Track-B ADRs (028-ext, 031, 032, 033) follow.

---

## ADR-025 — A public referral share carrying `c=ZMPHZC` is a PIFS advertisement (hard gates)
- **Status:** Locked (2026-07-08). Basis: `docs/sprint2/S2-01` §4/§13; NSE/COMP/55482 §3.2, §4.1/4.2, cl.15.
- **Context:** A referral link/creative broadcast to a non-1:1 audience while carrying the AP partner code is advertising by an Authorised Person, which an AP cannot self-approve.
- **Decision:** Treat every public share creative as a PIFS advertisement: (a) **Zerodha written pre-approval required before go-live** (external gate — build/demo behind it); (b) the SEBI/NSE **disclosure + market-risk block is baked into every creative and un-removable**; (c) **no paid/sponsored boosting** and no context-free link spam; (d) the reward wording lives behind a **single config toggle** (`SHARE_SHOW_REWARD`, default off) so it flips without code if Zerodha approves it. A genuine 1:1 client share is lighter (see the §4.4 determination in `Wati-Project/wati-shared-automation-inventory.md` §5d).
- **Consequences:** software ships fully but stays behind the approval gate; disclosures cannot be weakened by lower config tiers (ADR-022 compliance lock).

> **AMENDED 2026-07-20 (ADR-038):** *The locked text above is unchanged and still governs for PIFS today. This annotation records two changes of scope.*
>
> **(1) Advisory softening for AP-authored creatives.** Gates (a) *partner written pre-approval before go-live* and (c) *no paid boosting / no context-free link spam* remain the standard, but for **AP-authored** share creatives they are enforced **advisory** per ADR-038: GoRefer verdicts the creative, cites the rule, names the breach, recommends a fix, and the AP may proceed only via an explicit first-person acknowledgment that is immutably recorded. Gate (b) is **NOT softened** — the SEBI/NSE **disclosure + market-risk block stays baked into every creative and un-removable** (ADR-038 DA Ruling 1: GoRefer's injected block is hard, the AP's own claims are advisory). Gate (d), the reward-wording config toggle, is unchanged.
>
> **(2) DA RULING — the premise generalizes; this ADR is no longer PIFS/`ZMPHZC`-specific.** With the doc 13 §8 correction (ADR-041), a partner code is **not** the partner's — it belongs to the **(AP, partner) pair**. `ZMPHZC` is *PIFS's* AP code at Zerodha, and every other AP carries their own. Therefore the rule reads, generally: **a public share carrying an AP's own partner code is THAT AP's advertisement, not PIFS's.** The advertising obligations, the pre-approval relationship with the partner, and the consequences of a non-compliant creative attach to **the AP whose code the creative carries** — which is the same entity ADR-036 makes the tenant and ADR-038 makes the decision-holder. Read the locked text above with "PIFS" as "the acting AP" and "`c=ZMPHZC`" as "the acting AP's partner code for that partner"; for Sprint 1, where PIFS is the sole AP, the two readings coincide exactly and nothing changes in behaviour.

## ADR-026 — One role-scoped Referral Profile template (admin/self via masking)
- **Status:** Locked (2026-07-08). Basis: `S2-01` §5.1/§13.
- **Context:** Both an admin (full PII, any referrer) and a self-service referrer (own record only) need a profile view; two separate screens would drift.
- **Decision:** **One template**, role-scoped by config: admin role → full detail + admin chrome; referrer role → locked to own record, `PII_MASK_FOR_CUSTOMER_VIEW` on, admin chrome hidden, a prominent Share action. The Share **Launcher** is a **separate** share-only surface (customize + share, no stats). Difference is config (role → masking + action visibility), not code.
- **Consequences:** self-service profile is Sprint-3-gated behind `ENABLE_CUSTOMER_LOGIN`; no divergent second screen to maintain.

## ADR-027 — Customer identity: Google OAuth + Client-ID binding, Zoho-verified, admin fallback
- **Status:** Locked (2026-07-08); **build deferred to Sprint 3** (S2-02 rescope). Basis: `S2-01` §8/§13.
- **Context:** Referrers need self-serve login bound to their Zerodha Client ID, without any Zerodha API and without handling Zerodha passwords.
- **Decision:** Google OAuth sign-in; on first login the referrer enters Client ID + registered mobile; **auto-bind if the Google email OR the entered mobile matches the Zoho record** for that Client ID (both normalized); mismatch → a **pending-verification** state routed to an admin queue (Ashok approves/rejects). No Zerodha API; no Zerodha password ever handled; mobile-OTP self-verify deferred (DF-6).
- **Consequences:** flips `ENABLE_CUSTOMER_LOGIN`; anti-impersonation gate needs no external API; additional providers later.

## ADR-028 (base) — Share attribution via `?s=` channel tag, recorded then stripped pre-redirect
- **Status:** Locked (2026-07-08); implemented in M11. Basis: `S2-01` §7. **Extended by ADR-028 (B1)** for the path-prefix form.
- **Context:** Each share surface must be attributable without leaking anything into the outbound Zerodha URL.
- **Decision:** Each share appends `?s={platform}` (`wa, fb, x, li, tg, ig, email, copy`; param name config, `SHARE_CHANNEL_PARAM`). `/r/{client_id}` records `s` as the click's share-channel (reuses the Sprint-1 Channel column), then **strips it before the 302** to Zerodha. Preview crawlers get the OG card but are excluded from human-click counts.
- **Consequences:** per-channel analytics per referrer; the Zerodha 302 Location stays clean; the WhatsApp-button limitation is handled by the path-prefix extension (ADR-028 B1).

## ADR-029 — WhatsApp-native referral amplification (Wati quick-reply → GoRefer webhook → session kit)
- **Status:** Locked (2026-07-08). Basis: `S2-02` §2/§12.
- **Context:** For the WhatsApp sprint, a referrer should get a ready-to-forward kit inside WhatsApp rather than via a web launcher.
- **Decision:** PIFS nudges opted-in clients with a Wati template; a **quick-reply button** opens the 24h session; the tap routes (Wati keyword/flow, or a webhook to GoRefer) to deliver the forwardable kit (image + caption + `gorefer.in/r/{client_id}?s=wa` + disclosures) via session messages. Chosen over the multi-platform web launcher (deferred to Sprint 3), which is not discarded.
- **Consequences:** GoRefer's job shrinks to the tracked redirect (+ optional ingest); the delivered kit is a free session message (uncapped), avoiding the MARKETING 131049 cap on the kit itself.

## ADR-030 — Wati template variable convention + route via `gorefer.in`, never direct-to-Zerodha
- **Status:** Locked (2026-07-08). Basis: `S2-02` §3/§12; memory `wati-setup-reference`.
- **Context:** The legacy Wati referral template exposed `c=ZMPHZC` in a button URL straight to `signup.zerodha.com` and bypassed click tracking; variable naming was inconsistent.
- **Decision:** Named variable convention **`{{name}}`, `{{client_id}}`** (never "ID"); reward wording baked from config at submit time, not a runtime var. GoRefer **routes the referral button through `gorefer.in/r/{client_id}` (never direct-to-Zerodha)** so the partner code is injected server-side (hidden) and every click is tracked. A whole-template must use one variable format (named), enforced 2026-07-09.
- **Consequences:** partner code never appears in a client-facing URL; per-referrer attribution + click tracking preserved; template naming convention `gorefer_{partner}_{purpose}_{YYYY_MM_DD}`.

---

## ADR-028 (extended, B1) — Share channel carried as a URL path prefix `/r/{channel}/{client_id}`

- **Status:** Locked (2026-07-09), extends ADR-028 (the M11 `?s=` share-channel capture/strip).
- **Context:** WhatsApp dynamic URL buttons require the template variable to be the LAST path/query token, so `?s=wa` cannot trail `{{client_id}}` in a button URL like `gorefer.in/r/{{client_id}}`. The `wa` attribution tag therefore cannot ride as a query param on that button.
- **Decision:** Accept the share channel ALSO as a **leading path segment** — `GET /r/{channel}/{client_id}` (e.g. `/r/wa/RJ4521`) — in addition to the legacy `/r/{client_id}?s=`. The channel is read from the path, normalized through the same config-driven map (`wa→WhatsApp … unknown→other`), recorded as the click's `metadata["channel"]`, and **stripped before the 302** by construction (the destination is assembled server-side from the program template). A narrow `{channel}` path converter (1–8 lowercase letters) ensures the segment can never shadow a client_id or the `continue` route.
- **Consequences:** the pending `gorefer_zerodha_referral_2026_07_09` template's URL button (`/r/wa/{{client_id}}`) keeps `wa` attribution; no schema change (reuses the Sprint-1 Channel column); legacy `?s=` form unchanged.

## ADR-031 (B2) — Per-sub-broker Disclosure Page `/d/{slug}` as the canonical §4.4 host

- **Status:** Locked (2026-07-09).
- **Context:** A light WhatsApp message and a `direct`-bypass link (ADR-032) do not inline the full SEBI/NSE AP identification block; NSE §4.4 permits this only if a **linked page** carries the full prescribed disclosures. A single, durable host for those disclosures is needed — one that also composes multiple regulators for a sub-broker who does securities + insurance + loans.
- **Decision:** A public per-sub-broker page **`GET /d/{slug}`** (e.g. `/d/pifs`) composes each **active** partner/program's regulator-mandated disclosure block for that tenant, in **regulator order** (SEBI/NSE → IRDAI → RBI → other), filled with the tenant's own values. Content is **config-driven** (each program carries a `disclosure_template` + `regulator` + `disclosure_sequence`; blank template → the canonical central AP block + market-risk warning). **No PII**; **no partner code / raw Zerodha URL**; the view writes no event, so a crawler hit is inherently excluded from human counts. It is **distinct** from the profile/preference surface.
- **Consequences:** a new partner/regulator is a data row, not code; a lapsed partnership's block drops off; the message/`direct` link can point here and stay compliant.

## ADR-032 (B3) — `LANDING_MODE` per-tenant bypass + DERIVED `MESSAGE_DISCLOSURE_LEVEL`

- **Status:** Locked (2026-07-09).
- **Context:** Some sub-brokers want a frictionless `/r/{id}` that redirects straight to Zerodha (no landing page); but the landing page is currently the disclosure host, so bypassing it risks a "light message + no disclosure host" compliance gap (§3b).
- **Decision:** Per-tenant **`LANDING_MODE = page | direct`** (config cascade, default `page`). `direct` logs the click on `transaction.on_commit` then 302s straight to Zerodha (channel/`?s` stripped, code server-side, landing skipped). **`MESSAGE_DISCLOSURE_LEVEL` is DERIVED, never free-set**: `full` iff `direct` AND no live `/d/{slug}` host; else `light`. A hand-set `direct`+`light`+no-`/d/` combination is **refused** (`DisclosureCouplingError`) so the bypass-without-disclosure gap cannot be configured open. Depends on ADR-031.
- **Consequences:** frictionless conversion for tenants that want it, with the disclosure coupling enforced in one place; guardrails (no partner code in body, clean 302) unchanged.

## ADR-033 (B4) — Assisted-referral capture via `POST /api/wati/webhook` → Zoho lead

- **Status:** Locked (2026-07-09).
- **Context:** The referrer "Refer directly (we'll assist)" branch captures a prospect's Name + Mobile (Email optional) so Ashok can follow up — third-party PII with a DPDP consent obligation. The old multi-broker flow's version of this had a consent gap.
- **Decision:** The Wati flow POSTs `{client_id (referrer), name, mobile, email?, consent?}` to **`POST /api/wati/webhook`** (auth: static key + IP allowlist, HMAC wax-seal deferred DF-2). GoRefer lazily resolves/creates the referrer identity+referral, then creates **one Zoho lead** through the **same capture-first pipeline** as the landing form (`capture_lead`, behind `ENABLE_ZOHO_WRITE` — log-only in demo), marked `lead_source=whatsapp_assisted`, `submitted_by=referrer`, with `consent` + `consent_captured_at` (DPDP). **Never a password** (credential-shaped fields rejected at the edge and in the service); **deduped** on (referral, prospect mobile); PII stays on the erasable Prospect/Lead, never in the immutable event log; status never set here (Zoho only, guardrail #2).
- **Consequences:** one lead pipeline (not two); assisted referrals re-added with the consent guardrail; "forward the link" stays the primary CTA.

## ADR-034 (Q-M-PREF) — Preferences screen as the UI surface for the user-tier config cascade

- **Status:** Locked (2026-07-10). Design approved by Abhay 2026-07-09 (`mockups/preferences-screen-mockup.html`, Variant C · Cobalt). Basis: `S2-03` §14. Depends on ADR-022 (config cascade), ADR-031 (`/d/{slug}`), ADR-032 (`LANDING_MODE` coupling).
- **Context / Problem:** Per-tenant config (landing mode, reward wording, contact numbers, share channels, assisted-referral toggle, partnerships) had no operator surface — values were only settable by seeding/DB edits. Critically, `LANDING_MODE=direct` is a compliance-sensitive bypass (ADR-032): it must be chosen deliberately by the operator **through a screen that enforces the disclosure coupling**, never flipped by a backend override where the coupling could be bypassed.
- **Alternatives Considered:**
  1. **Backend/env override for `LANDING_MODE`** — rejected: divorces the flip from the ADR-032 guard (a live `/d/{slug}` must exist) and from an audit trail; Abhay explicitly ruled it out ("PIFS goes `direct` only through this screen").
  2. **A separate `TenantPartnership` table** (as `S2-03` §10 sketched) to drive `/d/{slug}` — rejected for Sprint 1: the built system already composes the disclosure page from the tenant's **active `ReferralProgram` rows** (ADR-031, `disclosure_service.compose_disclosures`). Introducing a parallel table would duplicate the composition source. The screen manages those existing rows instead (add/activate/deactivate). Reconciliation logged as COORDINATION Q-M-PREF-1.
- **Decision:** A **`GET/POST /admin-panel/preferences`** screen (admin-only in Sprint 1, staff-gated, tenant-scoped; becomes the sub-broker's self-serve settings when `ENABLE_CUSTOMER_LOGIN` lands), server-rendered Django + HTMX, matching the approved Variant-C mockup. Each control persists to the **GLOBAL (tenant) tier** of the cascade via a new `config.cascade.set_tenant()` helper (which refuses compliance-locked keys). Keys: `landing_mode`, `share_show_reward`, `referrer_reward_claim`, `support_helpline_phone`, `wati_business_number`, `share_channels_allowlist`, `enable_assisted_referral` (names centralised in `apps/config/preferences.py`; central baselines seeded so behaviour is unchanged until overridden). **The ADR-032 coupling is enforced AT THE SCREEN:** `direct` is only selectable/persistable when the tenant has a **live** `/d/{slug}` — defined as the disclosure page enabled **AND** at least one active `ReferralProgram` composing a real block (`landing_mode.has_live_disclosure_page`). A POST requesting `direct` without a live disclosure page is forced back to `page` with a notice; the segment is disabled in the UI; and deactivating the last active partnership while `direct` is refused. Partnerships that drive `/d/{slug}` are the tenant's `ReferralProgram` rows (add = new Partner+Program row, config-over-code per ADR-031).
- **Reasoning:** one UI home for the user-tier cascade; the most compliance-sensitive setting (`direct`) can only be turned on where the disclosure host is proven live, closing the ADR-032 gap at the exact surface an operator uses; no new table when the existing composition source suffices; `LANDING_MODE` never a backend flag (a test asserts `settings` carries no `LANDING_MODE`).
- **Consequences:** saved values take effect immediately (landing page reads helpline/WhatsApp number/reward wording from the cascade); the incentive-claim compliance lock is untouched (the reward *claim text* is a separate, unlocked tenant field, while the locked central `referral_incentive_claim` remains the audit/fallback copy); write flags (`ENABLE_ZOHO_WRITE`/`ENABLE_WATI_SEND`) stay OFF; Postgres-only, demo works offline.

## ADR-035 (Q-M-OTP) — Referrer self-service identity/ownership model + pluggable OTP delivery port

- **Status:** Locked (2026-07-11). Design by Abhay 2026-07-11 ("make WhatsApp/Wati primary, pluggable port, very easily configurable for admin"). Basis: `S2-03` §15 + Mission Q-M-OTP. Depends on ADR-001 (raw client_id link), ADR-022 (config cascade), ADR-023 (`(tenant_id, client_id)` boundary), ADR-034 (Preferences screen), M5 Wati adapter/contract. **Built behind `ENABLE_OTP_LOGIN=false`; the login UI + identity binding themselves are Sprint-2 (customer-login gate) — THIS ADR/mission builds only the OTP delivery layer.**
- **Context / Problem:** A referrer's GoRefer link IS his raw Zerodha Client ID (ADR-001), which is **public** (it sits in the shared link). So self-service login must prove OWNERSHIP of a public id — it can never accept a typed Client ID (anyone could type `DA1707` and read that referrer's analytics), and it must NEVER send an OTP to a number the user types. There is NO Zerodha API to verify against. Separately, the OTP *channel* must be operator-switchable (WhatsApp primary, SMS/manual fallback) with no code change, and OTP delivery must assert real delivery (the account's historical ~60% Wati send-failure is survivable for marketing but fatal for a time-sensitive code).
- **Identity model decision:** **no link-claiming step** — a login only *unlocks the retroactive view* of everything already keyed to the Client ID (lazy-journey creation recorded it from the first click). Ownership is proven, not asserted:
  - **Path A (known referrer, Client ID in Zoho):** resolve the Client ID → the **on-file** mobile/email in Zoho (verified live 2026-07-11: Zoho Contact carries `ClientId` + `Mobile`, e.g. QPJ023 → 9335138774) → send an **OTP to that on-file channel** (never a typed number) → bind the login to **`(tenant_id, client_id)`** (ADR-023).
  - **Path B (unknown referrer):** human-reviewed **evidence** — a screenshot of the logged-in Zerodha console showing **Client ID + registered name together** (name is the ownership signal, the id alone is public); minimal PII, screenshot purged after verification (DPDP/ADR-020); OCR auto-approval deferred to Sprint 3+. On approval the referrer is upserted into Zoho so future logins fall back to Path A.
- **OTP-port decision (built now):** OTP delivery is **ports-and-adapters**. A single port `OtpDeliveryChannel.send(recipient, code, ttl_seconds, context) -> DeliveryResult{status, provider_ref, error}` is terminal-status aware (success = proven delivery, never HTTP 200). Adapters: **`WatiWhatsAppOtpAdapter` (PRIMARY** — AUTHENTICATION-category template `gorefer_login_otp` with a copy-code button, via the M5 Wati adapter; verifies terminal delivery, cascades on non-delivery), `SmsOtpAdapter` (interface+stub, provider TBD → DF-OTP-SMS), `ManualOtpAdapter` (Path-B assisted handoff), `DemoOtpAdapter` (log-only offline when `ENABLE_OTP_LOGIN` off). `OtpService.issue()` generates a CSPRNG code, stores **hash+expiry ONLY** (peppered, identity-bound, salted — never plaintext, never logged), sends via the primary and **auto-cascades down the configured fallback list** on non-delivery; `OtpService.verify()` checks hash+expiry+attempts, **single-use**. All behavioural knobs are **per-tenant config-cascade keys** (`OTP_PRIMARY_CHANNEL`, `OTP_FALLBACK_CHANNELS`, `OTP_WHATSAPP_TEMPLATE`, `OTP_CODE_LENGTH`, `OTP_CODE_TTL_SECONDS`, `OTP_MAX_VERIFY_ATTEMPTS`, `OTP_RESEND_COOLDOWN_SECONDS`, `OTP_RATE_LIMIT_PER_IDENTITY_PER_HOUR`), **all editable on the Preferences screen** (config-over-code: swap channel/order/limits with no deploy). Master `ENABLE_OTP_LOGIN` (env flag) gates the whole feature.
- **Alternatives Considered:** (1) accept a typed Client ID + typed number for OTP — **rejected** (public id + attacker-controlled channel = trivial account takeover of analytics). (2) SMS-primary — **rejected** as primary (Wati WhatsApp auth template ≈ ₹0.115/msg, reportedly < half the cheapest SMS OTP; SMS kept as a fallback slot). (3) Hardcode the channel — **rejected** (violates config-over-code + the "easily configurable for admin" requirement).
- **Consequences:** login (Sprint 2) reveals retroactive analytics with zero claiming; OTP channel is a config change, not a deploy; codes are unrecoverable from the DB (hash-only) and single-use/rate-limited/per-tenant; demo mode sends nothing (log-only) so the flow is testable offline. **GO-LIVE preconditions (NOT build blockers):** fix Wati delivery reliability before OTP depends on it; create + Meta-approve the AUTHENTICATION template. **Open (surfaced as QUESTIONs, stubbed not guessed):** the SMS provider (DF-OTP-SMS) and the exact Zoho-READ module/method for the `client_id → on-file channel` lookup (Q-M-OTP-2) — the recipient resolver falls back to Path B (assisted) until wired, never guessing a number.
---

> **DA ratification pass (2026-07-20).** ADR-036…041 below ratify
> `docs/architecture/13-Partner-Hierarchy-and-Vendor-Independence.md` (all items
> owner-dispositioned 2026-07-19; nothing left open). Every one of them is
> **model-only — NOT scheduled** (doc 13 §5): they bind the multi-AP mission when it
> starts and change nothing in Sprint 1. They are recorded now because the decisions
> are made, and would otherwise be re-litigated from memory when that mission opens.

---

## ADR-036 — Five-level partner hierarchy; the tenant is the Authorized Partner

- **Status:** Locked (2026-07-20, DA ratification of doc 13). **Model-only — not scheduled; binds the multi-AP mission when it starts.** Ratifies **D-13-1** + the NSE isolation mandate + **D-13-6** + **O-1**. Basis: doc 13 §1/§6; owner (Abhay) 2026-07-19; the 2026-07-09 layered-architecture draft. Depends on ADR-023 (multi-tenant boundary), ADR-024 (single-schema `tenant_id`).
- **Context / Problem:** GoRefer owns no referral program; it hosts other people's. Sprint 1 has exactly one Partner (Zerodha) and one tenant (PIFS), so "partner", "program" and "tenant" currently collapse into each other and the distinction is invisible. It stops being invisible the moment there is a second AP: rules arrive from **four different altitudes** (regulator, partner group, partner, AP), and a design with no place to hang each of them will hang them all in code. Worse, **NSE bars one person from operating across two brokers** — a tenancy cut in the wrong place would make the forbidden arrangement representable.
- **Alternatives Considered:**
  1. **Tenant = partner** (Zerodha is a tenant) — rejected: puts every AP of a partner in one shared bucket, so a partner's APs could see each other's referrers, and the NSE isolation rule becomes unenforceable.
  2. **Tenant = partner group / category** — rejected: even coarser; same failure, worse.
  3. **Tenant = the human operator** — rejected: this is exactly what NSE forbids. One human legitimately operating two broker-APs must appear to the system as two separate, non-communicating tenants; making the human the tenant makes cross-broker leakage the default.
  4. **Tenant = Authorized Partner (AP)** — chosen.
- **Decision:** GoRefer models a **five-level tree** — **Regulator → Partner Group → Partner → Authorized Partner (AP) → referral links/referrers/journeys/events** — and **the tenant IS the AP. One AP = one isolated login.**
  - **Regulator** is not a GoRefer entity; it is a *rule source* attached to a partner group (SEBI/NSE for brokers, IRDAI for insurance, RBI for loans).
  - **Partner group** is a taxonomy node carrying the regulator's rules and group-level defaults (schema at build time: a `PartnerGroup` model + `Partner.partner_group` FK).
  - **Partner** carries its own rules binding all its APs, **and the destination-URL template** (`ReferralProgram`) — but **NOT the partner code** (see ADR-041).
  - **AP = tenant** carries its own rules, links, numbers, templates, timings and formats.
  - **NSE isolation mandate (binding):** one login = **exactly one** NSE-broker AP + any number of **non-NSE** partners side by side. A second broker **forces a new isolated login**. This is the reason the tenancy cut is at the AP.
  - **Multi-login UX (D-13-6, stated requirement):** one human operating two broker-APs experiences them as **two separate people** — separate logins, **no cross-tenant view, no combined dashboard, no shared search, and no "switch account" affordance that carries data across**. Convenience features that would aggregate across two broker tenants are **not permissible**, however reasonably they are asked for; the isolation is a regulatory requirement, not a UX preference.
  - **AP onboarding verification (O-1, in scope):** before an AP's links go live the platform **verifies the AP's regulator registration number** (e.g. NSE AP reg. no.) **and their partner code for each partner** they are registered with. Verification is a precondition of activation, not a background task.
- **Reasoning:** The cut has to sit where the *legal* boundary sits. The regulated entity is the AP; the AP is who a regulator suspends, who owns the referrer relationships, and who NSE forbids from doubling up across brokers. Putting the tenant there makes the legal boundary and the technical isolation boundary **the same line**, so isolation bugs and compliance bugs become the same class of bug, and the existing `tenant_id` machinery (ADR-023/024) already enforces most of it. O-1 exists because advisory content enforcement (ADR-038) protects the platform on *what is said* but nothing protects it on *who is saying it* — an unregistered person soliciting through GoRefer is direct platform exposure, and it is cheap to check a registration number once at onboarding and expensive to explain afterwards.
- **Consequences:**
  - Sprint 1 is **unchanged**: the tenancy cut is already correct, only PIFS is seeded. The gap is purely the missing upper tiers (`PartnerGroup`, regulator/rule rows) — none of which is built now (doc 13 §5).
  - A new partner group (insurance, loans) becomes **data plus its regulator's rule rows**, not a rebuild.
  - The multi-login rule is a **permanent product constraint**: any future "unified view" feature must be checked against it before design, and refused for two NSE-broker tenants.
  - Onboarding acquires a verification step, and therefore a state before "active" (see the ADR-040 AP lifecycle).

---

## ADR-037 — Dual-cascade semantics: one resolver, per-key `locked_at_tier`

- **Status:** Locked (2026-07-20, DA ratification of doc 13). **Model-only — not scheduled; binds the multi-AP mission when it starts.** Ratifies **D-13-2** as decided in doc 13 §7. Basis: doc 13 §2/§6/§7. Extends ADR-022 (3-tier config cascade) and the ADR-014 compliance lock.
- **Context / Problem:** Rules and configuration look alike — both are "a value resolved for a tenant" — but they **merge in opposite directions**. Config is *override, nearest-to-the-AP wins*: a tenant's landing mode should beat the platform default. Compliance is *tighten-only, most-restrictive wins*: SEBI's rules beat Zerodha's, which beat PIFS's own stricter limits, and **no lower tier may ever loosen a higher one**. Today this is approximated by `COMPLIANCE_LOCKED_KEYS` resolving central-only — a 2-level stand-in for what is really a 5-level path. If the two ever share one nearest-wins resolver, **a tenant override can out-vote a regulator**, silently, through a config screen.
- **Alternatives Considered:**
  1. **Two entirely separate resolvers** (a config `resolve()` and a parallel compliance resolver) — rejected: two code paths that must agree about tiers, tenancy and caching will drift, and every new key must be routed by hand into the right one; the drift would stay invisible until it mattered.
  2. **Per-key `locked_at_tier` on one resolver** — chosen.
  3. **Compliance as code (constants/branches), config as data** — rejected: makes each new regulator or partner rule a deploy, which defeats the purpose of a partner-group tier and contradicts config-over-code.
- **Decision:** **One resolver, with per-key lock metadata.** Generalize `COMPLIANCE_LOCKED_KEYS` into a per-key **`locked_at_tier`** across the full five-tier path (regulator → group → partner → AP/tenant → user):
  - **Unlocked keys** keep today's ADR-022 semantics exactly: **nearest-to-the-user wins**.
  - **A key locked at tier T resolves at T and stops.** Lower tiers may **not** override it — their values are not consulted, so there is no "was it overridden?" ambiguity to audit later.
  - **Compliance keys must never ride the config cascade.** The lock is precisely what removes them from it. Concretely: the SEBI/NSE disclosure block, the market-risk warning and the reward-claim wording remain resolvable **only** at their locked tier, exactly as ADR-014/ADR-022 already enforce at the 2-level approximation.
  - **Tighten-only is expressed as the lock, not as a merge.** A lower tier that wants to be *stricter* does so by setting its **own** additional key (its own stricter limit), never by rewriting the higher tier's value. There is no union-of-restrictions merge function to get wrong.
  - Locks bind **platform config and platform-rendered surfaces**. For **AP-authored communications** the enforcement mode is **ADVISORY** per ADR-038 — the lock governs what the *platform* renders, not what the *AP* is permitted to say.
- **Reasoning:** One resolver keeps tenancy, caching and tier-walking in a single place, so there is exactly one thing to test and one thing to get right; the per-key metadata is what lets the two semantics coexist without a second code path. Expressing tighten-only as a **hard stop at the locked tier** rather than as a most-restrictive *merge* is deliberate: merging requires the system to *compare* restriction strength across arbitrary value types (text blocks, lists, numbers), which is either impossible or a source of subtly wrong answers. A stop is total, obvious and trivially auditable — the resolved value always traces to exactly one tier.
- **Consequences:**
  - ADR-022 stands unchanged for every unlocked key; this is a generalization, not a replacement. The current `COMPLIANCE_LOCKED_KEYS` set becomes the seed of the `locked_at_tier` table.
  - Every new config key must declare a lock tier (default: unlocked). A compliance key introduced without a lock is a defect, and the natural target of a future guardrail test.
  - The 5-tier path is **not built now**. What is locked here is the semantics, so the multi-AP mission extends the existing resolver rather than inventing a second one.

---

## ADR-038 — Compliance enforcement for AP-authored content is ADVISORY, with an acknowledged, audited bypass

- **Status:** Locked (2026-07-20, DA ratification of doc 13). **Model-only — not scheduled; binds the multi-AP mission when it starts.** Ratifies the doc 13 §2 enforcement-mode decision (owner, 2026-07-19), the 4-part popup requirement, **O-3** and **O-4**. **Amends ADR-014 and ADR-025** (annotations recorded under each). Depends on ADR-036 (the partner-group tier supplies the regulator), ADR-037 (locks).
- **Context / Problem:** ADR-014 makes compliance a hard blocking gate. That is right for what **GoRefer itself** renders and generates. Extended naively to a multi-AP platform it becomes something else: GoRefer would be *refusing to let a regulated professional publish their own words*. GoRefer is not the AP's compliance officer and cannot be — it does not carry the AP's registration, cannot see their full context, and a rule library will sometimes be wrong or stale. But doing nothing is equally wrong: a platform that silently distributes a violating claim has no defence at all.
- **Alternatives Considered:**
  1. **Hard block for AP-authored content** (extend ADR-014 as-is) — rejected: GoRefer assumes a decision authority it does not hold; a false positive in the rule library becomes GoRefer censoring a compliant AP; and it pushes the AP to route around the platform entirely, destroying the audit trail that is the platform's actual protection.
  2. **No checking** — rejected: no informed consent, no evidence, maximum platform exposure.
  3. **Advise + explicitly acknowledged, immutably audited bypass** — chosen.
- **Decision:** For **AP-authored content sent from the AP's own number/identity**, the rule engine **returns a verdict** — compliant, or violates rule N — and **the AP retains the final call**. A bypass is possible **only** through an explicit, recorded acknowledgment.
  - **The bypass popup** is shown at the moment the AP saves/submits/sends content that fails a check, and MUST contain all four of:
    1. **The specific rule broken, cited by name and source** — for brokers a SEBI/NSE rule; for another partner group, that group's regulator (IRDAI, RBI, …). Which regulator applies is resolved from the **partner-group tier** (ADR-036), so citations are **data rows, not code** — a new partner group brings its own rule set with no rebuild.
    2. **What in the AP's content breaks it** — the offending claim or omission, named concretely, not a generic warning.
    3. **The platform's recommendation** — how to fix it so it becomes compliant.
    4. **An explicit first-person consent control** to proceed anyway — e.g. *"I understand this violates [rule ref]. I agree that I am breaking this rule and I choose to continue on my own responsibility."* — a deliberate act (checkbox / typed confirmation + button), **never pre-ticked, never the default path.**
  - **The audit record** is immutable, one per event, and captures: **tenant, user, timestamp, content snapshot/hash, rule id + the exact rule-text version shown, verdict, recommendation shown, and the action taken** (*fixed* vs *continued anyway*).
  - **O-3 — rule-library ownership.** Rules-as-data need a maintainer and a cadence: **each rule row carries its source circular reference and a review date**; the library has a named owner (**Abhay/DA until delegated**) and a periodic review. Stale rule text is not neutral — it is **wrong advice published under the platform's name**, which is exactly why the audit record pins the rule-text *version* that was shown.
  - **O-4 — the platform–AP agreement mirrors the popup.** The onboarding contract states what the popup states: the platform advises, the AP decides, regulated conduct is the AP's responsibility. A contract clause and per-event recorded consent are materially stronger together than either alone.
- **DA RULING 1 — the render boundary (resolves an ambiguity ADR-014 would otherwise re-litigate).** When GoRefer **renders or generates** an artifact that contains AP-authored copy, the two halves of that artifact are governed differently, and the split runs *inside* the artifact:
  - the **auto-injected disclosure/risk block is HARD and non-removable** — injection is intrinsic to the render/asset path (ADR-014) and is **never bypassable by acknowledgment**; no popup, no checkbox, no acknowledgment reaches it;
  - the **AP's own claims within that artifact are ADVISORY** — checked, verdicted, and bypassable via the acknowledged route above.
  In one sentence: **GoRefer's own words stay hard; the AP's words become advisory; and the AP can never acknowledge away GoRefer's words.**
- **DA RULING 2 — the scope boundary of doc 13 §2 is CONFIRMED as drawn.** Advisory mode applies **only** to AP-authored content sent from the AP's own number/identity. These stay **HARD**, and no acknowledgment can touch them:
  1. **Platform-rendered surfaces** (`gorefer.in` pages) — the auto-injected disclosure block + market-risk warning (ADR-014); this is GoRefer's own liability surface, not the AP's.
  2. **Platform behaviours** — never auto-submit a partner's signup form; never impersonate or clone a partner (ADR-014's misrepresentation rule).
  3. **Person-level legal duties** — DPDP consent and opt-out enforcement. **An acknowledgment can never authorize messaging someone who opted out.** The duty is owed to the *person*, who is not a party to the AP's acknowledgment and whose rights the AP therefore cannot waive.
- **Reasoning:** Advisory is not a weakening — it is the honest allocation of a responsibility GoRefer cannot discharge. The regulated entity is the AP; GoRefer is the tool that informed them. The record — *"we showed the rule, the specific breach, and the fix; they chose to proceed"* — is simultaneously **the platform's protection** and **the AP's informed-consent trail**, and it exists only if the AP stays on the platform, which a hard block would discourage. The four popup parts are each load-bearing: without the citation it is not informed; without the specific breach it is not actionable; without the recommendation the platform gave no help; without a first-person deliberate act it is not consent. Ruling 1 exists because "an asset containing both a disclosure block and an AP claim" is precisely the case a future reader could resolve two different ways — naming which half is which costs one paragraph now and an argument later. Ruling 2 exists because opt-out is where waiver is most tempting and most impermissible: the consenting party would be the wrong person.
- **Consequences:**
  - ADR-014's hard gate **stands unchanged for platform-rendered surfaces and platform-generated assets**; only AP-authored content moves to advisory (annotation appended under ADR-014).
  - ADR-025's hard gates are re-scoped per its own amendment below.
  - The bypass path is a **first-class feature with an immutable log**, not an escape hatch bolted on afterwards: the log is the artifact the entire decision rests on, so it is built with the checker, never after it.
  - The rule library becomes a maintained asset with an owner and a review cadence (O-3), and a legal task exists to align the AP agreement (O-4).
  - GoRefer must never describe itself, in UI or contract, as certifying or approving AP content — it advises.

---

## ADR-039 — Platform-standard vendor stack; role-ports; portability invariants

- **Status:** Locked (2026-07-20, DA ratification of doc 13). **Model-only — not scheduled; binds the multi-AP mission when it starts.** Ratifies **D-13-5** (per-AP CRM **dropped**), **D-13-3**/**D-13-4** as narrowed, **D-13-7** (port renaming). Basis: doc 13 §3/§6 (owner's final same-day revision, 2026-07-19). Depends on `apps/integrations/base.py`, `CLAUDE.md` §6b (contract-doc CI gate).
- **Context / Problem:** An earlier capture on 2026-07-19 had each AP bringing their **own** CRM and BSP. Abhay revised this before end of day: **all APs use the platform's shared stack.** That revision needs recording, because it removes a large amount of speculative machinery (per-tenant adapter registry, per-tenant vendor credentials) — and because "we standardized" must not quietly become "we got locked in".
- **Alternatives Considered:**
  1. **Per-AP vendor choice** (each AP brings their own CRM/BSP) — **dropped by the owner**: multiplies credential custody, adapter permutations and support surface by the number of APs, for a benefit no real AP has asked for. (A Google Sheet is not a CRM in any case — same-day decision.)
  2. **Hard-wire the current vendors** into the domain — rejected: cheap today, and precisely what turns a later CRM addition or BSP swap into a rewrite.
  3. **Platform-standard stack behind role-ports** — chosen.
- **Decision:** Every external dependency is a **role filled through a port** (`apps/integrations/base.py`), and the **binding is platform-wide, not per-AP**:
  - **CRM of record: ONE shared CRM for the whole platform** (Zoho today). **The per-AP CRM option is DROPPED** (D-13-5, superseding the earlier same-day capture). Every new AP onboards into the platform CRM. A certification checklist is needed only if the *platform* ever swaps CRM — at which point `Zoho-GoRefer/Zoho-Integration-Contract.md` is that checklist's seed.
  - **WhatsApp BSP: one BSP** (WATI today), platform-wide. Per-AP numbering is settled by ADR-040 (each AP has their own number under the **platform's** WABA); the **AP-owned-WABA path remains optional** for an AP who insists on their own branding, and that AP owns getting their template set approved on that WABA, with GoRefer tracking per-number approval and gating sends on it (**D-13-3**, narrowed — the CRM half of D-13-3 is gone).
  - **D-13-4 credential custody, narrowed:** per-tenant, encrypted, never in `.env`, never checked in. **DA RULING 4 — narrowed further:** under ADR-040/G-1 **the platform owns the WABA**, so **per-AP WABA credentials arise ONLY in the optional AP-owned-WABA path**. In the standard topology there are **no per-AP vendor credentials at all** — platform CRM/BSP credentials stay exactly as today. Per-tenant credential custody is therefore a **conditional** requirement, existing only if and when an AP exercises the owned-WABA option — not a general one.
  - **Email** is a future port; per-AP formats/templates are plain config-cascade keys at the tenant tier — no new machinery.
  - **D-13-7 — port naming:** rename vendor-named ports (`ZohoAdapter`, `WatiAdapter`) to **role names** (`CrmAdapter`, `MessagingAdapter`) **at refactor time**. This is naming-only coupling today and deliberately not worth a churn commit now; it is recorded so the rename is a known task rather than a rediscovery.
- **Two moves that must stay permanently cheap** (future-proofing requirement, owner 2026-07-19 — platform-standard is today's *posture*, not a structural commitment):
  1. **Adding a new CRM later** (multi-CRM may return): **one new adapter** written against the role contract. This stays cheap **only** while vendor vocabulary stays quarantined in the adapter package (status map, webhook shape, seal) and **the domain core never learns a CRM's name** — already enforced by the `apps/integrations` boundary and the contract-doc CI gate.
  2. **Swapping the WhatsApp BSP:** template approvals attach to the **WABA at the Meta level, not to the BSP** — keep the same WABA/number, re-point it at the new provider, and the approved template set carries over; only the API surface changes. **Corollary rule: BSP-native extras (chatbots, CDP attributes, campaign tooling) must NEVER become load-bearing in GoRefer.** GoRefer's dependency stays deliberately thin — send-template + terminal delivery status + webhook, exactly the surface `Wati-GoRefer/Wati-Integration-Contract.md` describes. (Changing the **number** is the expensive move, since it re-enters template approval — so BSP portability planning always preserves the WABA.)
- **Role-level invariants — these hold regardless of which vendor fills a slot, and any replacement adapter MUST honor them:**
  1. **The CRM of record is the sole source of truth** for account/reward status; GoRefer never fabricates (ADR-013/016). An adapter may satisfy the *ingest* contract by polling instead of webhook — the contract does not change, only the transport.
  2. **Messaging success = terminal delivery status, never HTTP 200.** This is a Meta-level truth and survives any BSP.
  3. **Never auto-submit a partner's signup form** — redirect a real human browser only.
  4. **Save the lead in GoRefer first; preserve the true open date; single-winner attribution.**
  5. **Contract docs move with adapter code** (CI-enforced, `CLAUDE.md` §6b) — a new vendor adapter is written *against* the existing contract doc.
- **Reasoning:** Standardizing removes real, compounding cost (credential custody per AP, N adapter permutations, N support paths) for a flexibility nobody has requested — but standardizing *without* ports would trade that cost for lock-in, which is the more expensive mistake because it is discovered late. Ports plus the five invariants keep the exit cheap: the invariants are exactly the things that would otherwise be silently re-decided by whoever writes adapter #2, and writing them down means a replacement adapter is checked against a list rather than against someone's memory of Sprint 1. The BSP corollary names the specific trap: BSP-native features are attractive precisely because they are free and adjacent, and each one adopted quietly converts a thin dependency into a thick one.
- **Consequences:**
  - **Sprint 1 code is unchanged** — process-global adapters chosen by flag is exactly right under this decision. No per-tenant adapter registry, no per-tenant CRM credentials.
  - The contract docs (`Zoho-GoRefer/`, `Wati-GoRefer/`) are now **load-bearing artifacts**: they are the spec a future adapter is written against, which retroactively raises the value of the §6b CI gate.
  - Per-tenant encrypted credential storage is **conditional** — build it if and when an AP takes the owned-WABA path, not before.
  - The port rename (D-13-7) is a tracked refactor-time task, not a now-task.

---

## ADR-040 — Multi-AP messaging topology, opt-out scope, and metering

- **Status:** Locked (2026-07-20, DA ratification of doc 13). **Model-only — not scheduled; binds the multi-AP mission when it starts.** Ratifies **G-1** (per-AP own number under the platform WABA; supersedes "shared number"), **G-3** (dissolved), **G-4** (per-AP opt-out + platform kill-switch), the **metering half of G-6**, and **O-2** (AP lifecycle). Basis: doc 13 §7 (owner dispositions, 2026-07-19). Depends on ADR-036 (tenant = AP), ADR-039 (platform-standard BSP).
- **Context / Problem:** With one AP, one business number is obviously right. With fifty it is obviously wrong, and three separate problems arrive together: **blast radius** (a shared Meta quality rating means one AP's misbehaviour throttles everyone), **inbound ownership** (a reply to a shared number belongs to *whom?*), and **opt-out scope** (does "stop" mean stop this AP, or stop the platform?). Deciding these late means retrofitting them onto live conversations and live consent records — the two things that cannot be safely migrated.
- **Alternatives Considered:**
  1. **One shared platform number for all APs** — rejected (this was the earlier posture, now superseded): a shared Meta quality rating is a shared blast radius; inbound replies need a routing rule that cannot be reliably inferred; and the recipient experience misrepresents who they are talking to.
  2. **Each AP brings their own WABA** — rejected as the default: every AP then re-runs template approval on their own WABA, which is slow, failure-prone and duplicated N times. Kept as an **optional** path (ADR-039).
  3. **Per-AP own number, all under the platform's WABA** — chosen.
- **Decision:**
  - **G-1 — topology: each AP gets their OWN number, all under the platform's WABA.** Templates are approved **once at WABA level** and serve every number under it; **Meta's quality rating is per number**, so one AP's misbehaviour throttles **only that AP**. Costs accepted by the owner: the BSP bills per connected number (passable to the AP), and **~20 numbers per WABA** before a second WABA is needed (which brings one batch template re-approval). **This supersedes the earlier "shared business number is the standard posture"** recorded in doc 13 §3 — corrected in that doc (see its §3 supersession note). The **AP-owned-WABA path stays optional** for APs who insist on their own branding.
  - **G-3 — inbound conversation ownership: DISSOLVED**, not solved. With per-AP numbers, **replies arrive on the owning AP's number**; there is no routing rule to write and no ambiguity to adjudicate. The best fix to G-3 was to remove the condition that created it.
  - **G-4 — opt-out scope: per-AP opt-out + an explicit platform-wide kill-switch.** By **default an opt-out binds that AP's number only** — each AP is a distinct sender relationship, and a person who stops hearing from one AP has not asked to stop hearing from a different business. A **second, explicit "stop everything" escalation** opts the person out **platform-wide**, enforced at the send gate for **every** AP number. **The stop-confirmation message MUST explain the distinction** — a person who believes they opted out of everything, and did not, is precisely the failure mode this clause exists to prevent. (Per ADR-038 Ruling 2, no AP acknowledgment can override either scope.)
  - **G-6 metering half — per-AP usage counters from day one of multi-AP.** Messages, conversations and numbers are counted **per AP**, **counting only — no billing machinery, no invoicing, no rating engine.** The rationale, stated plainly: **invoicing can be done retroactively; counting cannot.** Un-counted usage is unrecoverable, so the cheap half is done immediately and the expensive half waits until it is actually needed.
  - **O-2 — AP lifecycle: `active → suspended → exited`,** with each asset's fate decided per state:
    - **The AP's number** stays in the platform WABA. **NO quick recycling to another AP** — stray replies to a recycled number would reach a *competitor*, which is both a confidentiality breach and a regulatory embarrassment.
    - **In-flight conversions** (accounts opening after exit) need a stated credit rule, decided at build time rather than during the first dispute.
    - **Referrer data** follows DPDP retention (ADR-020).
    - **Links and sending are decoupled: suspended = links still resolve, but ALL sending stops immediately** (e.g. on regulator suspension). Existing shared links continuing to work is harmless; continuing to *send* on behalf of a suspended AP is not.
- **Reasoning:** G-1 is the decision the other two fall out of — which is why it is recorded as *the topology decision* rather than as three separate fixes. Per-number quality rating is the specific Meta mechanic that makes it work: it converts a shared, uncontrollable reputational risk into a per-tenant one borne by the tenant who caused it, which is also the fair allocation. Keeping all numbers under **one platform WABA** captures the approve-once benefit that made a shared number attractive, without the shared blast radius — the two goods turned out to be separable, having been assumed to be a trade-off. On G-4, the per-AP default matches the legal and human reality (distinct sender relationships), while the explicit escalation covers the person who genuinely means "all of you"; the confirmation-message requirement exists because a silently narrower opt-out than the user intended is worse than no opt-out, since it manufactures false confidence. The metering rationale is asymmetric and worth stating: the cost of counting early is a counter; the cost of counting late is data that no longer exists. O-2's no-recycling rule rests on the same asymmetry — the saving from reusing a number is trivial next to one stray reply landing at a competitor.
- **Consequences:**
  - Doc 13 §3's "shared business number is the standard posture" is **superseded** and corrected in that doc.
  - Per-number template-approval tracking and send gating are needed **only** for the optional AP-owned-WABA path (ADR-039/D-13-3); under the standard topology, WABA-level approval covers every number.
  - Opt-out storage must be **scoped** (AP-scoped and platform-scoped are different records) from the first multi-AP migration — retrofitting scope onto a flat opt-out table means guessing what past opt-outs meant, which is not answerable.
  - Usage counters are a day-one deliverable of the multi-AP mission; billing is explicitly out of scope.
  - AP records need a lifecycle state, and the send gate must consult it (suspended ⇒ no sends, links unaffected).

---

## ADR-041 — The partner code belongs to the (AP, partner) pair; upsert key is `(tenant, mobile)`

- **Status:** Locked (2026-07-20, DA ratification of doc 13). **Model-only — not scheduled; binds the multi-AP mission when it starts.** Ratifies the doc 13 §8 **LOCKED CORRECTION**, **G-2** (upsert key) and **G-5** (off-platform referrer home). Basis: doc 13 §7/§8 (owner-accepted 2026-07-19). Depends on ADR-001 (raw `client_id` link), ADR-016 (single-winner attribution), ADR-036 (tenant = AP).
- **Context / Problem:** `ZMPHZC` has been treated throughout Sprint 1 as *Zerodha's* partner code. **It is not. It is PIFS's AP code at Zerodha.** Every AP brings their **own** code for each partner they are registered with, and their links must redirect carrying **their** code. Today's `Partner.code` works **only** because PIFS is the sole AP — it is correct by coincidence, and the coincidence ends with AP #2. Left uncorrected, **every AP's conversions would credit PIFS**: the most damaging class of failure this platform can have, because it is silent, it is financial, and it corrupts the referral record that ADR-016 declares authoritative.
- **Alternatives Considered:**
  1. **Keep the code on `Partner`** — rejected: factually wrong, and produces mass mis-attribution the moment a second AP exists.
  2. **Move the whole `ReferralProgram` (code *and* destination-URL template) under the AP** — rejected: the destination-URL template genuinely **is** partner-level (it is Zerodha's signup URL shape, identical for every Zerodha AP); duplicating it per AP would mean a partner's URL change requires N edits, and the copies would drift.
  3. **Split them: template stays partner-level, code moves to the AP–partner link** — chosen.
- **Decision:**
  - **The destination-URL template stays partner-level** (`ReferralProgram`). **The partner code moves to the AP–partner link** — the code is an attribute of the *pair* `(AP, partner)`, because that is what it factually is: this AP's registration with that partner. Redirect assembly then composes a partner-level template with the **acting tenant's** code for that partner.
  - **G-2 — the lead upsert key is `(tenant, mobile)`.** One lead per prospect **per AP**: strict NSE isolation (ADR-036) means two APs' records of the same person must not merge, and duplicate outreach is handled at the **send layer**, which already dedups by mobile. This must be the **FIRST migration** of any multi-AP mission.
  - **G-5 — off-platform referrers land in a holding tenant.** A referrer arriving from a Zoho-ingested conversion with no known AP goes to a **system "unassigned" tenant**; an **admin assigns** them to the right AP, and **the assignment is auditable**. **Hard uniqueness rule: one `client_id` → one tenant per partner.**
  - **Both the code move and the `(tenant, mobile)` key MUST land in the first multi-AP migration.** Neither is a follow-up: the day a second AP exists without them, conversions mis-credit and leads cross-merge — and both corrupt data rather than merely failing.
- **Reasoning:** This is the one item in doc 13 where the current implementation is not merely *incomplete* for multi-AP but **actively wrong** — and it is invisible today precisely because there is one AP, which is what makes it dangerous. Splitting template from code follows the ownership of each fact: the URL shape is the partner's, the code is the AP's registration with that partner, and modelling each where it actually lives means neither has to be duplicated or synchronized. `(tenant, mobile)` follows the same principle: the tenant boundary is the legal boundary (ADR-036), so a person known to two APs is legitimately two records, and merging them would breach the very isolation the tenancy cut exists to enforce. G-5 refuses the tempting shortcut of auto-assigning an unknown referrer by inference — under ADR-016 GoRefer credits **no one** rather than guess, so an explicit, auditable admin assignment is the consistent answer, and the holding tenant gives those records a real home instead of a null.
- **Consequences:**
  - `Partner.code` becomes wrong-by-design and must be migrated, not extended. Redirect assembly gains one input (the acting tenant) — mechanically small, but it touches the guardrail that keeps the partner code server-side, so the guardrail tests move with it.
  - The "holding tenant" is a real seeded tenant with an admin assignment workflow and an audit trail — small, but not free, and in scope for the first migration.
  - The uniqueness rule (one `client_id` → one tenant per partner) becomes a DB constraint, not a convention.
  - Sprint 1 is unaffected: with PIFS as the sole AP today's behaviour is correct — it simply must not be *relied upon* as the model.

---

## ADR-042 — Tenant-configurable actor hierarchy BELOW the AP (ordered levels, one parent)

- **Status:** Locked (2026-07-27, owner ratification of doc 16 Q-16-1). **Model-only — built in doc 16 Phase 4.** Basis: doc 16 §0 O-2 / §3.1; owner decisions 2026-07-27 (in-session, recorded in COORDINATION). Depends on ADR-016 (single-winner attribution, unchanged), ADR-023/036 (tenant boundary; the ADR-036 tree above the tenant is untouched — the two trees join at the tenant node).
- **Context / Problem:** Sprint 1 has no relations between actors below the tenant — referrers are a flat set, "role" is five uncoordinated string vocabularies, and authorization is a binary `is_staff` (doc 16 §2.1). "Any type of customer with no code changes" (owner, 2026-07-27) requires structures like PIFS → sub-AP → introducer → referrer, or agency → manager → agent, whose depth cannot be predicted per tenant.
- **Decision:** Each tenant defines an **ordered level schema as data** (`ActorLevelSchema`: tenant, rank, code, label). Actors form a **tree — exactly one parent, same tenant, rank-adjacent** (DB-enforced); prospects/customers are leaves outside the level schema. **Attribution is untouched:** an ancestor *sees* descendant journeys (visibility via the single subtree choke point, `TenantQuerySet`), it never *credits* from them. One canonical **ActorRole registry** (doc 16 Phase 3) replaces the five vocabularies; adding an actor type or level is a data operation. Free-form graphs and multi-parent relations are **rejected** — they make single-winner attribution ambiguous.
- **Consequences:** Migration is a relabeling (existing referrers become depth-1 actors); no visible change until a tenant defines a second level. Cascade tiers `level`/`actor` (ADR-043) activate with it. Rail E-5 (ADR-044) guards the invariants.

---

## ADR-043 — Config totality: one ScopedConfig store + a declared key registry with per-key cascade policy

- **Status:** Locked (2026-07-27, owner ratification of doc 16 Q-16-2, amended by O-3). **Built in doc 16 Phase 1** (Phase 0 lands only the D-1 compliance-reader fix). Basis: doc 16 §0 O-3 / §3.2. Generalizes ADR-022; implements ADR-037's semantics; ADR-034's Preferences screen becomes registry-generated.
- **Context / Problem:** The three cascade tiers are three physical tables with a hand-written resolver branch each; 61 behavior-governing literals sit outside config entirely; and the compliance lock protected keys **nothing read** (doc 16 D-1 — fixed in Phase 0 by routing the render paths through `resolve()` and seeding every locked key).
- **Decision:** **Every behavior is a config key.** One `ScopedConfig` table `(scope_type, scope_id, key, value)` replaces the three tables (resolver signature preserved); a **code-declared key registry** gives every key a default, type/validator, UI group (or `operator_only`), and **cascade policy**: `locked@tier` (ADR-037 hard stop), `override` (ADR-022 nearest-wins), or `aggregate` (read-model rollups climbing the actor tree — never through the resolver, so every resolved value still traces to exactly one tier). **An unregistered key does not resolve** (rail E-1). **Tenant admins self-serve their own tenant-tier defaults** through the registry-generated Preferences screen; locked keys render visible-but-locked. New behavior literals must register a key in the same PR (CLAUDE.md §6e).
- **Consequences:** The 61-site hardcode inventory (doc 16 §2.2) becomes the Phase-1 backlog, migrated in churn order, each shipping with its old value as the default (zero behavior change day one). Adding a cascade tier becomes data. `attribution_window_days` and the dead `ENABLE_ASSET_GENERATOR` flag were removed (D-5) rather than carried into the registry.

---

## ADR-044 — The architecture is machine-enforced: rails E-1…E-6 with an observe→enforce ladder

- **Status:** Locked (2026-07-27, owner ratification of doc 16 Q-16-4/Q-16-5). **Rails E-1(partial)/E-2/E-3/E-6 landed in Phase 0**; E-1(full) lands with Phase 1, E-4 with Phase 2, E-5 with Phase 4. Basis: doc 16 §0 O-4 / §5; precedent: the three guardrail tests + `scripts/check_contract_docs.py`.
- **Context / Problem:** Every boundary in this codebase that was held only by prose drifted: the port Protocols nothing imported (D-3), the tenant-scoped managers that did not exist (D-4), the compliance lock guarding unread rows (D-1). Prose does not hold architecture; CI does.
- **Decision:** Six rails, each with a CI call site: **E-1** key-registry gate (every compliance-locked key seeded + read; Phase 1 extends to all keys); **E-2** rendered compliance surfaces must track the locked resolver byte-for-byte (`tests/test_architecture_rails.py`); **E-3** vendor packages referenced only inside `apps/integrations/` — `scripts/check_architecture.py` fails on any NEW leak, the committed baseline (14 files) may only shrink; **E-4** shared port contract suite executing ADR-039's five invariants (Phase 2); **E-5** hierarchy invariants (Phase 4); **E-6** authoring rule CLAUDE.md §6e. **Observe→enforce ladder:** a rail ships observing with a baselined violation list; growth fails immediately; an emptied baseline makes the rail a hard boundary automatically. A rail with no CI call site is itself a defect (dead-gate rule).
- **Consequences:** doc 16 §6's not-building list is ratified alongside (Q-16-5): no rules DSL, no actor graphs, no per-AP vendor choice, no SaaS surface, no speculative second adapters, no persisted vendor-column renames before a real second vendor.
