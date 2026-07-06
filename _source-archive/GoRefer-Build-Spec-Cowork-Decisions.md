# GoRefer — Build / Decision Spec (Cowork Session)

> **What this document is.** This is the **build spec** for GoRefer. It captures the decisions and findings from the **Cowork working session dated 2026-07-04**, layered on top of the origin document.
>
> **Read alongside** [`GoRefer-Master-SourceOfTruth-from-ChatGPT.md`](./GoRefer-Master-SourceOfTruth-from-ChatGPT.md) — that ChatGPT document is the **origin / source-of-truth** (the original 14-section vision). This document **complements** it; it does **not** replace it. Where the two disagree, the conflict is flagged explicitly (see §5 Identifier and §6 Open decisions).
>
> **Do not treat this as the vision doc.** The vision lives in the ChatGPT source-of-truth. This is the ground-truth of *what we decided and verified on 2026-07-04* and what remains open before build.

---

## 1. Project scope

**GoRefer** is a **referral-management platform**. It is the same purpose earlier discussed under the working name **refer.pifs.in**, now productized as **GoRefer** with an enlarged scope.

- **Start narrow:** Zerodha only.
- **Expand later:** multiple brokers / partners / companies over time.
- **Build as a scalable product from day one**, per Abhay's core principles — permanent productized solutions (never a temporary patch just for one user), automation-first, minimal manual input from users.

---

## 2. Requirements captured (R1–R7)

| ID | Perspective | Requirement / problem |
|----|-------------|-----------------------|
| **R1** | Partner | The refer-a-friend link must carry **BOTH** the partner code (`c=ZMPHZC`) **AND** the referring client's Zerodha client ID (`r=<client_id>`). The new account then maps to **both** the partner and the referrer. |
| **R2** | Partner | A plain signup link carries **only** the partner code. The account maps to the partner alone — no referrer benefit. |
| **R3** | Partner | **No click tracking exists today.** Also, the partner/referrer codes are visible & editable on Zerodha's own form, so mappings can be altered. |
| **R4** | Partner | Links are **long and fragile**. The partner code can be dropped or mistyped → lost mapping, or mapping to the wrong partner. |
| **R5** | End user | Referring is a **confusing multi-step process**, and the referrer's own ID can be broken. The user needs **one simple action**. |
| **R6** | Solution vision | **One short link** that fires the referral and leads to account opening, with the partner code **hidden** from casual tampering. |
| **R7** | Partner | Anyone can **replace the partner code with their own** to self-refer and cut the partner out → **revenue leakage**. |

---

## 3. Verified facts about Zerodha's links

*Confirmed by a live test + screenshot, July 2026.*

**Identifiers used in testing**

| Item | Value |
|------|-------|
| Partner (AP) code | `ZMPHZC` |
| NSE AP registration no. | `AP2516003693` |
| Sample referrer client ID | `DA1707` |

**What the links actually do**

- `https://signup.zerodha.com/api/lead?c=ZMPHZC&r=DA1707` lands **DIRECTLY** (one hop) on Zerodha's "**Signup now**" form. Fields observed: mobile number, full name, e-mail, account-type dropdown, reCAPTCHA, **Continue**.
- **BUT that form is LEAD-CAPTURE ONLY.** Submitting it ends at a "**thanks / we'll contact you**" screen — it does **NOT** proceed into full account opening (PAN / KYC).
- Tested variant `/?c=ZMPHZC&r=DA1707` also pre-fills both codes but **likewise stops at "thanks."**
- **Full KYC / account opening is a separate step** that Zerodha drives afterward via its own follow-up.

**Why the codes cannot be locked**

- The partner code and referrer code appear as **pre-filled, EDITABLE text boxes** on the form — the user can change or delete them before submitting.
- Therefore **R3 / R7 (locking the codes) CANNOT be fully prevented**, because it is **Zerodha's own page**, not ours.

**Why we must never auto-submit**

- The form carries **Google reCAPTCHA** → automated / background submission of Zerodha's form is **bot-gated** and **MUST NOT be attempted** (compliance + account risk).
- The **only compliant path** is redirecting a **real human browser** to the public link.

**Attribution constraints**

- The referred account must open **within 60 days** of the referral.
- If the prospect had **already registered** on Zerodha before using the link, **the mapping does not apply.**

---

## 4. The agreed solution design (capture-first, human-assisted)

The core idea: **capture the lead in our own system first**, then hand a real human off to Zerodha's public form — never automate Zerodha's page.

### Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. OUR branded GoRefer form                                            │
│    "Passive Income Financial Solutions — open your Zerodha account"    │
│    (NOT a Zerodha look-alike)                                          │
│    Fields: mobile, name, email                                        │
│    Partner code (c=ZMPHZC) + referrer code (r=<client_id>) baked in,   │
│    HIDDEN. Referrer may fill friend's details OR friend fills own.     │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │ submit
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 2. SAVE LEAD TO OUR SYSTEM FIRST (Zoho CRM / Wati)                     │
│    Lead is never lost, even if the person abandons Zerodha.            │
│    Ashok (Prayagraj office) alerted instantly.                        │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 3. THREE WhatsApp messages fire via Wati (each needs Meta-approved     │
│    template):                                                          │
│    a) → Ashok:    new lead [name, mobile, referred-by], call now.     │
│    b) → new person: "[Referrer] referred you to PIFS to open a         │
│         Zerodha account. Our representative will call to help.         │
│         To continue yourself: [link with r=]."                        │
│    c) → referrer (ONLY if phone resolvable from Zoho):                │
│         "Your referral for [name] is registered — thank you."         │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 4. Ashok CALLS and helps the person complete Zerodha account opening. │
│    Human satisfies reCAPTCHA legitimately.                            │
│    Preserves partner + referrer mapping.                              │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 5. "Continue account opening" link sent to the new person KEEPS r=    │
│    (Decision: Option A) so the referrer stays credited — even though  │
│    it ends at "thanks" and the human completes KYC.                   │
└──────────────────────────────────────────────────────────────────────┘
```

### Step detail

1. **Our branded form.** Clearly labelled "**Passive Income Financial Solutions — open your Zerodha account**", **NOT** a Zerodha look-alike. The referrer may fill in the friend's details, **or** the friend fills their own. Fields: mobile, name, email. Partner + referrer codes are **baked in and hidden**.
2. **Save the lead FIRST.** On submit, write the lead to **our** system (Zoho CRM / Wati) **before** anything Zerodha-side, so the lead is never lost even if the person abandons Zerodha. **Ashok (Prayagraj office) is alerted instantly.**
3. **Three WhatsApp messages fire via Wati** (each needs a Meta-approved template):
   - **To Ashok:** new lead `[name, mobile, referred-by]`, please call now.
   - **To the new person:** "*[Referrer] referred you to PIFS to open a Zerodha account. Our representative will call to help. To continue yourself: [link with r=].*"
   - **To the referrer** — **ONLY if their phone number is resolvable from Zoho.** For open-ended / unknown referrers we only have the `client_id`, no phone. Message: "*Your referral for [name] is registered — thank you.*"
4. **Ashok calls and helps** the person complete the Zerodha account opening. This satisfies reCAPTCHA legitimately (a real human), and preserves the partner + referrer mapping.
5. **The "continue account opening" link keeps `r=`** (Decision: **Option A**), so the referrer stays credited — even though the link ends at "thanks" and the human completes KYC.

---

## 5. Decisions locked in this session

| # | Decision | Status |
|---|----------|--------|
| 1 | **Capture-first flow** — our branded form runs *before* Zerodha's form. | **LOCKED** |
| 2 | **Keep `r=` in the continue link (Option A)** — referrer stays credited. | **LOCKED** |
| 3 | **Ashok completes the account opening on the call** (not the referrer). | **LOCKED** |
| 4 | **Do NOT auto-submit Zerodha's form** (reCAPTCHA + compliance + account risk). | **LOCKED** |
| 5 | **Do NOT clone / spoof Zerodha's page**; our form must be clearly **PIFS-branded**. | **LOCKED** |
| 6 | **Identifier scheme** — Abhay's stated preference in this session = **raw `client_id` in the path (no database).** ⚠️ **CONFLICTS** with the ChatGPT source-of-truth, which uses an **opaque token** (`z.gorefer.in/r/{token}`) requiring a DB. Recorded as an **OPEN decision** (see §6) with this context — *not* locked. | **OPEN** |

---

## 6. Open decisions

| Decision | Options | Recommendation | Status |
|----------|---------|----------------|--------|
| **Domain / URL scheme** | (a) `z.gorefer.in` subdomain [ChatGPT doc]; (b) `gorefer.in` bare-domain + path; (c) a hyphenated variant Abhay recalls but not yet located in the docs | **Bare domain + path** for a one-person operation (simpler DNS / SSL / ops). Graduate to subdomains per partner later. | **OPEN — awaiting Abhay** |
| **Identifier** | raw `client_id` in path (no DB) **vs** opaque token (needs DB) | **Reconcile before build.** Raw `client_id` is simpler but exposes the ID; a token allows revocation / rotation. | **OPEN** |
| **Lead destination** | Zoho CRM, Wati, or both | — | **OPEN** |
| **Ashok's WhatsApp number** | needed for the alert template | — | **OPEN** |
| **Sub-model** | referrer fills friend's details (lower friction, WhatsApp opt-in risk) **vs** friend fills own details (clean opt-in) | — | **OPEN** |

---

## 7. Compliance requirements (MANDATORY)

> The ChatGPT source-of-truth **omits all of this.** This section is a hard gate on the build. Nothing publishes until it passes.

### 7.1 Incentive-claim status — LIVE but REVOCABLE

The claim "**300 reward points + 10% of brokerage**" is **currently permitted** but sits on shifting regulatory ground:

- **NSE/INSP/63425 (14-Aug-2024)** — banned non-AP referrer brokerage-sharing.
- **NSE/INSP/66284 (24-Jan-2025)** — put that ban in **ABEYANCE**.
- Interim regime **reverted to NSE/INSP/43824 (11-Mar-2020)**, which **permits** it.
- Zerodha **relaunched refer-and-earn** on these terms.

**Implication:** if NSE reinstates the ban, all public content claiming **10%** becomes **non-compliant**. **Keep the wording easy to pull** (single source, swappable in one place).

### 7.2 Required AP disclosure block

Must appear on **every owned channel / asset**:

```
Zerodha Broking Ltd.: SEBI Registration no.: INZ000031633 | Passive Income Financial Solutions Private Limited | NSE AP reg. no.: AP2516003693
```

### 7.3 Advertising & disclosure norms

- All public assets (posters, social posts, landing pages, WhatsApp templates) must pass the **NSE Code of Advertisement (NSE/COMP/55482)** and the **SEBI Feb-2026 social-media disclosure norms**.
- **Run Abhay's `zerodha-ap-social-media-compliance` skill on every asset before publishing.**

### 7.4 WhatsApp / Meta opt-in

- Messaging a new lead who did **not** themselves opt in (i.e. when the **referrer** submitted their details) **risks Meta flagging / throttling the whole Wati business number.**
- The **first message** to such a lead must be a **warm, utility-style notice naming the referrer** — **not** a marketing blast. **Watch volume.**

### 7.5 No misrepresentation

- Our form must **not resemble** Zerodha's signup (misrepresentation risk under **NSE/COMP/55482**).

---

## 8. Residual risks (cannot be fully eliminated)

| Risk | Mitigation | Residual state |
|------|-----------|----------------|
| **R7 code-swap** on Zerodha's own editable form | hidden default in our link | **Mitigated but not preventable** — it is Zerodha's page. |
| **Referrer notification impossible for unknown referrers** (no phone; only `client_id`) | message only when phone is **resolvable from Zoho** | Inherent — accept. |
| **Multi-step account opening** is inherent to Zerodha's referral flow | the human (**Ashok**) bridges the gap on a call | Inherent — accept. |

---

## 9. Recommended tech approach

- **Redirect + lead-capture service** — recommended: a **Cloudflare Worker** that **logs clicks** (solves **R3** tracking) and forwards to the correct **pre-filled Zerodha public URL**.
- **Zoho CRM** (already licensed) for the lead pipeline.
- **Wati** (already subscribed) for WhatsApp templates — **3 templates need Meta approval** (lead-time: hours to ~2 days).
- **Build order:** build the **form + CRM capture first** (works immediately); **submit Wati templates in parallel.**

---

## 10. How this maps to the ChatGPT source-of-truth

This build spec **fulfills the same 14-section vision** set out in [`GoRefer-Master-SourceOfTruth-from-ChatGPT.md`](./GoRefer-Master-SourceOfTruth-from-ChatGPT.md), while making four concrete corrections / additions grounded in this session's live testing:

1. **Corrects the URL / identifier open question.** The ChatGPT doc assumes an opaque token on `z.gorefer.in`; this session recorded Abhay's preference for a **raw `client_id` in a bare-domain path** and flags the conflict as an **open decision** to reconcile before build (§5, §6) — rather than silently adopting either.
2. **Adds the reCAPTCHA / lead-capture reality.** Verifies that Zerodha's link lands on a **lead-capture-only form** that **stops at "thanks"** and is **bot-gated** — so the flow **cannot** be automated and must be human-assisted (§3, §4).
3. **Adds the capture-first, human-assisted flow.** Save the lead in our system **first**, alert Ashok, and let a **human** complete Zerodha's KYC — preserving attribution without touching Zerodha's page (§4).
4. **Adds the entirely-missing compliance layer.** The full NSE / SEBI / Meta compliance gate (§7) — absent from the ChatGPT doc — is now a mandatory pre-publish requirement.

---

*Session: Cowork, 2026-07-04. Origin document (unchanged): `GoRefer-Master-SourceOfTruth-from-ChatGPT.md`.*
