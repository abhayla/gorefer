# GoRefer — 12. Resolved Gaps & Edge-Case Decisions

**Document 12 of the GoRefer Architecture Repository.**
**Owner:** Abhay Kumar Maurya / PIFS (drafted with AI assistance). **Sprint:** 1 (Zerodha). **Status:** Decisions locked. **Last updated:** 2026-07-06.

> **What this is.** The authoritative record of the gap / edge-case resolutions raised against the GoRefer referral model and now **locked** — the **original 16 gaps** plus the **Round-2 external-review decisions** (Gemini / Grok / Claude walk, approved by Abhay 2026-07-06). Each entry is presented as **Gap # · Title · Decision (what GoRefer does) · Rationale / notes**, grouped by the persona the gap primarily affects — **Partner**, **Referrer**, **Friend**, and **Cross-cutting** — with the Round-2 decisions gathered in their own **Round 2 — External-review resolved decisions** section. These are decisions, not options; where a behaviour is deferred it is called out explicitly as a Sprint-2+ item.
>
> **Read alongside:**
> [`01-GoRefer-Foundation-Specification.md`](./01-GoRefer-Foundation-Specification.md) (REQ/BR/NFR/AC),
> [`04-System-Architecture.md`](./04-System-Architecture.md) (orchestrator model, sequence flows),
> [`05-Database-Design.md`](./05-Database-Design.md) (referral identity, journeys, events, dates),
> [`06-API-Specification.md`](./06-API-Specification.md) (`GET /r/{client_id}`, `GET /open`, `POST /api/leads`, `POST /api/share`),
> [`07-UI-UX-Specification.md`](./07-UI-UX-Specification.md) (landing page, disclosure rendering),
> [`08-Zoho-WATI-Integration.md`](./08-Zoho-WATI-Integration.md) (Zoho sync, WATI delivery status),
> [`11-Referral-Workflow-and-Edge-Cases.md`](./11-Referral-Workflow-and-Edge-Cases.md) (the end-to-end workflow these decisions refine).
>
> **New ADRs encoding these decisions:** ADR-015 (partner-direct link), ADR-016 (Zoho single-source / single-winner), ADR-017 (true opening date), ADR-018 (best-effort visitor identity), ADR-019 (bot filtering), ADR-020 (DPDP baseline), and — from the Round-2 walk — ADR-021 (simple central runtime model), ADR-022 (3-tier config cascade + compliance lock), ADR-023 (multi-tenant boundary designed now / SaaS later) — see [`02-Architecture-Decisions-ADR.md`](./02-Architecture-Decisions-ADR.md). The Round-2 walk also opened backlog items **DF-1** (Zoho API pull), **DF-2** (wax-seal webhook auth), **DF-3** (edge/distributed runtime), **DF-4** (full bulk backfill) in `Deferred-Features-Backlog.md`; full walk log in `gorefer-ops/review/Review-Matrix-v1.md`.
>
> **Anchors:** Partner code `ZMPHZC` (injected server-side). NSE AP reg. no. `AP2516003693`. WATI business number `+91 70806 42020`. Ashok's personal number `73888 82020` (NOT used for inbound capture).

---

## How to read a decision

Each gap below carries four fields:

- **Gap #** — the stable identifier for this edge case.
- **Title** — the one-line problem.
- **Decision (what GoRefer does)** — the locked behaviour. This is what gets built.
- **Rationale / notes** — why, plus compliance and cross-reference notes.

The guiding principles behind every decision: **Zoho is downstream truth**, **GoRefer never fabricates or overrides**, **compliance is a hard gate**, and **PIFS never funds a top-up reward**.

---

# Partner

Gaps that concern how the **partner (PIFS/Zerodha)** is credited and how partner-originated traffic is modelled.

## Gap 1 — Partner-direct link with no referrer

- **Title:** A prospect who has no referrer but should still credit PIFS (partner brokerage).
- **Decision (what GoRefer does):** Introduce a **second link type** — `gorefer.in/open` — which redirects to `signup.zerodha.com/?c=ZMPHZC` **with no `r=` parameter**. The resulting journey is stored with **`referrer = NONE`** and **`source = partner-direct`**. This is **not** modelled as a fake/synthetic referrer. The Referral Explorer can **filter referral journeys vs partner-direct journeys** as distinct populations.
- **Rationale / notes:** PIFS still earns partner brokerage on accounts that arrive without any referrer, so those journeys must be first-class and countable — but crediting a phantom referrer would corrupt referrer analytics and leaderboards. A dedicated `source=partner-direct` keeps the two populations clean. Encoded in **ADR-015**. Complements the referral path `gorefer.in/r/{client_id}` (ADR-001/ADR-005).

---

# Referrer

Gaps that concern **who gets credited**, how off-platform referrers appear, and what the referrer sees.

## Gap 3 — Same prospect, two referrers → single winner

- **Title:** A prospect clicks two different referrers' links (or is referred by two people); who is credited?
- **Decision (what GoRefer does):** **Exactly one winner.** **Zoho (synced from Zerodha) is authoritative** for who is credited. GoRefer credits **exactly one journey** — the one matching the **Zerodha-credited referrer**, matched by **mobile number + credited referrer id**. There is **NO last-redirect (last-click) fallback**. If Zoho shows **no referrer**, GoRefer credits **no one**. GoRefer **never assumes or overrides** Zoho's credit. A single unique mobile flips **at most one** journey to `converted`.
- **Rationale / notes:** Reward money flows through Zerodha to the referrer's own account (see Gap 7); GoRefer must mirror whoever Zerodha actually credited, not invent its own attribution rule. A last-click heuristic would frequently disagree with Zerodha and mis-state who "won." Deterministic, mobile-keyed, single-winner matching keeps GoRefer's story identical to the money. Encoded in **ADR-016**. See also Gap 11 (mobile-authoritative identity) and Gap 2 (join key).

## Gap 3b — Off-platform referrals (conversions with zero GoRefer clicks)

- **Title:** Accounts opened with a referrer but where the friend never clicked a GoRefer link.
- **Decision (what GoRefer does):** GoRefer referral records = **observed clicks** ∪ **Zoho-imported conversions** (accounts opened with a referrer but with no GoRefer click). A **referrer identity is created lazily** on the **first click OR the first Zoho-imported conversion** — whichever comes first. A referrer's numbers therefore equal **everything Zoho credits to them** plus **click-level detail for the link-sourced subset only**. **A conversion can exist with zero GoRefer clicks.**
- **Rationale / notes:** Referrers are open-ended (ADR-001) and many real referrals happen off-platform (word of mouth, a phone call, Ashok keying a lead). Refusing to count those would under-report referrers and make the dashboard untrustworthy. Lazy creation on first-click-or-first-conversion (extends ADR-008) lets a referrer exist purely because Zoho credited them. Encoded in **ADR-016**.

## Gap 5 — Referrer feedback / notifications

- **Title:** Does the referrer get told when their referral converts?
- **Decision (what GoRefer does):** **Sprint 1 = NONE.** The **"My Referrals"** referrer surface is **off** in Sprint 1 (architected but disabled per ADR-009/ADR-011). **Sprint 2 (deferred)** = a **conversion WhatsApp nudge** to reachable referrers, dependent on the WATI delivery fix (Gap 12) landing first.
- **Rationale / notes:** Sprint 1 is admin-only; exposing referrer notifications now would mean building the customer surface and depending on an as-yet-unreliable WATI channel. Deferring keeps Sprint 1 scope tight without a later redesign. See Gap 12 (WATI prerequisite) and REQ-F01 (stale-lead nudge, same channel).

## Gap 6 — Mistyped / invalid referrer id

- **Title:** A shared link carries a wrong or malformed `client_id`.
- **Decision (what GoRefer does):** **Accept-and-redirect** with **format validation only** — **no ownership verification** (there is no Zerodha API to check against). Mitigations: (a) GoRefer **generates customers' links from Abhay's own data via WATI**, so the shared links are **correct by construction**; (b) the landing page **echoes the URL** and shows a small **"Referral ID: X"** line for self-serve visual confirmation. **No separate confirm page.**
- **Rationale / notes:** Ownership can't be verified without an API that doesn't exist (ADR-013), and a hard block would reject legitimate ids GoRefer simply can't validate. A wrong id only fails to credit that one referrer; the partner code `ZMPHZC` is injected server-side and always credits PIFS regardless (Gap 7). Format-validation + echo is the pragmatic, low-friction guard. Builds on ADR-001.

## Gap 7 — Referrer reward path

- **Title:** How and by whom is the referrer's reward paid?
- **Decision (what GoRefer does):** The referrer reward path is **entirely Zerodha's**. The `r={client_id}` parameter routes the reward to the **referrer's own Zerodha account**; **GoRefer does nothing** in this flow. There are **two separate money flows**: (1) **referrer reward** via `r=`, handled by Zerodha; (2) **partner brokerage** via `c=ZMPHZC`, credited to PIFS. **No PIFS top-up.**
- **Rationale / notes:** Keeping the two flows separate and both external means GoRefer never touches reward money and never creates a payout liability. A PIFS-funded top-up would create both a financial liability and a compliance exposure. See Gap 4 (reward truth) and Gap 14 (reward wording). Encoded alongside ADR-016.

---

# Friend

Gaps that concern the **referred prospect (the "friend")** — their identity, their status, and why they did or didn't convert.

## Gap 2 — Attribution reconciliation (join key)

- **Title:** How is a GoRefer click reconciled to a Zoho lead / Zerodha account?
- **Decision (what GoRefer does):** The **join key = mobile number + a GoRefer journey-reference** stamped on the Zoho lead. This works for **both** the **form path** and the **WhatsApp path**. Friends who go **straight to Zerodha without giving a mobile** get **referrer-level-only attribution** (derived from the Partner Console), **not click-level** attribution.
- **Rationale / notes:** Mobile is the one identifier shared across GoRefer, Zoho, and Zerodha; stamping a journey-reference on the lead makes the join deterministic rather than fuzzy. Where no mobile is captured, GoRefer honestly downgrades to referrer-level attribution instead of guessing a click. Underpins Gap 3 (single-winner) and Gap 11 (identity). See ADR-016.

## Gap 8 — Friend already a Zerodha client / unconverted reason

- **Title:** Why didn't a lead convert — e.g. the friend already has a Zerodha account?
- **Decision (what GoRefer does):** GoRefer **cannot detect** this itself. It uses a **Zoho lead disposition / reason** (set by Ashok) that GoRefer **surfaces on the journey** — e.g. *"existing Zerodha client / not interested / wrong number."* This applies **only to leads that reached Zoho**; **anonymous clicks stay reason-less**.
- **Rationale / notes:** Without a Zerodha API GoRefer has no way to know a prospect is already a client (ADR-013); the human who worked the lead (Ashok) does. Surfacing his Zoho disposition turns "unconverted" from a black box into an explained outcome, while honestly leaving anonymous clicks unexplained. See Gap 9 (stale leads) and Gap 4b (dates).

---

# Cross-cutting

Gaps that span personas — reward truth, dates, timers, identity, delivery, sharing, compliance, privacy, and bot traffic.

## Gap 4 — Reward truth (GoRefer never computes rewards)

- **Title:** Who is the source of truth for reward amounts?
- **Decision (what GoRefer does):** GoRefer **NEVER computes or stores reward amounts.** The **Zerodha Console is the sole source** of reward truth. GoRefer shows **conversion** (from Zoho) **only**. **Compliance:** there is **NO PIFS-funded top-up reward.**
- **Rationale / notes:** Any reward number GoRefer computed could diverge from Zerodha's actual payout and would be an unverifiable, fabricated figure (violating the never-fabricate principle). Showing conversion-only keeps GoRefer truthful and keeps PIFS clear of any payout liability. See Gap 7 and Gap 14. Related to ADR-013/ADR-016.

## Gap 4b — Date capture (true account-opening date)

- **Title:** Which date drives conversion analytics?
- **Decision (what GoRefer does):** Store the **TRUE account-opening date from Zoho** as a first-class field, **distinct from the sync/import date**. Also store **click date(s)**, **lead date**, and **sync date**. **All conversion analytics and timelines run off the true opening date**, never the import date — so historical / off-platform imports land in their **real period** and produce **no fake day-1 spike**.
- **Rationale / notes:** Bulk-importing off-platform conversions (Gap 3b) on the day GoRefer goes live would otherwise stack every historical account on one date and distort every trend line. Anchoring analytics to the true opening date keeps history honest. Encoded in **ADR-017**. See `05-Database-Design.md` (date fields).

## Gap 9 — Stale lead handling

- **Title:** A lead sits unworked / unconverted for a long time.
- **Decision (what GoRefer does):** **Sprint 1:** **Zoho owns follow-up**; GoRefer provides a **read-only aging flag** — days since lead, flagged once **past the 60-day window** with **no conversion**. The flag is **GoRefer-derived**, **not** a Zoho override. **Future:** GoRefer runs an **active WATI stale-lead nudge** (REQ-F01, already in the docs).
- **Rationale / notes:** In Sprint 1, follow-up is a human/Zoho responsibility; GoRefer's job is to make staleness *visible*, not to act on it or mutate Zoho. Deriving the flag (rather than writing back) preserves Zoho as source of truth. See Gap 10 (60-day window) and Gap 5 (deferred nudges).

## Gap 10 — The 60-day window

- **Title:** How does GoRefer treat the reward-eligibility window?
- **Decision (what GoRefer does):** GoRefer **follows Zoho** for conversion and referrer and **never claims a reward was paid** (Console is the truth). It may show an **optional derived hint**: *"opened >60 days after first click — reward may not apply."*
- **Rationale / notes:** GoRefer can measure the time between first click and opening, but it cannot know Zerodha's actual reward decision, so the window is surfaced as a **hint**, not a verdict. This keeps a useful signal without asserting a payout GoRefer can't verify. See Gap 4 and Gap 9.

## Gap 11 — Visitor identity (best-effort, mobile-authoritative on submit)

- **Title:** How does GoRefer identify a returning visitor and count uniques?
- **Decision (what GoRefer does):** Set a **first-party cookie `visitor_id` on the first click**. **Same cookie = same journey**; **new/absent cookie = new journey**. IP / device / user-agent are **secondary** signals only. **Unique-vs-total counts are BEST-EFFORT / approximate and labelled as such.** On **form submit**, GoRefer **promotes to a mobile-keyed identity** and **merges cookie-journeys that share that mobile** (lead-side only). **Conversions are keyed by the opener's Zerodha account ID and the referrer by Zerodha client id — NOT by mobile** (amended by R10/R11; Zoho conversion data carries no mobile).
- **Rationale / notes:** Cookies are the most reliable client-side signal but are cleared/blocked often, so unique counts are honestly labelled approximate rather than sold as exact. Mobile is authoritative for the person on the **lead side** the moment it appears; **conversions**, however, are keyed by the opener's Zerodha account ID and the referrer by Zerodha client id (Zoho conversion data has no mobile) — see R10/R11. Encoded in **ADR-018**. Feeds Gap 2 and Gap 3.

## Gap 12 — WATI ~33% delivery failure

- **Title:** Roughly a third of WATI WhatsApp messages fail to deliver.
- **Decision (what GoRefer does):** This is a **SEPARATE prerequisite workstream** (the existing **wati-message-failure-fix**: dedup + opt-in-aware audience + Marketing/Utility template classification). It is **NOT a GoRefer feature.** GoRefer **consumes WATI delivery status** (`delivered` / `read` / `clicked`) so the **funnel starts at "delivered,"** making the delivery leak **visible** in the analytics.
- **Rationale / notes:** Fixing WhatsApp deliverability is a WATI/Meta configuration problem, not something GoRefer's referral engine should own; conflating them would bloat scope. But GoRefer *can* consume delivery status so the ~33% leak is measured rather than hidden. Gates the deferred nudges in Gap 5 and REQ-F01. See `08-Zoho-WATI-Integration.md`.

## Gap 13 — Share-on-WhatsApp destination number

- **Title:** Which WhatsApp number does the "Share on WhatsApp" button point to?
- **Decision (what GoRefer does):** It points to the **WATI business number `+91 70806 42020`**, **NOT** Ashok's personal number `73888 82020`. Inbound messages are **captured**, the **referral id is parsed**, and a **Zoho lead is created with attribution**; the **prospect's WhatsApp number becomes the captured mobile**; the exchange **opens the WhatsApp 24-hour service window**.
- **Rationale / notes:** Routing inbound to the WATI business number is what makes capture, attribution, and the 24-hour service window possible — a personal number gives none of that and can't be automated compliantly. The parsed referral id ties the inbound chat back to the right referrer. Feeds Gap 2 (join key) and Gap 11 (mobile identity).

## Gap 14 — Compliance rendering (per-partner, auto-injected)

- **Title:** How are legal disclosures and reward wording kept correct and un-omittable?
- **Decision (what GoRefer does):** Centralise the **AP disclosure block + market-risk warning + reward wording ("300 points + 10% brokerage")** as **per-partner config**, **auto-injected into every rendered page** and **baked into every generated asset** so they **cannot be omitted**. The **"10%" wording lives in ONE editable field.** A **manual `zerodha-ap-compliance-skill` gate** runs **before publish**. GoRefer **never clones Zerodha's page.**
- **Rationale / notes:** Compliance failure is existential for an AP relationship, so the disclosures are made a structural default rather than a step someone can forget. The single editable "10%" field means a regulatory reversal is a one-line change, not a site-wide scramble (the claim is live-but-revocable, ADR-014). Non-cloned, PIFS-branded rendering removes misrepresentation risk under NSE/COMP/55482. Extends **ADR-014**.

## Gap 15 — PII / DPDP baseline

- **Title:** How is personal data of prospects handled under DPDP?
- **Decision (what GoRefer does):** **Consent + notice + Privacy Policy link on the form**; a **cookie/privacy notice** for tracking; **purpose limitation** (data used for **referral / account-opening only**); **retention** = **anonymize / purge UNCONVERTED prospect PII after 12 months**; **store the raw IP + city as PII in a separate erasable record — no hashing** (superseded the earlier hash/drop; see **R17**), **PII kept OUT of the immutable event log** (R16); **manual erasure-on-request** in Sprint 1.
- **Rationale / notes:** GoRefer collects real prospect PII (name, mobile, email), so a DPDP-aligned baseline is mandatory, not optional. Purpose limitation and 12-month purge of unconverted PII minimise both risk and stored liability; the raw IP + city are kept as erasable PII (no hashing — hashing IPv4 was false privacy), access-controlled and purged/erasable (see R17). Manual erasure is acceptable at Sprint-1 volume. Encoded in **ADR-020**.

## Gap 16 — Bot / preview phantom clicks

- **Title:** Link-preview bots and crawlers inflate click counts.
- **Decision (what GoRefer does):** Maintain a **UA bot-list** (WhatsApp, `facebookexternalhit`, Telegrambot, Slackbot, Twitterbot, LinkedInBot, Googlebot, prefetchers). Bot hits are **logged but EXCLUDED** from click / unique / journey counts. A **JS-confirmation beacon** marks a **"confirmed human click"** (bots don't run JS). A **bot preview never creates a journey and never counts as a redirect.**
- **Rationale / notes:** WhatsApp/Facebook/Telegram fetch a URL to render a preview the instant a link is shared, so without filtering every shared link would show phantom clicks and fake uniques. Logging-but-excluding preserves auditability while keeping counts honest; the JS beacon is a reliable human signal because preview bots don't execute JavaScript. Encoded in **ADR-019**. Feeds the best-effort counts in Gap 11.

---

## Decision index

| Gap # | Persona | Title | Encoding ADR |
|------:|---------|-------|--------------|
| 1  | Partner       | Partner-direct link with no referrer            | ADR-015 |
| 2  | Friend        | Attribution reconciliation (join key)           | ADR-016 |
| 3  | Referrer      | Same prospect, two referrers → single winner    | ADR-016 |
| 3b | Referrer      | Off-platform referrals (zero-click conversions) | ADR-016 |
| 4  | Cross-cutting | Reward truth (GoRefer never computes rewards)   | ADR-013 / ADR-016 |
| 4b | Cross-cutting | Date capture (true account-opening date)        | ADR-017 |
| 5  | Referrer      | Referrer feedback / notifications               | — (Sprint 2) |
| 6  | Referrer      | Mistyped / invalid referrer id                  | ADR-001 |
| 7  | Referrer      | Referrer reward path                            | ADR-016 |
| 8  | Friend        | Friend already a client / unconverted reason    | ADR-013 |
| 9  | Cross-cutting | Stale lead handling                             | REQ-F01 |
| 10 | Cross-cutting | The 60-day window                               | ADR-016 |
| 11 | Cross-cutting | Visitor identity (best-effort, mobile-auth)     | ADR-018 |
| 12 | Cross-cutting | WATI ~33% delivery failure                      | — (prerequisite) |
| 13 | Cross-cutting | Share-on-WhatsApp destination number            | — |
| 14 | Cross-cutting | Compliance rendering (per-partner)              | ADR-014 |
| 15 | Cross-cutting | PII / DPDP baseline                             | ADR-020 |
| 16 | Cross-cutting | Bot / preview phantom clicks                    | ADR-019 |

### Round-2 external-review decisions

| Ref | Area | Title | Encoding / backlog |
|----:|------|-------|--------------------|
| R1  | Security/Privacy | Beacon-gated referrer name (short link kept)          | (extends ADR-001/ADR-019) |
| R2  | Security         | Zoho webhook basic-auth now; wax-seal + Zoho-pull deferred | DF-2 / DF-1 |
| R3  | Security         | Nonce-bound click-confirm beacon                       | (extends ADR-019) |
| R4  | Security         | Preview mode behind admin auth                         | — |
| R5  | Architecture     | Simple central runtime model (one app + one DB)        | ADR-021 (edge → DF-3) |
| R6  | Architecture/DB  | Rollups recompute; no provisional/final; removal-with-audit | (mirror Zoho, ADR-017) |
| R7  | Architecture/Ops | Zoho status-sync worker (M6)                           | — |
| R8  | Architecture/DB  | Idempotency guard (M6)                                 | — |
| R9  | Ops/DB           | Lazy per-referrer Zoho backfill; bulk deferred         | DF-4 |
| R10 | API/Attribution  | Referrer matched by Zerodha client id (amends Gap 3/2) | (ADR-001/ADR-016) |
| R11 | Database         | Off-platform conversion uniqueness (opener Zerodha id) | (ADR-016) |
| R12 | Architecture/API | Explicit Zoho-status→stage map; Zoho authority; reward-if-signalled | (extends Gap 4/10) |
| R13 | API              | Leads dedup records 2nd-referrer attempt (amends Gap 3)| — |
| R14 | Compliance       | Compliance gate genuinely enforced                     | (extends ADR-014) |
| R16 | Privacy/DB       | PII out of immutable event log                         | (extends ADR-020) |
| R17 | Privacy          | Store raw IP + city as PII, no hashing (amends ADR-020)| (reverses ADR-020) |
| R18 | Database         | Source label on every status change                    | — |
| R19 | Ops              | Sync-freshness indicator                               | — |
| A1  | Config           | 3-tier config cascade + compliance lock                | ADR-022 |
| A2  | Architecture     | Multi-tenant boundary now / SaaS later                 | ADR-023 |

*Round-2 deferrals (not built in Sprint 1): #21, #22 (conflicts with Gap 5), #23, #25, #26 (cash incentive rejected), #27, #28, #29, #30 (→ A2 SaaS).*

---

# Round 2 — External-review resolved decisions (2026-07-06)

A second review walk (Gemini = schema/data-model, Grok = product/growth + sync design, Claude = engineering/security) surfaced ~38 distinct suggestions; each was walked item-by-item with Abhay and **approved, deferred, or parked as a locked-decision conflict**. The decisions below are locked on the **same footing as the 16 gaps above** and refine or extend them. Where a Round-2 decision **amends** an earlier gap, that is called out. Full walk log and dispositions: `gorefer-ops/review/Review-Matrix-v1.md` (Final Approval Log). Numbering (R#) follows the review matrix rows for traceability.

## R1 — Unauthenticated referrer-name enumeration (beacon-gated name)

- **Title:** `GET /api/landing/{client_id}` returned a real first name, letting guessable Zerodha ids be harvested into an id→name map.
- **Decision (what GoRefer does):** **Keep the short link and personalization**, but the landing page returns **generic content (no name) on initial load**; the referrer's name is revealed **only after the JS human-confirmation beacon completes** and **only to a request carrying a valid, fresh, server-issued nonce**, with **rate-limiting + bot filtering**. Enumeration is made **economically impractical, not cryptographically impossible**; residual first-name-only exposure is consciously accepted. **Not** the signed-URL-param option — no link bloat.
- **Rationale / notes:** Preserves the raw-`client_id` short link (ADR-001) and the personalization value while removing cheap bulk harvesting. Reuses the nonce mechanism shared with R3. See also Gap 16 (bot filtering) and Gap 11 (beacon).

## R2 — Zoho account-status webhook authentication (basic now, wax-seal deferred)

- **Title:** The Zoho `account-status` webhook used a static key with no replay protection.
- **Decision (what GoRefer does):** **Keep the basic webhook for now, without the wax-seal.** Interim minimum when it goes live at **M6**: **static key + Zoho-IP allowlist**. Full **wax-seal (HMAC + timestamp + nonce)** and the **Zoho-API pull alternative** are moved to the backlog as **DF-2** and **DF-1**.
- **Rationale / notes:** The endpoint is only live from M6; Sprint 1 M1–M4 runs in demo mode with `ENABLE_ZOHO_WRITE` off, so there is no live exposure yet. Risk accepted: the endpoint stays forgeable if the key leaks until DF-2 lands.

## R3 — Forgeable click-confirm beacon (nonce-bound)

- **Title:** `POST /api/click/confirm` trusted a client-supplied `visitor_id` + `client_id`.
- **Decision (what GoRefer does):** **Bind the human-confirmation beacon to a server-issued one-time nonce** (the same nonce mechanism approved in R1). Forged beacons without a valid, unused nonce are **rejected**.
- **Rationale / notes:** Turns the "confirmed human click" (Gap 16, ADR-019) into a signal that cannot be trivially replayed or fabricated by a caller.

## R4 — Preview mode behind admin auth

- **Title:** `preview=true` was gated only by an `Authorization` header being *present*, not valid.
- **Decision (what GoRefer does):** **Preview mode requires a valid logged-in GoRefer admin session** (Sprint-1 admin-only login), not merely a present header. Any request lacking a valid admin session is **rejected**.

## R5 — Runtime model: simple central (one app + one DB) — ADR-021

- **Title:** Edge-scalability language (doc 04 §8) contradicted synchronous ordering (doc 06 §4.1); the runtime model was undecided.
- **Decision (what GoRefer does):** **Lock a simple central model — one app + one DB (a single logical brain)** — encoded as **ADR-021**, to be written before any code. Reliability comes from a **managed DB + backups + standby + health check**, not edge/distributed. Edge/distributed is deferred to backlog **DF-3** (revisit only past ~1M clicks/month).
- **Rationale / notes:** At ~250–1,000 clicks/day and ~6 event-rows/journey (~0.5–3M rows/yr, ~4 inserts/sec peak) the load is ~0.1% of one Postgres instance and holds even at 100×. Simplicity beats premature distribution.

## R6 — Rollups recompute on change; no provisional/final (mirror Zoho, removal-with-audit)

- **Title:** Late beacons and backdated imports mutate history, so day-rollups cannot be forward-folded.
- **Decision (what GoRefer does):** On any change, **mark the affected day(s) dirty and recompute from raw events** — no forward-only folding. GoRefer **does NOT use a provisional/final model**: it **mirrors Zoho's current mappings** — whatever Zoho maps is already final. The ~5th–6th-of-next-month batch is a **reconciliation/cleanup** that fills missing mappings and fixes gaps, **not** a provisional→final promotion. **Removal / un-mapping must propagate** (Zerodha → Zoho → GoRefer) via a **reversal/tombstone event**: the effective view drops it and rollups recompute, while the audit trail is retained. Clicks stay real-time, every click.
- **Rationale / notes:** Because add/fix/remove can hit **past** periods (true open date, ADR-017), rollups must recompute rather than fold. Removal-with-audit keeps the story honest without deleting history. See memory: gorefer-conversion-data-finality; pairs with R18 (source labels).

## R7 — Zoho status-sync worker (M6)

- **Title:** A resilient mechanism to ingest Zoho status without loss.
- **Decision (what GoRefer does):** Build a **Zoho status-sync worker in M6** with a **watermark (resume point)**, a **dead-letter / problem-tray** (retry failed updates without loss), and **off-platform auto-create** (a conversion with zero clicks, ADR-016). **Referrer-notification side-effects are deferred to Sprint 2** (depend on the WATI fix, Gap 12). The polling fallback is the deferred Zoho-API pull (DF-1); the worker processes the webhook reliably for now.

## R8 — Idempotency guard (M6)

- **Title:** Duplicate or retried Zoho deliveries could double-apply.
- **Decision (what GoRefer does):** Add an **idempotency guard in M6**: dedupe each Zoho update by a **unique id** (Zoho `event_id`, or a composite `account + referrer + date` fallback) tracked in a **`zoho_sync_idempotency` table**; **check-before-apply and guard side-effects** so retries/duplicate deliveries process **exactly once**. Distinct from the deferred wax-seal replay protection (R2 = attacker; this = normal duplicate deliveries). Pairs with R7 to give exactly-once.

## R9 — Historical backfill: lazy per-referrer fetch (bulk deferred, DF-4)

- **Title:** A fixed 24-month bulk backfill is insufficient (mappings exist since 2016).
- **Decision (what GoRefer does):** **Replace bulk with a lazy on-demand fetch**: when a referrer/client **first appears** in GoRefer (first click OR first conversion), pull **that referrer's full Zoho history** then, dated to **true open dates** (fits lazy creation, ADR-016/008). Global all-time totals fill in **as referrers become active** — not complete at launch (accepted). A full bulk backfill is kept as an **optional deferred one-off = DF-4**, only if complete all-time global dashboards are wanted at launch.

## R10 — Account-status payload: referrer matched by Zerodha client id (amends Gap 3 / Gap 2)

- **Title:** The account-status payload was ambiguous about which id credits the referrer.
- **Decision (what GoRefer does):** Lock precise, distinct field semantics in docs 06/08: the **opener = name + opener Zerodha id**; the **referrer is matched/credited by Zerodha client id** (the raw `client_id` in the referral link, ADR-001) — **NOT by mobile** (conversion data carries no mobile). The opener→click-journey link **prefers a GoRefer journey-reference stamped on the Zoho lead** and echoed back on the account update (confirm feasibility at M6); else best-effort by name; else the conversion is recorded **under the referrer only** (off-platform zero-click OK, ADR-016).
- **Rationale / notes:** **Amends Gap 3 and Gap 2**, which described mobile-keyed matching. On the **conversion side**, matching is by **Zerodha id** because conversion data has no mobile. (Lead-side mobile keying, e.g. R13, still applies where GoRefer's own form captures a mobile.) See memory: gorefer-conversion-data-finality.

## R11 — Off-platform conversion uniqueness (opener Zerodha account id)

- **Title:** Off-platform Zoho imports had no uniqueness guard, risking phantom duplicate journeys.
- **Decision (what GoRefer does):** The **unique upsert key for a conversion record = the opener's Zerodha account id** (one per account, always present in the data); **fallback `zoho_lead_id`**. **Not** mobile (conversion data has none, per R10). **Upsert-on-key** (update if exists, insert if new) so one account can never become two journeys. Protects the lazy per-referrer fetch (R9) against overlapping loads; pairs with R8.

## R12 — Explicit Zoho-status→stage map; Zoho authority past Redirected; reward only if signalled

- **Title:** No published mapping from Zoho status to GoRefer stage; authority past "Redirected" unclear; a "Rewarded" stage was unreachable.
- **Decision (what GoRefer does):** (a) **Publish an explicit Zoho-status → GoRefer-stage map** in docs 06/08; **past "Redirected," Zoho is the SOLE authority** — GoRefer mirrors and **never advances a stage on its own**. (b) The **"Rewarded" stage is reachable ONLY if Zoho supplies a reward signal to mirror**; the **default stops at `account_opened`**, and reward amounts live only in the Zerodha Console (GoRefer never computes rewards).
- **Rationale / notes:** Enforces never-fabricate; extends Gap 4 (reward truth) and Gap 10 (60-day window) with a concrete state map.

## R13 — Leads dedup records a second-referrer attempt (amends Gap 3)

- **Title:** The 24-hour lead dedup on `(mobile, client_id)` silently swallowed a second referrer of the same prospect.
- **Decision (what GoRefer does):** **Keep the 24-hour lead dedup** (no duplicate active leads), but **record a "referrer-B attempt" event** so a second referrer is **logged, not silently swallowed**. Final credit still follows Zoho single-winner attribution (Gap 3). Gives an audit trail for referral-overlap disputes without double-counting. (Lead-side mobile is available here — this is GoRefer's own capture form, unlike the conversion side R10/R11.)

## R14 — Compliance gate genuinely enforced (extends Gap 14)

- **Title:** The ADR-014 compliance gate was declared pipeline-enforced but nothing actually enforced it.
- **Decision (what GoRefer does):** Make it **genuinely enforced**: (1) **auto-inject the disclosure/risk block into the render/asset path** so nothing can render without it (enforced by construction); (2) add a **hard blocking pre-publish gate** — publish/generate **refuses** unless the compliance review is marked done. Wire it now (small in Sprint 1: admin-only, asset generator off) so "enforced" is literally true as public surfaces grow. Extends **Gap 14 / ADR-014**.

## R16 — PII kept out of the immutable event log (extends Gap 15)

- **Title:** Event-log immutability collides with DPDP anonymization when PII sits in event metadata JSONB.
- **Decision (what GoRefer does):** **Keep PII OUT of the immutable event log.** Personal data (name / phone / email) lives in a **separate, erasable person record**; **events reference the person by id only**. A **CI/code rule blocks any PII from being written into event metadata**. Satisfies both immutability (honest history) and DPDP erasure (anonymize the person record without touching the log). Extends **Gap 15 / ADR-020**.

## R17 — Store raw IP + city as PII, no hashing (amends Gap 15 / ADR-020)

- **Title:** A hashed IP is not real privacy (IPv4 is brute-forceable).
- **Decision (what GoRefer does):** **Store BOTH the raw IP and the city, plainly — no hashing.** The raw IP is **treated as PII**: it lives in the **erasable person/journey record** (not the immutable event log, per R16) and is covered by the DPDP rules already set — **12-month purge** of unconverted-prospect PII, **erasure-on-request**, **admin-only access**.
- **Rationale / notes:** **Reverses ADR-020's "derive city then hash/drop raw IP"** → now **"store raw IP + city as PII."** Hashing IPv4 was false privacy; treating the raw IP as erasable PII is both simpler and more honest.

## R18 — Source label on every status change

- **Title:** Status changes lacked a traceable origin.
- **Decision (what GoRefer does):** **Stamp a source/origin tag on every status change** — which system/event caused it and when (e.g. *"Zoho sync, 2026-07-06, zoho_lead_id 12345"*). The **audit backbone for never-fabricate**: every status must be traceable to an origin. Pairs with R6 (removal-with-audit) and R12 (explicit status map).

## R19 — Sync-freshness indicator (anti "fabrication by omission")

- **Title:** Silent stale Zoho data looks current but isn't.
- **Decision (what GoRefer does):** Store **`last_successful_zoho_sync_at`** (plus WATI health); show a **sync-health indicator** on the dashboard (*"Zoho synced 4 min ago ✓ / 2 days ago ⚠"*); **alert when staleness exceeds a threshold**. Guards against looks-current-but-isn't data. Pairs with R7 (sync worker) and R18 (source labels).

## A1 — 3-tier configuration cascade + compliance lock — ADR-022

- **Title:** How configurable values resolve, and what can never be weakened by an override.
- **Decision (what GoRefer does):** All configurable values resolve through a **3-tier cascade: CENTRAL (platform default) → GLOBAL (admin / PIFS instance-wide) → USER (per-user)**, precedence **user → global → central** (most specific wins, fall back to central). Applies to the WhatsApp number (confirms Gap 13), disclosure/incentive text, branding, program settings, etc. **Sprint 1: CENTRAL + GLOBAL(admin) tiers live; the USER tier is designed-in but DORMANT** behind `ENABLE_CUSTOMER_LOGIN` (Sprint 2+). **Compliance lock:** the SEBI/NSE disclosure + risk warning are **locked at central and NOT weakenable/removable** by global or user overrides (ties R14). Encoded as **ADR-022**. See memory: gorefer-config-hierarchy.

## A2 — Multi-tenant boundary now, SaaS later — ADR-023

- **Title:** GoRefer as a multi-tenant SaaS for other APs / distributors.
- **Decision (what GoRefer does):** **Not built in Sprint 1** (single-tenant = PIFS only), but **design the tenant boundary now**: bake a **`tenant`/`org_id` boundary into the data model from day one** (every row scoped to a tenant) so multi-tenancy is a later feature-flip, not a rebuild; the config cascade's global tier becomes per-tenant-admin. When enabled: **hard cross-tenant isolation**, **per-tenant compliance** (each AP's own NSE AP reg + disclosures, compliance-lock per tenant), and pricing/monetization. First validation tenant already in-family = **Madhu's AngelOne + MF (ARN-314013)** business. **Keep the feature OFF in Sprint 1.** Encoded as **ADR-023**. See memory: gorefer-config-hierarchy.

## Round-2 deferrals (Sprint 2+ / strategic)

The following Round-2 findings were **deferred to Sprint 2 or parked as strategic**, and are **not** built in Sprint 1:

- **#21** — trackable link alone won't sustain sharing (monitor; feed Sprint 2).
- **#22** — referrer feedback loops in Sprint 1 → **CONFLICTS with Gap 5 (none in Sprint 1)**; deferred to Sprint 2, gated on the WATI fix.
- **#23** — A/B capture-first vs direct redirect → capture-first stays locked; **instrument** friction, do not drop it.
- **#25** — Ashok as a human bottleneck (~15 leads/week) — scaling gap, Sprint 2.
- **#26** — incentive concentration / PIFS micro-incentive "Plan B" → **the PIFS-funded cash incentive is REJECTED** (violates Gap 4 / Gap 7 no-top-up); recognition-only if ever revisited.
- **#27** — referrer differentiation vs simply forwarding the Zerodha link — Sprint 2.
- **#28** — fraud / abuse economic model (bot filtering ≠ incentive-abuse) — Sprint 2 gap.
- **#29** — future-partner expansion realism (content/compliance won't port cleanly) — acknowledged.
- **#30** — GoRefer monetization path — folded into **A2** (multi-tenant SaaS).

---

*End of Document 12. Status: decisions locked. These resolutions — the original 16 gaps plus the Round-2 external-review decisions — supersede any conflicting edge-case narrative in earlier drafts and are the reference for implementation.*
