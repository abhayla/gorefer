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

## ADR-024 — Technology stack: Django + Django Ninja + HTMX + Tailwind + PostgreSQL (+ django-tenants)

- **Status:** Locked (2026-07-06). Chosen after a neutral external cross-check (prompt: `../../review/Framework-Evaluation-Prompt.md`) run past **ChatGPT, Grok, Gemini, DeepSeek** plus a supplementary framework analysis. Full basis + trade-offs: **[`review/Framework-Decision-Synthesis.md`](../../review/Framework-Decision-Synthesis.md)** and the per-LLM captures `review/ChatGPT-Framework.md`, `review/Grok-Framework.md`, `review/Gemini-Framework.md`, `review/DeepSeek-Framework.md`. Encoded into the build guide `implementation/10` §1.
- **Context / Problem:** GoRefer needs a concrete stack. Constraints: a **part-time solo, Python-fluent** builder who must read/debug/extend the whole codebase alone; **mobile-first, WhatsApp-driven traffic on slow Indian networks** (light pages matter); the **simple central app + one PostgreSQL** runtime (ADR-021); an **event-sourced** model; **strict typed contracts** for Zoho/WATI payloads; the **3-tier config cascade** (ADR-022); and a **multi-tenant SaaS future** (ADR-023).
- **Alternatives Considered:** (1) **Django + Django Ninja** — batteries: admin, auth, ORM, migrations, forms, templates + mature multi-tenancy (`django-tenants`); Django Ninja adds FastAPI-style Pydantic-typed async APIs. (2) **FastAPI** (+ SQLAlchemy/Alembic + Pydantic + Jinja/HTMX + SQLAdmin) — lean, async-first, native Pydantic; you assemble ORM/migrations/auth/admin yourself. (3) Node/TS + React/Next — one language front+back but a second runtime and not the founder's language. (4) Next.js full-stack. (5) Go. (6) Rails/Laravel. Options 3–6 rejected (new language and/or wrong shape for a solo Python founder / server-rendered app).
- **Decision:** Build on **Django** with **Django Ninja** for the JSON/API layer, **server-rendered Django templates + HTMX + Tailwind CSS** for the UI (NO React/SPA in Sprint 1), **PostgreSQL** (ADR-021), and **`django-tenants`** as the multi-tenancy path for the ADR-023 boundary. Background work starts with `transaction.on_commit()` + a light DB-backed queue (django-q / django-rq); add Celery/Redis only when scheduled workflows demand it. The **customized Django admin** jump-starts the M7 internal dashboard; **admin-only auth is env-bootstrapped** (ADR / REQ-016). Typed contracts use **Pydantic (via Django Ninja) schemas** for Zoho/WATI payloads.
- **Reasoning:** The external cross-check was **unanimous** on the parts that matter structurally — Python; **server-rendered templates + HTMX + Tailwind, not React/SPA** (light on cheap Android over slow networks); PostgreSQL; an **append-only event table** (no Kafka/CQRS); a **non-blocking redirect** (validate + 302, background-write the click, idempotent via unique constraints); the adapter pattern; **`tenant_id` from day one**; and **API-first** so a richer customer SPA can come later on the same API. The only split was FastAPI vs Django, which tied **2–2** (ChatGPT/Gemini → FastAPI; Grok/DeepSeek → Django). Two things break the tie toward Django: (a) for the **already-locked server-rendered + HTMX** route, Django is the more natural home — its templating, forms, ORM, and admin are purpose-built for server-driven rendering, whereas FastAPI + HTMX means hand-assembling those; and (b) the founder's own priorities — **part-time solo, admin/CRUD-heavy app, multi-tenant SaaS ambition** — favour batteries (admin/auth/migrations + `django-tenants`). **Django Ninja preserves FastAPI's one real edge** (Pydantic-typed async APIs) inside Django, and async is moot at ~4 req/s (sync + `transaction.on_commit()` is ample). FastAPI is the recorded, equally-safe close second.
- **Consequences:**
  - The repo is a **Django project** (apps such as `referrals`, `events`, `config`, `tenants`, `integrations`, plus `templates/` + `static/` for Tailwind and Django Ninja API routers). Uses the **Django ORM + Django migrations** (NOT SQLAlchemy/Alembic).
  - The `/r/{client_id}` **redirect is a sync Django view**: format-validate → 302, with the click/journey write handed to `transaction.on_commit()` (or the light queue) so it never blocks; idempotency via unique constraints (ADR-021, review #11).
  - The **admin dashboard** leverages a customized Django admin + HTMX (per ADR-022/ADR-014, the compliance block is injected via middleware + a template tag and is non-removable).
  - **Multi-tenancy:** `django-tenants` (schema-per-tenant) is the default path for ADR-023; a `tenant_id` discriminator is the lighter single-schema fallback — decide at multi-tenant-enable time; keep tenant vs shared apps separated early, start with one bootstrap tenant.
  - **Revisit trigger:** if GoRefer ever pivots to an API-first / ML-serving core with a React/Next SPA as the *primary* UI, re-open FastAPI (the close second).
- **Cross-references:** [ADR-021 central runtime](#adr-021--runtime-model-simple-central-one-app--one-db) · [ADR-022 config cascade](#adr-022--configuration-3-tier-cascade-central---globaladmin---user) · [ADR-023 multi-tenant boundary](#adr-023--multi-tenant-boundary-designed-now-feature-sprint-2) · build guide `implementation/10` §1 · decision basis `review/Framework-Decision-Synthesis.md`.
