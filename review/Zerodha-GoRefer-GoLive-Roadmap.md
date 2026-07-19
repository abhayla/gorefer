# Zerodha → GoRefer — Go-Live Roadmap (phases, tasks, dependencies)

> **What this is.** The ordered path from today's state to **Zerodha fully functional on GoRefer** —
> every remaining task, grouped by phase, with the dependency chain that dictates the order.
> **Owner:** Abhay / PIFS. **Created:** 2026-07-14. **Companion docs:**
> [`Deferred-Features-Backlog.md`](./Deferred-Features-Backlog.md) (DF-* items),
> [`../../Zoho-Project/send-queue/zoho-pifs-sendqueue-build.md`](../../Zoho-Project/send-queue/zoho-pifs-sendqueue-build.md) (queue build),
> [`../COORDINATION.md`](../COORDINATION.md) (DA⇆Engineer log). GoRefer app = Django M1–M8 (built + verified).
>
> **Status legend:** ✅ done · 🔧 built-not-live · ⏳ next · 🔒 gated (blocked by a dependency) · ⬜ later.

---

## The one load-bearing rule (why the order is what it is)

**Deliverability is the gate on everything.** The specs are explicit: `ENABLE_WATI_SEND`, referrer
OTP-over-WhatsApp, and all Wati nudges stay **blocked until the Send Queue proves one-per-person +
terminal-status delivery in production**. You cannot turn on GoRefer's WhatsApp or the customer product
on a channel failing ~60% — it just amplifies the broken pipe. So **Phase 1 first, always.**

```
P1 Deliverability (Send Queue live) ──┬──▶ P3 GoRefer live integration ──▶ P4 Customer self-service ──▶ P5 Scale
                                      └──▶ P2 UTILITY migration (parallel, boosts P1)
```

---

## PHASE 1 — Fix deliverability (the foundation) — ~80% done
**Goal:** kill the ~60% WhatsApp failure by making the Send Queue live in production.
**Why first:** every downstream item is gated on a reliable channel.

| # | Task | State | Depends on | Notes |
|---|------|-------|-----------|-------|
| 1.1 | Build queue data layer (WA_Send_Queue, WA_Contact_State, WA_Queue_Config + 18 config rows) | ✅ | — | Verified via MCP |
| 1.2 | Author + prove 6 gatekeeper Deluge functions (dedup/opt-out/junk/cap/welcome/officevisitor/source-self-clean) | ✅ | 1.1 | Dry-run proven live; every invariant verified |
| 1.3 | Wire + prove the real Wati send (token in Zoho Variable `wati_token`; query-param form; all template params) | ✅ | 1.2 | Proof-send DELIVERED to test number, terminal-verified |
| 1.4 | Paste the 3 send-block files (contacts/leads/welcome) into Zoho + Save | ⏳ | 1.3 | Human paste (browser tool can't edit Deluge). Inert until go-live (dry_run=true) |
| 1.5 | Schedule the gatekeeper functions | 🔒 | 1.4 | Referrers 10:30 · Contacts 12:00 · Leads 19:00 · welcome real-time · officevisitor on-visit-create (Zoho UI → Schedules) |
| 1.6 | Wire the Wati **inbound webhook** → `wa_inbound_webhook_handler` | 🔒 | 1.4 | Opt-out keyword → Opt_Out; any reply → Session_Open_Until = now+24h |
| 1.7 | **Week-1 delivery baseline** (`check-whatsapp-delivery-health`) | ⏳ | — | Measure the CURRENT real rate BEFORE go-live, so the fix is provable |
| 1.8 | Define the **Params_JSON contract** per template (name/value array, ALL vars) | 🔒 | 1.4 | Each converted rule must write correct params or Wati 400s. Tie to 1.9 |
| 1.9 | **⛔ Convert live Zerodha sending rules to write queue notes** — ONE bucket at a time | 🔒 | 1.4–1.8 | **The go-live.** Referrers first (smallest), overlapping-audience rules together, keep old code for rollback. Needs explicit go-ahead |
| 1.10 | Flip `dry_run=false` (allowlist first, then widen) + measure again | 🔒 | 1.9 | Confirm delivery jumps toward >90% eligible. **Closes the ~60% problem** |

**Phase-1 exit:** WhatsApp from Zoho is deduped, opt-out-safe, and delivering >90% of eligible sends,
proven against the week-1 baseline.

---

## PHASE 2 — Maximize deliverability (the other half) — parallel to P1
**Goal:** push delivery higher + protect the Meta quality rating. Independent of the rule conversion.

| # | Task | State | Depends on | Notes |
|---|------|-------|-----------|-------|
| 2.1 | **UTILITY template migration** — re-issue welcome/account-opened/referrer-status as UTILITY | ⬜ | — | UTILITY is cap-exempt → far better delivery. Use `wati-template-create-and-track` |
| 2.2 | Route transactional notes as UTILITY through the queue's fast-lane | 🔒 | 2.1, 1.4 | welcome_fastlane already treats UTILITY/TRANSACTIONAL as cap-exempt |
| 2.3 | Consent cleanup — OfficeVisitor feedback→session captures fresh consent over time | 🔧 | 1.6 | Grandfather legacy; new records need Consent=yes (config already set) |

---

## PHASE 3 — Turn on GoRefer's live integration (make the referral loop real) — 🔒 gated on P1
**Goal:** GoRefer (Django app, M1–M8, built + verified) goes from demo-mode to live. Flip the write flags
now that WhatsApp is reliable.

| # | Task | State | Depends on | Notes |
|---|------|-------|-----------|-------|
| 3.1 | Flip **`ENABLE_WATI_SEND`** → GoRefer's 3 lead-time notifications fire (Ashok / new person / referrer) | 🔒 | P1 exit | Routed through the proven queue |
| 3.2 | Flip **`ENABLE_ZOHO_WRITE`** — **Model 2: UPSERT by mobile.** GoRefer creates/updates the Lead in Zoho on capture, stamped with the journey-reference (#10); never blind-creates (search-or-create keyed on normalized mobile). | 🔒 | P1 exit **+** WRITE-upsert built & verified **+** Zoho Mobile-dedup rule live | **Supersedes DF-9** (Abhay+DA 2026-07-15). journey-id now hard-stamped on the lead |
| 3.3 | Flip **`ENABLE_ZOHO_READ`** → GoRefer reads account/reward status back onto the journey | 🔒 | P1 exit | Conversion truth from Zoho (never fabricated); **independent of WRITE** |
| 3.4 | Set **`WATI_WEBHOOK_KEY`** on prod → WhatsApp assisted-capture E2E works | 🔒 | P1 exit | Backlog precondition #3 |
| 3.5 | Confirm the full loop end-to-end in prod | 🔒 | 3.1–3.4 | click → landing → capture → lead saved → WhatsApp → Zoho lead → account opens → status syncs back → dashboard |

**Phase-3 exit = "Zerodha fully functional on GoRefer"** — referrals work end-to-end: capture, notify,
track, convert. (P4/P5 are enhancement + scale, not core function.)

---

## PHASE 4 — Customer-facing self-service (the product step) — 🔒 gated on P1
**Goal:** referrers log in and see their own performance.

| # | Task | State | Depends on | Notes |
|---|------|-------|-----------|-------|
| 4.1 | Meta-approve the **`gorefer_login_otp`** AUTH template (currently HOLD) | 🔒 | P1 exit | Needs the reliable channel |
| 4.2 | Wire the Zoho `client_id → on-file channel` READ (Q-M-OTP-2) | 🔒 | 3.3 | Resolves OTP recipient from Zerodha client id; live example QPJ023→9335138774 |
| 4.3 | Enable **`ENABLE_OTP_LOGIN`** — OTP over WhatsApp (Q-M-OTP, built behind flag) | 🔒 | 4.1, 4.2 | Ports-and-adapters already built + verified |
| 4.4 | Open **"My Referrals"** (`ENABLE_CUSTOMER_LOGIN`) — the M13 customer-login gate | 🔒 | 4.3 | Referrer sees their link, clicks, conversions (architected, disabled) |

---

## PHASE 5 — Deploy + harden for real traffic — ⬜ later
**Goal:** production-grade hosting + security for scale.

| # | Task | State | Depends on | Notes |
|---|------|-------|-----------|-------|
| 5.1 | Deploy GoRefer to the Hostinger VPS `72.61.240.224` (nginx + certbot) + DNS/TLS for `gorefer.in` | ⬜ | P3 | Per `docs/deploy/DEPLOY-TARGET.md` (authoritative) |
| 5.2 | HMAC "wax-seal" on the Zoho status webhook (DF-2) | ⬜ | 3.3 | Before any real reward payout depends on the webhook |
| 5.3 | Ongoing monitoring | 🔧 | P1 | `wati-referral-send-monitor` + `check-whatsapp-delivery-health` watch for regressions |
| 5.4 | Test-DB isolation (DF-TESTDB-ISOLATION) | ⬜ | — | CI hygiene; low prod risk |

---

## Dependency summary (the critical chain)

- **P1.4 (paste) → P1.5/1.6 (schedule + webhook) → P1.9 (rule conversion) → P1.10 (go-live + measure).**
- **P1 exit gates ALL of P3 and P4.** (WATI_SEND, ZOHO_WRITE, ZOHO_READ, OTP, customer login.) `ZOHO_WRITE` is now ON by design (Model 2 upsert-by-mobile, supersedes DF-9) and additionally gated on the WRITE-upsert adapter being built + verified and the Zoho Mobile-dedup rule being live.
- **P2 runs in parallel with P1** and boosts its delivery numbers.
- **P3 exit = the real definition of "fully functional."** P4/P5 are product + scale on top.

## Reusable skills supporting this roadmap
`audit-whatsapp-sends` · `check-whatsapp-delivery-health` · `run-whatsapp-send-queue` ·
`manage-zoho-functions` · `wati-send-and-verify-delivery` · `wati-template-create-and-track` ·
`zerodha-ap-social-media-compliance` (pre-publish gate for any public asset).

## Nearest highest-leverage move
**Finish Phase 1.** It's ~80% done, it fixes the headline ~60% failure, and it unblocks everything
downstream. The only human step in the near term is P1.4 (paste 3 files) — inert until go-live, so it can
happen whenever; the go-live decision is P1.9.
