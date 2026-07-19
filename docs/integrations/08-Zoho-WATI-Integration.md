# 08 — Zoho + WATI Integration Contracts (GoRefer)

> **What this document is.** The **integration contract** between GoRefer and its two external systems of record: **WATI** (WhatsApp Business API — the outbound campaign + notification channel) and **Zoho CRM Plus** (the lead pipeline and the ONLY authority for account/reward status). It defines who owns which data, the exact join keys, the call directions, and the hard constraints that a wrong assumption here would silently violate.
>
> **Read alongside:** `GoRefer-Master-SourceOfTruth-from-ChatGPT.md` (origin vision), `GoRefer-Build-Spec-Cowork-Decisions.md` (locked decisions + live Zerodha test), `GoRefer-Context-Brief.md` (settled facts). Where those disagree, the Build-Spec and Context-Brief win — they are grounded in live 2026-07-04 testing.
>
> **Compiled:** 2026-07-04 (Cowork session). **Owner:** Abhay Kumar Maurya (PIFS, Zerodha Authorised Person).
>
> **Confidence tags:** [Certain] = verbatim in a source doc / verified by live test; [Likely] = strong inference; [Guessing] = gap being filled (flagged explicitly).

---

## 0. The one-paragraph mental model

GoRefer is the **referral intelligence layer** that sits between WATI and Zerodha. **WATI is a messenger, not a brain** — it delivers the campaigns and notifications GoRefer tells it to send. **GoRefer is the brain** — each referrer's link is simply `gorefer.in/r/{client_id}` carrying their raw Zerodha `client_id` (no token, no mapping — ADR-001); GoRefer captures the lead and decides what fires. **Zoho is the ledger of truth for people and outcomes** — GoRefer creates the Lead on submit and *reads back* account-opening and reward status from Zoho. **GoRefer never fabricates an account-opening or reward event; those originate only in Zoho.** Zerodha remains the underlying brokerage; a real human (Ashok) completes account opening on a call.

```
                 generates link, decides sends           reads status back
   CUSTOMER ──▶  ┌────────────────────────────┐  ◀── writes Lead ──▶  ┌──────────┐
   / FRIEND      │        G o R e f e r        │                       │   ZOHO   │
                 │  (referral intelligence)    │                       │   CRM    │
                 └──────────┬─────────────────┘                        └──────────┘
                            │ tells WATI what to send                        ▲
                            ▼                                                 │ human
                       ┌─────────┐                                     ┌────────────┐
                       │  WATI   │ ── WhatsApp ──▶ Ashok / lead / ...  │  ZERODHA   │
                       └─────────┘                                     │  (broker)  │
                                                                       └────────────┘
```

---

## PART A — WATI INTEGRATION (the outbound channel)

### A1. What WATI is responsible for

[Certain] WATI sends **the referral campaigns** (the outbound WhatsApp templates targeting existing Zerodha customers) and **the three transactional notifications** that fire when a lead is captured (to Ashok, to the new person, and — conditionally — to the referrer). WATI does **not** generate links, does **not** hold the referral mapping, and is **not** a source of truth for anything. It is the delivery pipe.

[Certain] **Each referrer's link is `gorefer.in/r/{client_id}`** — the raw Zerodha `client_id` in the path (no token, no mapping — ADR-001). For a WATI campaign to Abhay's own customers, GoRefer builds each customer's `gorefer.in/r/{their_client_id}` link from data Abhay already has (this is **not** an import) and injects the finished string into the WATI template as a variable. The public GoRefer link is what the customer sees and shares; the raw Zerodha URL (`https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={{client_id}}`) is never exposed in any template — `c=ZMPHZC` is injected server-side at click time.

> **Identifier note (LOCKED, ADR-001).** The public link scheme is the **raw Zerodha `client_id` in the path** — there is no opaque token and no token→id mapping. WATI only ever receives a **finished string** from GoRefer, so the WATI contract is unaffected. (Future non-Zerodha partners with no reusable native id will use a GoRefer-generated id minted at referrer login — not Sprint 1.)

### A2. WATI account facts (settled — do not re-ask)

[Certain] (`wati-shared-capabilities-audit.md`, `WATI-ZOHO-INTEGRATION-MAP.md` §1.)

| Field | Value |
|---|---|
| Tenant | `105355` |
| WABA id | `108848848852725` |
| Business number | +91 70806 42020 |
| API host / base | `live-mt-server.wati.io/105355` |
| Auth | Bearer JWT (see A7 security) |
| Meta daily cap | 100,000 unique contacts/day (using ~0.09%) |
| Messaging quality | High (protect this — see A3) |
| Send mechanism today | Zoho workflow → Deluge → WATI REST `sendTemplateMessage` (`?SourceType=ZOHO`); each send is a 1-recipient "campaign" named `zoho_auto_<template>` |

### A3. ⚠️ THE CRITICAL COWORK REALITY — ~33% delivery failure (funnel leaks at step zero)

[Certain] (`wati-shared-delivery-failure-rca.md`, `wati-shared-capabilities-audit.md`, `WATI-ZOHO-INTEGRATION-MAP.md` §1.)

**The current WATI campaign failure rate is ~33% over a rolling 30 days (5,402 attempts), spiking to ~60% in bad 7-day windows.** This is not a cosmetic problem — **it is the funnel leaking at step zero.** GoRefer can build the most elegant referral engine in the world, but if one in three campaign messages never arrives, one in three referral loops never even starts. **This MUST be fixed before or in parallel with GoRefer launch, not after.**

**Root causes (all four must be addressed):**

1. **No opt-in** — messaging contacts who never opted in. WATI defaults every contact to `Allow Campaign = true` and does **not** honour Zoho's opt-out fields today, so suppressed/unwilling contacts still get blasted.
2. **All-Marketing classification** — every recent template is category **MARKETING**, which is hardest to deliver, hits per-user marketing caps (Meta code `131049`), and erodes quality rating. Transactional messages should be **UTILITY**.
3. **Duplicate sends** — the same mobile number sits across **4 overlapping Zoho modules** (`Contacts`, `Leads`, `OfficeVisitors`, `Referrers`), so one person can be messaged multiple times from independent workflows — burning quota and annoying recipients.
4. **Invalid / non-WhatsApp numbers** — Zoho's existing raw lead lists contain numbers that were never on WhatsApp.

**The required fix (contract for GoRefer):**

- **Dedup + single suppression-aware audience.** GoRefer must never hand WATI a raw multi-module list. It must resolve to **one canonical audience keyed on normalized Mobile**, de-duplicated across all Zoho modules, with `Do_not_contact` / `WhatsApp_Opt_Out` / `Incorrect_Mobile` honoured **before** the send — not after.
- **Opt-in-aware sending.** No contact receives a marketing campaign unless opt-in state permits it (see A4). Transactional GoRefer notifications go out as **UTILITY** templates.
- **Verify actual delivery, never trust HTTP 200.** [Certain] HTTP 200 from WATI means "accepted," not "delivered." GoRefer (or its test harness) must read the **terminal message status** from WATI and classify failures by Meta error code. Use a fail-closed test-recipient allowlist for template testing. (Abhay's `wati-send-and-verify-delivery` skill.)

> **Design rule.** If the dedup + opt-in-aware audience is not in place, GoRefer's launch amplifies a broken pipe. Treat "audience is deduped and suppression-aware" as a **precondition**, not a feature. **Fixing this ~33% delivery failure is a HARD prerequisite** before GoRefer relies on WhatsApp for any notification — and it **gates spend**: money should not go into WhatsApp-dependent flows until the pipe delivers reliably.

### A4. Opt-in rule (protect the whole number)

[Certain] (`GoRefer-Build-Spec` §7.4.)

**Messaging a lead who did NOT themselves opt in risks Meta flagging / throttling the ENTIRE WATI business number** — not just that one conversation. In GoRefer's capture-first flow, the *referrer* often submits the *friend's* details, so the friend never opted in. Therefore:

- **The first message to such a lead MUST be a warm, utility-style notice that names the referrer** — e.g. *"[Referrer] referred you to PIFS to open a Zerodha account. Our representative will call to help."* — **not** a marketing blast.
- Naming the referrer establishes context and legitimacy; a cold marketing template to a non-opted-in number is the single fastest way to get the number throttled.
- **Watch volume.** Ramp gradually; a sudden spike of first-contact messages to non-opted-in numbers looks like spam to Meta.

Meta failure codes to classify: `131049` (per-user marketing cap), `131048` / `131026` (spam/quality-related, per ambassador-plan references).

### A5. Template approval — lead time and the three GoRefer templates

[Certain] (`GoRefer-Build-Spec` §9, `wati-templates.json`, `WATI-ZOHO-INTEGRATION-MAP.md`.)

- **Every WhatsApp template must be Meta-approved before it can send.** Approval lead time is **hours to ~2 days**. **Submit templates in parallel with the build** — do not serialize the build behind approval.
- The GoRefer three transactional notifications (Ashok alert / new-person warm notice / referrer thank-you) each need an approved template. Choose category deliberately: the Ashok alert and the referrer thank-you are **UTILITY**; the new-person notice is **UTILITY** (warm, referrer-named — see A4).
- **Existing manifest** (`Wati-Project/docs/wati-templates.json`, all currently `pending`): `daily_delivery_report` (UTILITY, internal), `zerodha_refer_earn_v3` (MARKETING, en — vars `{{1}}`=name, `{{2}}`=client_id; dynamic URL button `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={{2}}`), `zerodha_refer_earn_v3_hi` (Hindi variant).
- A rejected template must be revised and resubmitted (idempotent tracking — Abhay's `wati-template-create-and-track` skill). Never resubmit an already-APPROVED/PENDING template.

### A6. WATI send contract (the message-fire sequence)

[Certain] (`GoRefer-Build-Spec` §4.) On lead capture, GoRefer instructs WATI to fire up to **three** messages, each a Meta-approved template:

| # | Recipient | Trigger condition | Category | Body (intent) |
|---|---|---|---|---|
| a | **Ashok** (Prayagraj office) | always | UTILITY | New lead `[name, mobile, referred-by]` — call now. |
| b | **New person / friend** | always | UTILITY | "[Referrer] referred you to PIFS to open a Zerodha account. Our representative will call to help. To continue yourself: [link with `r=`]." (warm, referrer-named — A4) |
| c | **Referrer** | **only if referrer phone resolvable from Zoho** | UTILITY | "Your referral for [name] is registered — thank you." |

- Message (c) fires **only** when the referrer's phone is resolvable from Zoho by `client_id` (see B4). For open-ended/unknown referrers GoRefer has only the `client_id`, no phone → **skip silently, do not fabricate a number.**
- **Referrer-notification side-effects (the msg (c) thank-you) are deferred to Sprint 2.** Sprint 1 captures the lead and fires the Ashok + new-person messages; wiring the referrer thank-you as an automatic side-effect waits until the delivery-failure fix above is proven, so it does not amplify a leaking pipe.
- **Ashok's WhatsApp number for the alert template is an OPEN decision** (Context-Brief §7.2 #4). The helpline +91 73888 82020 exists but the alert-target number is unconfirmed — treat as a config value, not a hardcode.

### A7. WATI security finding (must fix)

[Certain] A long-lived admin WATI bearer JWT (issued 25-Feb-2025, ~2050 expiry) is **hardcoded inline** in Zoho Deluge functions and exposed on the WATI API-docs screen. **Rotate it and move it to Zoho Variables/Connections (or GoRefer's secret store).** GoRefer must read the token from config/secrets, never inline.

### A8. Future capability (DEFERRED — not Sprint 1): GoRefer → Wati automated stale-lead nudge

> **Deferred to a later sprint (Sprint 2+). Do NOT build in Sprint 1.** (Foundation Spec REQ-F01.)

When a GoRefer-sourced lead ages without converting (e.g. approaching Zerodha's 60-day attribution window), GoRefer would **automatically send a WhatsApp reminder to the prospect via Wati** to nudge them to complete account opening.

- **Sprint 1 (locked):** stale-lead follow-up is **owned by Zoho** (source of truth); GoRefer only surfaces a **read-only aging flag** derived from its own timeline. GoRefer never overrides Zoho.
- **Future:** GoRefer moves from passive aging flag → active stale-lead Wati nudge.
- **Hard dependency:** this **must not** ship until the **delivery-dedup + opt-in fix** (the ~33% delivery-failure problem in A3, plus the A4 opt-in rule) is in place. Layering an automated nudge on top of a leaking, non-opt-in-aware pipe would amplify the very failure A3 warns about.
- **Meta compliance:** the nudge must be a **warm, utility-style** message (A4), never a marketing blast, and must honour opt-in / suppression state before sending.

---

## PART B — ZOHO INTEGRATION (the ledger of truth)

### B1. The cardinal rule — account-opening & reward come ONLY from Zoho

[Certain] (`GoRefer-Build-Spec` §4, `GoRefer-Context-Brief` §5.)

**GoRefer WRITES the Lead (on name + mobile submit) and READS BACK account/contact status from Zoho. GoRefer never fabricates an account-opening or reward event.** Zoho is **pulled/mirrored** — GoRefer's conversion view is a mirror of Zoho's **current** mappings, held with no provisional/final distinction: a conversion is exactly what Zoho maps at read time, nothing more. The chain of authority:

- **A referral is "converted" only when Zoho says so.** Account opening happens off-platform (Zerodha drives KYC after a human, Ashok, assists). Zoho is where that outcome is recorded — as an **"Imported Event" with a recorded source** — and GoRefer reflects Zoho's state; it does not invent it.
- **Reward status** (300 points, 10% brokerage-share eligibility) is likewise a downstream Zerodha/Zoho fact. GoRefer displays it by reading Zoho; it must never compute or assert a reward that Zoho hasn't recorded.
- This keeps GoRefer honest: the referral dashboard can show "lead captured / contacted / KYC started / account opened" states, but the transition to **account opened** and **rewarded** must be sourced from Zoho, tagged with the recorded source of that import.
- **A monthly reconciliation batch (~5th–6th of the following month) fills in missing mappings and fixes gaps** — Zoho's referral mappings are often incomplete until Zerodha's month-end settlement lands, so GoRefer re-pulls and reconciles rather than freezing an early, incomplete snapshot.
- **Removals propagate.** If a mapping disappears or is corrected in Zoho (e.g. a wrongly-credited referrer is reversed), GoRefer reflects that too — via a reversal/tombstone carrying an audit trail — so a de-mapped conversion never lingers as a phantom credit.

### B2. What GoRefer writes to Zoho

[Certain] (`GoRefer-Build-Spec` §4 step 2.) On the branded GoRefer form submit (fields: mobile, name, email; `c=ZMPHZC` + `r=<client_id>` baked in and hidden):

1. **Save the lead to our system FIRST** — before anything Zerodha-side — so the lead is never lost even if the person abandons Zerodha's form.
2. Create a **Lead** in Zoho carrying: friend name, friend mobile, friend email (if given), **source** (whatsapp_campaign / landing_page / manual / etc.), and **referred-by** = the referrer's `client_id`.
3. Alert Ashok instantly (via the WATI Ashok template, A6-a).

> **Lead destination is an OPEN decision** — Zoho CRM, WATI, or both (Build-Spec §6, Context-Brief §7.2 #3). This contract assumes Zoho is the lead of record; if "both," WATI's contact record is a mirror, and Zoho remains the ledger for status.

### B3. What GoRefer reads back from Zoho

[Certain/Likely] GoRefer polls or subscribes to Zoho for the referred person's progression:

- **Contact / Lead status** — New → Contacted → Interested → KYC Started → **Account Opened** → Rejected (statuses per `GoRefer-Master` §6.13).
- **Account-opening event** — recorded in Zoho as an **Imported Event with a recorded source**; GoRefer reflects it, never fabricates it.
- **Reward / eligibility** — read from Zoho's referral/commission data; displayed, not computed.

**Conversion data shape and keys.** A converted referral, as GoRefer mirrors it from Zoho, carries **the opener's name, the opener's Zerodha account ID, and the referrer's Zerodha client ID** — **no mobile number**. The **referrer is matched by Zerodha client ID** (never by mobile): the `r=<client_id>` on the referral resolves to the credited referrer. The **conversion uniqueness key is the opener's Zerodha account ID (or `zoho_lead_id`)**, and each conversion is written as an **upsert** on that key so a re-pull updates in place rather than duplicating.

- **Opener → journey link.** GoRefer prefers to stamp a **GoRefer reference on the Zoho lead** and have it **echoed back** on the converted record, giving a precise opener-to-journey join (**confirm feasibility** with the Zoho lead-write path). Where that reference is absent, the link is **best-effort / referrer-only** — the conversion is still credited to the referrer, but not tied to a specific click journey.

**History is fetched lazily, per referrer.** When a referrer first appears in GoRefer (first click or first Zoho-imported conversion), GoRefer pulls **that referrer's** conversion history on demand — it does **not** do a fixed bulk load of everyone up front. A full all-time bulk backfill (every historical opening since 2016, for complete all-time global aggregates at launch) is a deferred one-off — see backlog **DF-4**.

### B4. Zoho modules and the join keys

[Certain] (`WATI-ZOHO-INTEGRATION-MAP.md` §2, `wati-shared-delivery-failure-rca.md` §5a.) Zoho CRM Plus — tenant `passiveincomesolutions`, org id `60019670093`.

| Module (API name) | Approx size | Role for GoRefer |
|---|---|---|
| `Contacts` | ~23,748 | Real customers + curated leads; mirrors WATI's contact list. Primary place to **resolve a referrer's phone from `client_id`** (enables WATI msg c). |
| `Leads` | 17,638 | Uncontacted/raw existing Zoho lists; source of the ~1,200/day WATI blast. GoRefer creates new referral leads here (or a dedicated pipeline). |
| `Referrers` (`CustomModule3`) | ~600 | The referral codes from the brokerage sheet — a **metrics target**, NOT a send audience. This is where referrer-level metrics roll up. |
| `OfficeVisitors` (`CustomModule2`) | 2,000+ | Prayagraj walk-ins. Has almost no opt-out fields — a dedup/suppression hazard. |
| `Comissions` (`CustomModule1`) | stale | Vestigial brokerage ledger (last refreshed Jul-2023). |
| `Employees` (`CustomModule4`) | — | Internal. |

**Join keys — the two that matter:**

- **`Mobile`** (phone) — the cross-module identity key. Normalize consistently: *remove spaces / `+` / `()` / `-`, then prefix `91`.* This is the dedup key for the single suppression-aware audience (A3).
- **Client ID** — `ClientId` in `Contacts`, `Client_Id` in `Referrers`. This is the **referrer** join key: it maps a referral's `r=<client_id>` back to a real Zoho contact so GoRefer can (a) resolve the referrer's phone for WATI msg c, and (b) roll referral metrics into the `Referrers` module.

> **Note the field-name inconsistency:** `ClientId` (Contacts) vs `Client_Id` (Referrers). GoRefer's Zoho adapter must handle both. **Mobile + Client ID are the two join keys** on which the whole integration hinges.

### B5. Compliance/opt-out fields (not uniform — handle defensively)

[Certain] `Do_not_contact`, `WhatsApp_Opt_Out`, `Incorrect_Mobile`, `Email_Opt_Out`, `Deactivated` exist on `Contacts` but are **NOT uniform across modules** — `OfficeVisitors` has almost none. WATI does not honour Zoho opt-outs today (live DPDP/compliance risk). GoRefer must treat a **missing** suppression field as "unknown," not "safe," and default to the more conservative behaviour. There is no WATI→Zoho webhook for delivery/read/opt-out feedback today — closing that loop is part of the dedup fix.

### B6. The sync worker (how status flows in)

[Certain] Status flows from Zoho into GoRefer through a dedicated **sync worker**, built to be resumable and self-healing rather than fire-and-forget:

- **Watermark.** The worker advances a watermark (last-processed marker) so each pull resumes from where it left off and never re-scans the whole history.
- **Dead-letter + retry.** A record that fails to process is retried; on repeated failure it lands in a dead-letter queue for inspection rather than blocking the stream or being lost.
- **Off-platform auto-create.** A conversion that arrives from Zoho with a referrer but **no prior GoRefer click** (an off-platform account opening) causes the worker to **lazily create the referrer identity and journey** so the conversion is still recorded — a converted journey can exist with zero clicks.
- **Idempotency guard.** Because conversions upsert on the opener's Zerodha account ID / `zoho_lead_id` (B3), re-processing the same record is a no-op update, not a duplicate — the worker is safe to re-run.
- **Source labels on status changes.** Every status transition GoRefer records is stamped with its **source** (which import/webhook/reconciliation pass set it), preserving the audit trail and keeping GoRefer honest about where each fact came from.
- **Health signals.** The worker exposes **sync-freshness** (how current the Zoho mirror is) and **WATI delivery health** so an operator can see at a glance whether either pipe has gone stale.

### B7. The Zoho → GoRefer status webhook (inbound trust)

[Certain] Zoho pushes account-opening/reward status to GoRefer over an inbound webhook. Since this endpoint is the **sole writer of conversions and credited-referrer data**, its authenticity matters:

- **Sprint 1 (now):** a **basic shared static key plus a Zoho server-IP allowlist** — cheap hygiene that keeps the endpoint from being trivially forged. (The endpoint only goes live from M6; M1–M4 run demo-mode with `ENABLE_ZOHO_WRITE` off, so there is no live exposure yet.)
- **Deferred — DF-2:** the full **"wax-seal"** (HMAC signature over payload + timestamp + one-time nonce, rejecting forged, stale, or replayed messages). To ship before the webhook is relied on for real referrer-reward payouts.
- **Deferred — DF-1:** replacing the inbound push with a **Zoho-API "pull"** (GoRefer polling Zoho over OAuth), which removes the forgeable inbound endpoint entirely. Kept as push for now; folds into the sync-worker hardening.

---

## PART C — COMPLIANCE GATE (applies to every WATI template & asset)

[Certain] (`GoRefer-Build-Spec` §7, `GoRefer-Context-Brief` §6.) The origin ChatGPT doc omitted compliance entirely; it is a **hard pre-publish gate** here.

- **Every WATI template, poster, landing page, and social asset must carry the AP disclosure block (verbatim):**

```
Zerodha Broking Ltd.: SEBI Registration no.: INZ000031633 | Passive Income Financial Solutions Private Limited | NSE AP reg. no.: AP2516003693
```

- **Market-risk warning (min font 10, verbatim):** "Investments in securities market are subject to market risks, read all the related documents carefully before investing." If brokerage rates are mentioned: "Brokerage will not exceed the SEBI prescribed limit."
- **Every asset must pass** the NSE Code of Advertisement (NSE/COMP/55482) and the SEBI Feb-2026 social-media disclosure circular (effective 1-May-2026), and must be run through Abhay's `zerodha-ap-social-media-compliance-skill` **before publishing** — this is a hard gate.
- **The 10% brokerage-share claim is LIVE but REVOCABLE.** It rests on NSE/INSP/66284 (24-Jan-2025) holding the ban (NSE/INSP/63425) in abeyance, reverting to NSE/INSP/43824 (permits it). **If NSE reinstates the ban, all "10%" content becomes non-compliant.** Therefore **keep the 10% wording in a single, swappable source** (one template variable / one config string), so it can be pulled everywhere in one edit.
- **No misrepresentation:** the GoRefer form must NOT resemble Zerodha's signup page (misrepresentation risk under NSE/COMP/55482) — reinforces the PIFS-branded, no-clone decision. No superlatives, no income projections/assured returns, no NSE logo, no MCX claims.

---

## PART D — INTEGRATION CONTRACT SUMMARY (the one-screen checklist)

| Boundary | GoRefer's obligation | Never do |
|---|---|---|
| **WATI — link** | Build `gorefer.in/r/{client_id}` (raw client_id, no token), inject finished string into template. | Expose raw Zerodha URL or `c=ZMPHZC` in any template. |
| **WATI — audience** | Hand WATI ONE deduped, suppression-aware, opt-in-aware audience keyed on normalized Mobile. | Hand WATI a raw multi-module list (duplicate sends). |
| **WATI — first contact** | First message to a non-opted-in lead = warm UTILITY notice naming the referrer. | Send a cold MARKETING blast to a non-opted-in number. |
| **WATI — delivery** | Read terminal message status; classify failures by Meta code. | Trust HTTP 200 as "delivered." |
| **WATI — templates** | Submit for Meta approval in parallel with build (hours–~2 days). | Serialize build behind approval; resubmit approved templates. |
| **WATI — secrets** | Read bearer token from secret store. | Inline the JWT. |
| **Zoho — write** | Create the Lead on name+mobile submit; save lead FIRST; alert Ashok. | Skip local capture and go straight to Zerodha. |
| **Zoho — read** | Read account-opening & reward status back from Zoho ("Imported Event," recorded source). | Fabricate an account-opened or reward event. |
| **Zoho — keys** | Join on normalized `Mobile` and Client ID (`ClientId`/`Client_Id`). | Assume a single field name; assume missing opt-out = safe. |
| **Compliance** | Disclosure block + risk warning on every asset; run compliance skill; 10% claim in one swappable place. | Publish anything unaudited; hardcode the 10% claim in many places. |

---

*Session: Cowork, 2026-07-04. Origin vision unchanged in `GoRefer-Master-SourceOfTruth-from-ChatGPT.md`. Live-test + decision ground truth in `GoRefer-Build-Spec-Cowork-Decisions.md` and `GoRefer-Context-Brief.md`.*
