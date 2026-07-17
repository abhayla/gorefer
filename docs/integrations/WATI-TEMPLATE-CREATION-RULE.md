# RULE — Whenever you create a WATI template, design the WHOLE flow (not just the message)

> **Standing rule (Abhay, 2026-07-17).** A WhatsApp template is never "just a message." Every
> template is the entry point to a *conversation* with buttons, routing, and follow-ups. Before any
> template is drafted or submitted to Meta, walk the **entire end-to-end flow** below and record the
> answers. This is a living document — **append what we learn**; never delete history.
>
> Companion docs: `WATI-TEMPLATE-INVENTORY.md` (what exists), `wati-templates.json` (the manifest),
> `docs/integrations/08-Zoho-WATI-Integration.md` (contract), `S2-WhatsApp-Wati-Test-Log-and-Learnings.md`
> (hard-won live learnings). Skill: `wati-template-create-and-track` (create + track to APPROVED).

---

## The end-to-end checklist (answer EVERY item before submitting)

### 1. Purpose & audience
- [ ] **Who receives it?** (office/Ashok · prospect · referrer · unknown-referrer). One template = one audience.
- [ ] **What triggers it?** (lead captured · referrer recruited · OTP · status change).
- [ ] **Is it transactional or promotional?** → decides category (next item).

### 2. Category (UTILITY vs MARKETING vs AUTHENTICATION) — deliverability-critical
- [ ] **UTILITY** for transactional/lifecycle (office alert, prospect welcome, "someone used your link").
      Uncapped — delivers reliably. **Default for GoRefer notifications.**
- [ ] **MARKETING** only for genuine promotion/recruitment (the Refer & Earn invite). **Subject to Meta's
      per-user cap (131049)** — will silently FAIL to a number that recently got marketing. Never use
      MARKETING for a message that must arrive (alerts, OTP, welcome).
- [ ] **AUTHENTICATION** for OTP only (copy-code button, no marketing, no free URLs).
- [ ] Wrong category is the #1 cause of "approved but doesn't deliver." (See test-log Test 1: a MARKETING
      refer template hit 131049.)

### 3. Variables ({{n}} / named)
- [ ] List every variable, its meaning, and a Meta sample value. Count must match what the code sends
      (`parameters:[...]`) — a mismatch = send fails.
- [ ] Prefer **named** vars ({{client_id}}) over positional where the API supports it (Abhay 2026-07-09).
- [ ] **Never trust a contact's positional/customParams** to fill vars — they're reused/stale across
      projects (test-log: real-estate params polluting a Zerodha contact). Pass explicit values.

### 4. Disclosure & compliance block (SEBI/NSE AP) — for ANY client/promotional content
- [ ] Does the content mention an incentive, referral, or investment? → it needs the disclosure.
- [ ] **Disclosure pattern (match the approved templates exactly):** a line near the end reading
      **`*Disclosures*: https://gorefer.in/d/pifs`** — bold label, **full `https://` URL** (a scheme-less
      `gorefer.in/...` in BODY TEXT does NOT render as a tappable link on WhatsApp and breaks the
      mandated §4.4 disclosure hyperlink — see test-log BUG_disclosure_link).
- [ ] Prospect-facing investment content also carries the **market-risk line** inline
      ("Investments in the securities market are subject to market risks.").
- [ ] The `/d/pifs` page must carry the §4.1 ID block (Zerodha SEBI INZ000031633 | PIFS | NSE AP
      `AP2516003693`) + §4.2 market-risk warning. Editing that page does NOT trigger a Meta re-approval.
- [ ] **Internal-only templates** (e.g. the office/Ashok alert — goes to PIFS's own staff, not a client
      or prospect) do **not** need the disclosure block. Decide audience first (item 1).
- [ ] **API-create == submit == publish.** Run the `zerodha-ap-social-media-compliance` review and get
      Abhay's explicit go BEFORE creating any client/promotional template.
- [ ] **Meta approval ≠ NSE/Zerodha approval.** AP-context referral content needs Zerodha written
      sign-off (referral T&C cl.8.vii) before a real broadcast.

### 5. Buttons — pick the RIGHT type, and design what each one DOES
For every button, record: type, label, and (critically) **what the user gets after tapping**.
- [ ] **Static URL button** — fixed link, no variable. Renders as a tappable button (URLs in buttons
      are fine even scheme-full; the scheme-less problem is only for URLs in BODY TEXT).
- [ ] **Dynamic URL button** — `https://gorefer.in/r/wa/{{client_id}}` style. WhatsApp requires the
      **variable LAST in the URL**, so you cannot append `?s=wa` after it → use a path route
      `/r/{channel}/{client_id}` (Q-M-CHANNELPATH). Record the `buttonParamMapping`.
- [ ] **Quick-reply button** — sends back its LABEL TEXT as an inbound message. **A quick reply is
      useless unless something is listening for that exact text.** For every quick reply, specify the
      route: which Wati keyword-action / chatbot flow / Astra agent fires, and what it replies with.
- [ ] **Copy-code (OTP) button** — AUTHENTICATION only.

### 6. Quick-reply / button ROUTING (the part everyone forgets)
- [ ] For each quick reply: **what happens next?** Name the handler (Wati keyword-action → chatbot flow,
      or Astra agent) and its exact response (text + any kit/link/image).
- [ ] **Keyword-actions match on the reply TEXT.** A Hindi button sends Hindi text → it needs its OWN
      keyword-action; the English keyword won't catch it (test-log finding #3). Every quick reply in a
      Hindi template needs a Hindi-text route.
- [ ] **Legacy-bot coexistence:** a live Wati chatbot currently intercepts ALL inbound, shows a menu,
      and auto-closes idle chats (test-log Key finding). A new quick-reply route must coexist with it,
      not be swallowed. Publishing/агent changes to the LIVE number are **not** done autonomously —
      Abhay's explicit ok + a coexistence plan required.
- [ ] **Attribution trap:** an unknown-referrer "Share" flow must capture THAT referrer's client_id
      first — reusing a fixed link (e.g. `.../r/wa/DA1707`) credits the wrong person (test-log OPEN q #2).
- [ ] **Known webhook gap:** the "Refer directly" chatbot collects Name/Phone/Email but does NOT POST to
      `/api/wati/webhook` and creates no Zoho lead. If a flow is meant to create a lead, that wiring must
      exist and be verified — don't assume the chatbot does it.

### 7. Language (Hindi + English parity)
- [ ] Every user-facing template should exist in **both English and Hindi** unless there's a reason not to.
- [ ] The Hindi version is a SEPARATE template (own name, e.g. `..._hin_...`) with its own approval.
- [ ] Hindi button labels differ → they need **separate keyword-actions / routes** (item 6).
- [ ] Keep the disclosure URL identical (`https://gorefer.in/d/pifs`) in both; translate the label
      (e.g. *खुलासा (disclosure)*).
- [ ] Decide language selection: how does the system know to send Hindi vs English? (contact attribute,
      referrer preference, default). Record it.

### 8. Naming & versioning
- [ ] **Convention: `gr_<partnerGroup>_<partner>_<purpose>_<lang>_<YYYY_MM_DD>`** — see the authoritative
      `WATI-TEMPLATE-NAMING-CONVENTION.md` (Abhay 2026-07-17). **Language (`en`/`hin`) is MANDATORY, just
      before the date, always present even for English.** E.g. `gr_brokers_zerodha_prospect_welcome_en_2026_07_17`,
      Hindi `gr_brokers_zerodha_prospect_welcome_hin_2026_07_17`. Partner is a single token (`angelone`,
      not `angel_one`). Bump the date (or `_v2` for same-day) on a re-submit.
      *(Templates created before this — `gorefer_zerodha_*` — are grandfathered, not renamed.)*
- [ ] A template body/button change = a NEW template + Meta re-approval (you cannot edit an approved
      template in place). Bot-reply materials (not in the template) are editable in the dashboard, no
      approval. Plan the version bump before you start.
- [ ] **Don't hardcode template names in code.** Names belong in config (a `ReferralProgram` field or a
      `rule_template_map`) read at send time, so a version bump doesn't need a code deploy. (This is why
      the 3 lead-capture names being hardcoded in `notify.py` is itself a debt item.)

### 9. Delivery verification (never trust the ack)
- [ ] Wati's `sendTemplateMessage` ack is `{"result":true}` with **no message id** — that's *accepted*,
      NOT delivered. Terminal status comes ONLY from `getMessages/{mobile}` (`statusString`
      DELIVERED/READ/FAILED). Never report delivered off the ack.
- [ ] Plan how terminal status is checked (the `LiveWatiAdapter` reconciles via getMessages; a webhook
      would need a correlation key, which the ack doesn't give).
- [ ] Classify FAILED by Meta code (131049 marketing-cap, 131026 not-on-WA, 131047 24h window, 131048
      spam-rate). Do NOT auto-retry a 131049 within 24h.

### 10. Test before broadcast
- [ ] Send to the test line (allowlist: `WATI_TEST_RECIPIENTS`) only; `WATI_ALLOW_ALL_RECIPIENTS` is an
      escalation.
- [ ] Verify terminal status = DELIVERED/READ via getMessages.
- [ ] Tap each button; confirm each quick reply's route fires and returns the right response (needs a
      human to tap — button taps aren't logged as inbound).
- [ ] Confirm the disclosure link opens (https, not scheme-less).
- [ ] Ask the human to confirm phone receipt (the one signal not in the API).

---

## Quick decision tree
```
New template?
├─ Who gets it?
│   ├─ PIFS internal staff (Ashok) ....... UTILITY, NO disclosure block, no buttons needed
│   ├─ Prospect (just submitted) ......... UTILITY, disclosure + market-risk line, minimal/no buttons
│   ├─ Referrer (transactional notice) ... UTILITY, disclosure line, minimal buttons
│   └─ Referrer (recruitment/promo) ...... MARKETING, disclosure + full flow (buttons + routes + Hindi)
├─ Any button? → for EACH: type + label + what-happens-after (route/response)
├─ Quick replies? → name the keyword-action/agent + its reply; Hindi needs its own route
├─ Hindi + English? → two templates, two approvals, two route sets, same disclosure URL
├─ Compliance content? → disclosure line `*Disclosures*: https://gorefer.in/d/pifs` + Abhay go + AP review
└─ Delivery → verify terminal status (getMessages), not the ack
```

## Change log
- **2026-07-17** — Rule created (Abhay). Seeded from the S2 test-log learnings + the approved
  `gorefer_zerodha_*` family's patterns (disclosure line, dynamic URL button, Hindi parity, quick-reply
  routing, legacy-bot coexistence). Keep appending.
