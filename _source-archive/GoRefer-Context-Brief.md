# GoRefer — Consolidated Context Brief

> **Purpose.** One place that captures every decision and fact about the GoRefer / Zerodha referral project that has **already been made, agreed, or verified** — so basic settled questions stop getting re-asked. Every claim is sourced to a file on disk. Where a source doc leaves something genuinely unresolved, it is listed under §7 OPEN — nowhere else.
>
> **Compiled:** 2026-07-04 (Cowork session). **Owner:** Abhay Kumar Maurya (PIFS, Zerodha Authorised Person).
>
> **Confidence tags:** [Certain] = stated verbatim in a doc / verified by live test; [Likely] = strong inference across docs; [Guessing] = gap being filled. Nothing below is [Guessing] unless it says so.
>
> **Source files read for this brief:**
> - `GoRefer/GoRefer-Master-SourceOfTruth-from-ChatGPT.md` (origin vision, 14-section spec)
> - `GoRefer/GoRefer-Build-Spec-Cowork-Decisions.md` (2026-07-04 decisions + live Zerodha test)
> - `GoRefer/GoRefer-Resume-Brief.md`, `GoRefer/ChatGPT-Discussion*.md`, `GoRefer/GoRefer-ChatGPT-Full-Formatted.md`, `GoRefer/README.md`
> - `Wati-Project/docs/wati-templates.json`; `5Wealths/wati-capabilities-audit.md`; `5Wealths/wati-message-failure-fix.md`
> - `Financial Wealth/FW-Zerodha/WATI-ZOHO-INTEGRATION-MAP.md`; `.../compliance.md`; `.../AMBASSADOR-PROGRAM-PLAN.md`
> - `VideCoding/GLOBAL.md` (canonical cross-project identity / link table)

---

## 1. Business setup (the ground truth — do not re-ask)

**Entity.** [Certain] Passive Income Financial Solutions Private Limited ("PIFS"). Director: Abhay Kumar Maurya. Registered office: Bldg D, Flat 802, Capital Tower, Wakad Link Road, Pune 411057. Branch: "Zerodha Prayagraj," managed by **Ashok Kumar Patel since 2022**. (`GLOBAL.md` §1.)

**Zerodha Authorised Person.** [Certain]
- Principal broker: **Zerodha Broking Ltd — SEBI Reg no. INZ000031633**.
- **NSE AP registration no.: `AP2516003693`** (appointed 10-Dec-2024; PIFS a Zerodha AP since 2016).
- **Zerodha partner / open-account code: `c=ZMPHZC`**.
- **MCX: NOT registered — never claim MCX.** (`GLOBAL.md` §1; `GoRefer-Build-Spec` §3.)

**Sample referrer client ID used in testing:** [Certain] **`DA1707`** = Abhay's own Zerodha client ID (`...&r=DA1707`). (`GLOBAL.md` §1; `GoRefer-Build-Spec` §3.)

**Madhu Kushwaha (spouse).** [Certain] AngelOne Authorised Person (since 2018); AMFI MF Distributor **ARN-314013** (on AssetPlus since 03-Jul-2025). AngelOne / MF is **out of scope for GoRefer** (`wati-message-failure-fix.md` §3). (`GLOBAL.md` §1.)

**Ashok's role.** [Certain] Runs the Prayagraj office; logs walk-in "Office Visitors," follows up leads, assists KYC/account opening, answers client questions. He is the human who completes Zerodha account opening on a call in the GoRefer flow. Account-opening helpline: **+91 73888 82020** (`ashokpifs@gmail.com`). In Wati he is an OPERATOR (usually Offline). (`GLOBAL.md` §1; `WATI-ZOHO-INTEGRATION-MAP.md` §1; `GoRefer-Build-Spec` §4.)

**How referrals / brokerage-sharing works.** [Certain]
- A Zerodha lead/signup link carries two codes: `c=` (partner → credits PIFS as AP for ongoing brokerage) and `r=` (referrer's Zerodha client ID → credits that client under Zerodha's Refer & Earn).
- Canonical **referral link form:** `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={{client_id}}` — `c=ZMPHZC` credits PIFS; `r=<client_id>` credits the referring client. Build per recipient from their Zoho `ClientId`.
- Plain partner links (no referrer): `https://signup.zerodha.com/?c=ZMPHZC` and `https://signup.zerodha.com/api/lead/?c=ZMPHZC`.
- Reward to the referrer: **300 Zerodha reward points + 10% of the referred client's brokerage** (status caveat in §6). Eligibility for the brokerage share: **≥3 successful referrals in the trailing 12 months**; payout withdrawable from Console once ₹100 accrues. (`GLOBAL.md` §1 "Key links"; `AMBASSADOR-PROGRAM-PLAN.md` §1.2; `GoRefer-Master` §2.)
- Empirical proof the dual mapping works: the Brokerage Analysis Google Sheet shows **4,281 accounts mapped to ZMPHZC, ~1,421 carrying a referrer code**. (`AMBASSADOR-PROGRAM-PLAN.md` §1.1.)

**Systems already owned.** [Certain]
- **Zoho CRM Plus** — tenant `passiveincomesolutions`, org id `60019670093`.
- **Wati** — WhatsApp Business API, tenant `105355`, business number **+91 70806 42020**, host `live-mt-server.wati.io`.
- **Link hub (LIVE, canonical):** `https://passive-income-solutions.github.io/` (GitHub org `Passive-Income-Solutions`, login `abhayinfosys@gmail.com`). (`GLOBAL.md` §1.)

---

## 2. GoRefer — concept, scope, and DECISIONS ALREADY MADE

### 2.1 Concept and scope

[Certain] **GoRefer is a referral-management platform / layer** — not just a WhatsApp campaign. It sits between Wati and Zerodha and "knows the customer ID, generates the referral link, stores friend details, assigns an executive, tracks progress, and records outcomes. Zerodha remains the underlying brokerage platform." (`GoRefer-Master` §1.)

[Certain] It is the same purpose earlier discussed as **refer.pifs.in**, now productized as **GoRefer** with enlarged scope. **Start narrow: Zerodha only. Expand later: multiple brokers/partners/companies.** "Build as a scalable product from day one." (`GoRefer-Build-Spec` §1.) Future subdomains envisioned: `groww.gorefer.in`, `upstox.gorefer.in`, `insurance.gorefer.in`, `mf.gorefer.in` — "same platform, different partner." (`GoRefer-Master` §6.14.)

[Certain] **Core design priority:** don't make referral depend on customers understanding referral links. Always push the **"Share Friend Name + Mobile"** path as recommended (highest conversion); keep the personal referral link available everywhere as the **secondary** path. Team-assisted onboarding converts better. (`GoRefer-Master` §7.)

### 2.2 The requirements that motivated it (R1–R7)

[Certain] (`GoRefer-Build-Spec` §2.) R1: link must carry **both** `c=ZMPHZC` and `r=<client_id>`. R2: plain link credits partner only. R3: **no click tracking today**, and codes are visible/editable on Zerodha's form. R4: links are long/fragile (codes can drop or be mistyped). R5: referring is confusing and multi-step. R6: want **one short link** that fires the referral, partner code hidden from casual tampering. R7: anyone can swap the partner code to self-refer → **revenue leakage**.

### 2.3 Decisions LOCKED in the 2026-07-04 build session

[Certain] (`GoRefer-Build-Spec` §5, §4.)

| # | Decision | Source |
|---|----------|--------|
| 1 | **Capture-first flow** — our own branded GoRefer form runs *before* Zerodha's form; lead is saved to our system first so it's never lost. | Build-Spec §5.1, §4 |
| 2 | **Keep `r=` in the "continue account opening" link (Option A)** — referrer stays credited even though the link ends at "thanks" and a human completes KYC. | Build-Spec §5.2, step 5 |
| 3 | **Ashok completes the account opening on the call** (not the referrer). | Build-Spec §5.3, step 4 |
| 4 | **Do NOT auto-submit Zerodha's form** — reCAPTCHA + compliance + account risk. The only compliant path is redirecting a real human browser. | Build-Spec §5.4, §3 |
| 5 | **Do NOT clone/spoof Zerodha's page** — our form must be clearly **PIFS-branded** ("Passive Income Financial Solutions — open your Zerodha account"), not a Zerodha look-alike. | Build-Spec §5.5, §4 |

### 2.4 The agreed capture-first, human-assisted flow

[Certain] (`GoRefer-Build-Spec` §4.) (1) Our PIFS-branded form (fields: mobile, name, email; `c=ZMPHZC` + `r=<client_id>` baked in and **hidden**; referrer may fill friend's details OR friend fills own). → (2) **Save lead to our system first (Zoho CRM / Wati)**; Ashok alerted instantly. → (3) **Three WhatsApp messages fire via Wati** (each needs a Meta-approved template):
- **(a) → Ashok:** new lead `[name, mobile, referred-by]`, call now.
- **(b) → new person:** "[Referrer] referred you to PIFS to open a Zerodha account. Our representative will call to help. To continue yourself: [link with `r=`]."
- **(c) → referrer:** "Your referral for [name] is registered — thank you." — **ONLY if the referrer's phone is resolvable from Zoho** (for open-ended referrers we may only have `client_id`, no phone).

→ (4) Ashok calls and helps complete Zerodha opening (human satisfies reCAPTCHA legitimately, preserves both mappings). → (5) The continue link keeps `r=`.

### 2.5 The multi-channel campaign surface (from the origin vision)

[Certain] Every touchpoint carries **both** the customer referral link and the PIFS partner link. Channels specified: Wati/Meta WhatsApp template (vars `{{1}}`=name, `{{2}}`=referral link, `{{3}}`=partner link); WhatsApp Status (image, no clickable link); Facebook / Instagram (link-in-bio) / LinkedIn / X / Email; a referral **landing page**; and a **referral asset generator** (Status 1080×1920, IG story/post, FB post, interactive PDF). Admin panel, analytics, leaderboard of top referrers. (`GoRefer-Master` §4, §6.9–6.13.)

### 2.6 Recommended tech approach (proposed, not yet locked)

[Certain as *recommendation*] Redirect + lead-capture service, recommended as a **Cloudflare Worker** that logs clicks (solves R3) and forwards to the correct pre-filled Zerodha URL; **Zoho CRM** for the lead pipeline; **Wati** for the 3 templates (need Meta approval, hours–~2 days). Build order: **form + CRM capture first** (works immediately), submit Wati templates in parallel. (`GoRefer-Build-Spec` §9.) Note: this is the doc's recommendation; the identifier/domain/lead-destination choices it depends on are still OPEN (§7).

---

## 3. Zerodha link mechanics — VERIFIED (live test, July 2026)

[Certain] Confirmed by live test + screenshot (`GoRefer-Build-Spec` §3):

- `https://signup.zerodha.com/api/lead?c=ZMPHZC&r=DA1707` lands **directly (one hop)** on Zerodha's "Signup now" form. Fields: mobile, full name, e-mail, account-type dropdown, **reCAPTCHA**, Continue.
- **That form is LEAD-CAPTURE ONLY.** Submitting ends at a "thanks / we'll contact you" screen — it does **not** proceed into full account opening (PAN/KYC). The `/?c=...&r=...` variant behaves the same.
- **Full KYC / account opening is a separate step** Zerodha drives via its own follow-up.
- The partner and referrer codes appear as **pre-filled, EDITABLE text boxes** → the user can change/delete them before submitting. Therefore **R3/R7 code-locking CANNOT be fully prevented** — it's Zerodha's own page, not ours. (Mitigate with a hidden default in our link; residual risk accepted.)
- The form carries **Google reCAPTCHA** → automated/background submission is bot-gated and **must not be attempted**.
- **Attribution constraints:** account must open **within 60 days** of the referral; **if the prospect already registered with Zerodha before using the link, the mapping does not apply.** (Also in `GoRefer-Master` §2.3; `AMBASSADOR-PROGRAM-PLAN.md` §1.2.)

---

## 4. Wati — capabilities, existing templates, setup, constraints

### 4.1 Account & setup [Certain]
- Tenant **`105355`**, WABA id `108848848852725`, number **+91 70806 42020**, host `live-mt-server.wati.io`. Meta daily limit **100,000 unique contacts/day** (using ~0.09%); messaging quality **High**. Operators: AI Support Agent, Ashok Patel, Abhay Kumar. (`wati-capabilities-audit.md`; `WATI-ZOHO-INTEGRATION-MAP.md` §1.)
- **API:** full REST API (bearer auth), endpoint base `live-mt-server.wati.io/105355`. Key endpoints exist for contacts, `sendTemplateMessage(s)`, interactive buttons/CTA/list, chatbots, `scheduleBroadcast`. (`wati-capabilities-audit.md`.)
- **Send mechanism today:** Zoho workflow rules → Deluge functions → Wati REST `sendTemplateMessage` (`?SourceType=ZOHO`); each send is a 1-recipient "campaign" named `zoho_auto_<template_name>`. (`WATI-ZOHO-INTEGRATION-MAP.md` §3.)

### 4.2 Existing templates
- [Certain] Wati holds **119 templates**, all recent ones Marketing category; last new template 24-Dec-2025; **none carry the SEBI EoDI disclosure** (`WATI-ZOHO-INTEGRATION-MAP.md` §1). The dominant production template is **`zerodha_angelone_open_account_2025_12_24`** (dual-broker account-opening pitch), reused by four workflows. Other active: `angel_one_referral_bonus_2025_12_24`, `stay_connected_20241207`, `office_visitor_20231110`. (`WATI-ZOHO-INTEGRATION-MAP.md` §3.)
- [Certain] **GoRefer-specific template manifest** — `Wati-Project/docs/wati-templates.json` defines three, all **status `pending`**:
  1. **`daily_delivery_report`** (key `DAILY_DELIVERY_REPORT`, UTILITY, en) — 8 vars; internal delivery report to Abhay.
  2. **`zerodha_refer_earn_v3`** (key `REFER_EARN_EN`, MARKETING, en) — vars `{{1}}`=name, `{{2}}`=client_id; dynamic URL button `https://signup.zerodha.com/api/lead/?c=ZMPHZC&r={{2}}`; footer "Brokerage payouts begin Aug 2026 · T&C apply".
  3. **`zerodha_refer_earn_v3_hi`** (key `REFER_EARN_HI`, MARKETING, hi) — Hindi variant of the above.
- [Certain] The ambassador program specifies a **new** template `zerodha_ambassador_dynamic_2026_05` (Marketing, English; vars `{{1}}`=First_Name, `{{2}}`=ClientId) with the full compliance disclosure block — drafted, pending compliance audit + Meta submission. (`AMBASSADOR-PROGRAM-PLAN.md` §6.1.)

### 4.3 Sending / verification approach & constraints [Certain]
- **Never trust HTTP 200** — it only means "accepted." Verify actual delivery from Wati's terminal message status. Use a fail-closed test-recipient allowlist. (Abhay's `wati-send-and-verify-delivery` skill.)
- **Known delivery problem:** campaign failure rate **~33% (30-day, 5,402 attempts)** rising to **~60% in bad 7-day windows** — burning paid sends and eroding Meta quality. Root causes under investigation: invalid/non-WhatsApp numbers, missing opt-in, all-Marketing template classification, and **duplicate sends** because the same mobile sits across 4 overlapping Zoho modules. (`wati-message-failure-fix.md`; `wati-capabilities-audit.md`; `WATI-ZOHO-INTEGRATION-MAP.md` §1.)
- **Opt-in cap risk:** messaging a lead who did **not** opt in themselves (i.e., the referrer submitted their details) risks Meta flagging/throttling the whole business number. The first message to such a lead must be a **warm, utility-style notice naming the referrer**, not a marketing blast; watch volume. (`GoRefer-Build-Spec` §7.4.) Meta failure codes are classified in Abhay's skills (e.g. `131049` = per-user marketing cap; ambassador plan references `131048`, `131026`).
- **Security:** a long-lived admin Wati bearer JWT (issued 25-Feb-2025, ~2050 expiry) is **hardcoded inline** in the Zoho Deluge functions and also exposed on the Wati API-docs screen → must be rotated and moved to Zoho Variables/Connections. (`WATI-ZOHO-INTEGRATION-MAP.md` §3 security finding; `wati-capabilities-audit.md`.)
- **Largely-unused levers already paid for:** Astra AI agents, Chatbots (0), Automations/Sequences/Flows/Routing/Drip (all off), Catalog + WhatsApp Pay, CTWA (paid add-on ~₹5,000/mo, not bought), full API (token unused). (`wati-capabilities-audit.md`.)

---

## 5. Zoho CRM — what is documented

[Certain] Zoho CRM Plus, tenant `passiveincomesolutions`, org id `60019670093`. This IS well documented — chiefly in `WATI-ZOHO-INTEGRATION-MAP.md` (snapshot 2026-05-22, walked live via the Zoho MCP) plus the ambassador-program specs. Key facts:

**Modules in use** (API names): `Contacts` (~23,748 — real customers + curated leads; mirrors Wati's contact list), `Leads` (**17,638** — uncontacted/raw imports; the source of the ~1,200/day Wati blast), `Referrers` (`CustomModule3`, ~600 — the referral codes from the brokerage sheet; a *metrics* table, not a send audience), `OfficeVisitors` (`CustomModule2`, 2,000+ — Prayagraj walk-ins), `Comissions` (`CustomModule1`, stale brokerage ledger, last refreshed Jul-2023 — vestigial), `Employees` (`CustomModule4`). Join keys: `Mobile` (phone) and client-id (`ClientId` in Contacts, `Client_Id` in Referrers). (`WATI-ZOHO-INTEGRATION-MAP.md` §2; `wati-message-failure-fix.md` §5a.)

**How sends fire:** 13 workflow rules across 4 modules → Deluge functions → Wati API. The dominant one is **`Message_New _Old_leads`** (Leads, ~1,200/day). Two locked rules broadcast referral links to existing clients (`Zerodha_client_referral`) and remind referrers (`Zerodha_Referrer_Reminder`). Rules gate (where fields exist) on `WhatsApp_Opt_Out`, `Do_not_contact`, `Incorrect_Mobile`, plus a 15-day frequency cap. (`WATI-ZOHO-INTEGRATION-MAP.md` §3.)

**Compliance/opt-out fields** (`Do_not_contact`, `WhatsApp_Opt_Out`, `Incorrect_Mobile`, `Email_Opt_Out`, `Deactivated`) exist on Contacts but are **NOT uniform** — OfficeVisitors has almost none. Wati does **not** honor Zoho opt-outs today (every Wati contact defaults `Allow Campaign = true`) → a live DPDP/compliance risk. No Wati→Zoho webhook for delivery/read/opt-out feedback. (`WATI-ZOHO-INTEGRATION-MAP.md` §3–4.)

**GoRefer relevance:** the build-spec names **Zoho CRM as the lead destination candidate** and the place to resolve a referrer's phone from `client_id`. Detailed Zoho field/workflow/Deluge specs for referral automation already exist under `FW-Zerodha/ambassador/` (`zoho-fields-spec.md`, `zoho-workflow-rule.md`, `deluge-functions.md`, `active-client-sync-spec.md`). So Zoho is **documented, not absent** — but whether GoRefer writes leads to Zoho, Wati, or both is still an OPEN decision (§7).

**Wati↔Zoho integration:** fully mapped in `WATI-ZOHO-INTEGRATION-MAP.md` — verified Deluge call pattern, phone normalization (`remove spaces/+/()/-`, prefix `91`), the 4 independent send populations, the hardcoded-token finding, and the "what is NOT happening" gaps (no delivery webhook, no opt-out loop, no segmentation pull).

---

## 6. Compliance status

[Certain] (`GoRefer-Build-Spec` §7; `FW-Zerodha/compliance.md`; `AMBASSADOR-PROGRAM-PLAN.md` §1.3, §5; `GLOBAL.md` §1.)

**The 10%-brokerage / "abeyance" situation — LIVE but REVOCABLE.** The claim "300 reward points + 10% of brokerage" is **currently permitted**, but on shifting ground:
- **NSE/INSP/63425 (14-Aug-2024)** banned non-AP referrer brokerage-sharing.
- **NSE/INSP/66284 (24-Jan-2025)** put that ban **IN ABEYANCE** (paused, not repealed).
- Interim regime reverts to **NSE/INSP/43824 (11-Mar-2020)**, which **permits** brokerage-sharing referral. Zerodha relaunched Refer & Earn on these terms.
- **Implication:** if NSE reinstates the ban, all public content claiming **10%** becomes non-compliant → **keep the 10% wording in a single, swappable place.** (Verified 2026-06-28.)

**Mandatory AP disclosure block** — on every owned channel/asset (verbatim):
```
Zerodha Broking Ltd.: SEBI Registration no.: INZ000031633 | Passive Income Financial Solutions Private Limited | NSE AP reg. no.: AP2516003693
```
**Mandatory market-risk warning** (min font 10, verbatim): "Investments in securities market are subject to market risks, read all the related documents carefully before investing." If brokerage rates mentioned: "Brokerage will not exceed the SEBI prescribed limit."

**Advertising norms / gates.**
- All public assets must pass the **NSE Code of Advertisement (NSE/COMP/55482)** and the **SEBI Feb-2026 social-media disclosure circular** (HO/(79)2026-MIRSD-PODMMC, 26-Feb-2026, effective 1-May-2026).
- **Run Abhay's `zerodha-ap-social-media-compliance-skill` on every asset before publishing** — this is a hard gate.
- **Our form must not resemble** Zerodha's signup (misrepresentation risk under NSE/COMP/55482) → reinforces the "PIFS-branded, no clone" decision.
- **Rules of thumb:** no superlatives (best/No.1/lowest/leading), no income projections/assured returns, no NSE logo, no MCX claims, no PIFS-funded incentives on top of Zerodha's program (NSE/COMP/55482 §5.5), no paid ads pointing at client affiliate links (Zerodha T&C §15), no public-forum spam of affiliate links (T&C §8.h).
- **Undertakings:** Annexure B (Advertisement Code) and Annexure C (Artist) submitted by PIFS (exact dates TBD-confirmed); NSE registration cert on file. New AP creatives generally need Zerodha approval before publishing (Annexure B via the ENIT-COMPLIANCE module). (`compliance.md`.)

**Note:** the ChatGPT origin doc omitted all compliance; the Cowork build-spec added it as a mandatory pre-publish gate (`GoRefer-Build-Spec` §7, §10).

---

## 7. DECIDED vs genuinely OPEN

### 7.1 DECIDED / verified (stop re-asking these)
- [Certain] Partner code `c=ZMPHZC`; NSE AP `AP2516003693`; principal SEBI `INZ000031633`; Abhay's referrer id `DA1707`. (`GLOBAL.md`, `GoRefer-Build-Spec` §3.)
- [Certain] Referral link form = `signup.zerodha.com/api/lead/?c=ZMPHZC&r={{client_id}}`; `c` credits PIFS, `r` credits the client. (`GLOBAL.md`.)
- [Certain] Zerodha's link = **one-hop, lead-capture-only, ends at "thanks," reCAPTCHA-gated, codes editable**; 60-day window; prior-registration voids mapping. (`GoRefer-Build-Spec` §3.)
- [Certain] Capture-first flow; keep `r=` (Option A); Ashok completes on call; no auto-submit; no cloning Zerodha's page; PIFS-branded form. (`GoRefer-Build-Spec` §5.)
- [Certain] The **3 WhatsApp messages** (Ashok / new person / referrer-if-phone-known). (`GoRefer-Build-Spec` §4.)
- [Certain] Scope: start Zerodha-only, expand to multi-partner; product from day one. (`GoRefer-Build-Spec` §1.)
- [Certain] Recommended path is "Share Friend Name + Mobile," link is secondary. (`GoRefer-Master` §7.)
- [Certain] Compliance is a mandatory gate; disclosure block + risk warning + compliance-skill audit required. (`GoRefer-Build-Spec` §7.)
- [Certain] Tooling: Zoho CRM + Wati already owned; Cloudflare Worker is the recommended redirect/capture layer; build form+CRM first, Wati templates in parallel. (`GoRefer-Build-Spec` §9.)
- [Certain] Wati account facts (tenant 105355, number, limits) and the 3 pending GoRefer templates in `wati-templates.json`. (`wati-templates.json`, `wati-capabilities-audit.md`.)

### 7.2 GENUINELY OPEN (no doc resolves these)
[Certain that these are open — flagged unresolved in `GoRefer-Build-Spec` §5–6.]
1. **Identifier scheme** — raw `client_id` in the path (Abhay's stated 2026-07-04 preference, no DB) **vs** opaque token `z.gorefer.in/r/{token}` (ChatGPT source-of-truth, needs a DB). Explicitly recorded as OPEN / "reconcile before build." (`GoRefer-Build-Spec` §5 #6, §6.)
2. **Domain / URL scheme** — (a) `z.gorefer.in` subdomain; (b) `gorefer.in` bare-domain + path; (c) a hyphenated variant Abhay recalls but not yet located. Doc *recommends* bare-domain+path but it is **not locked**. (`GoRefer-Build-Spec` §6.)
3. **Lead destination** — Zoho CRM, Wati, or both. (`GoRefer-Build-Spec` §6.)
4. **Ashok's WhatsApp number for the alert template** — needed; the helpline 73888 82020 exists (`GLOBAL.md`) but the doc still lists this as OPEN, so treat the alert-template number as unconfirmed until Abhay says so. (`GoRefer-Build-Spec` §6.)
5. **Sub-model** — referrer fills friend's details (lower friction, opt-in risk) **vs** friend fills own details (clean opt-in). (`GoRefer-Build-Spec` §6.)
6. **Two source-doc conflicts still unreconciled:** (a) public link uses raw `client_id` (`z.gorefer.in/AB123`) vs opaque token (`z.gorefer.in/r/A7K29P`); (b) lead-capture fields — landing-page "Need Help" form uses Name/Mobile/**City** (3) while the WhatsApp bot uses Name/Mobile (2). Decide the canonical lead schema. (`GoRefer-Master` §5.1 NOTE, §6.6 NOTE.)

---

## 8. Related work already done (context, not GoRefer decisions)
- **Ambassador Program (Tier A)** — a fully-specified, compliance-audited, *non-invasive* monthly anniversary referral reminder to ~200–300 active PIFS-Zerodha clients, with new `Ambassador_*` Zoho fields, a new template, Deluge dispatcher (Wati primary + email fallback), cohort rollout, and a measurement dashboard. Its 4 pre-Day-1 questions were **closed 2026-05-23**. It reuses the same referral link and compliance block as GoRefer but is a separate, existing-client workstream. (`AMBASSADOR-PROGRAM-PLAN.md`.)
- **Wati delivery-fix project** — diagnosing/permanently fixing the 33–60% failure rate via dedup + suppression-aware single audience; referral data modeled as a child events table. (`wati-message-failure-fix.md`.)

---

*Compiled by Cowork, 2026-07-04. If any figure here conflicts with a newer live pull, trust the live pull and update this file + the root JOURNAL. Sources are named inline throughout.*
