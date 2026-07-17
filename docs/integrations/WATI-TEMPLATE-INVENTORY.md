# GoRefer — WATI Template Inventory & Gap (AUTHORITATIVE)

> **Read this before touching WhatsApp sends.** It is the single reconciled picture of
> (a) which templates the GoRefer **code** sends, (b) which templates actually **exist**
> in the Wati account, and (c) the gap between them. Built so nobody re-inspects the live
> account to answer "why doesn't the WhatsApp send work."
>
> **Compiled:** 2026-07-17 (Engineer), from: live `wati_list_templates` (MCP, tenant 105355),
> the repo manifest `apps/integrations/wati/wati-templates.json`, `docs/integrations/08`,
> and `docs/sprint2/S2-WhatsApp-Wati-Test-Log-and-Learnings.md`. **If the live account and
> this doc disagree, re-pull and update this file.**

---

## TL;DR — there are TWO different template families, often confused

| Family | Purpose | Direction | Category | Live status |
|---|---|---|---|---|
| **A. Lead-capture notifications** (3) | Fire when a lead is captured | GoRefer → office / prospect / referrer | **UTILITY** | ❌ **DO NOT EXIST in Wati** |
| **B. Referrer "Refer & Earn"** (3 live) | Invite a referrer to share their link | GoRefer → referrer (recruitment) | **MARKETING** | ✅ **APPROVED** (+ 4 deleted) |

**They are NOT interchangeable.** Family B cannot stand in for Family A: different audience
(a referrer being recruited ≠ an office alert / a just-submitted prospect), different content,
and different category (MARKETING is per-user capped — 131049 — and is the wrong category for a
transactional office alert or prospect welcome). The gap that blocks the live loop is that
**Family A was never created.**

---

## Family A — the 3 templates the CODE sends (lead-capture) — MISSING

`apps/integrations/wati/notify.py` hardcodes these names and sends them on every lead capture:

| Code constant | Template name (hardcoded) | Role / audience | Category (intended) | In Wati? |
|---|---|---|---|---|
| `TPL_OFFICE` | `gorefer_office_new_lead` | Office/Ashok — "new lead, call them" | UTILITY | ❌ ABSENT |
| `TPL_PROSPECT` | `gorefer_prospect_welcome` | The prospect who just submitted the form | UTILITY | ❌ ABSENT |
| `TPL_REFERRER` | `gorefer_referrer_used` | The referrer — "someone used your link" (only if phone known) | UTILITY | ❌ ABSENT |

**Designed bodies** (from the repo manifest `wati-templates.json`, all currently `pending` design
entries — never submitted/approved):
- **office:** `New GoRefer lead: {{1}} (mobile {{2}}), referred by client {{3}}. Please call to help them open their Zerodha account.` — vars: prospect_name, prospect_mobile, referrer_client_id.
- **prospect:** `Hi {{1}}, {{2}} referred you to PIFS to open a free Zerodha demat & trading account. Our representative will call to help you complete it. Investments in the securities market are subject to market risks.` — vars: prospect_name, referrer_display.
- **referrer:** `Good news! Someone just used your PIFS referral link to start opening a Zerodha account. We'll keep you posted. Reward status is shown in your Zerodha Console.` — no vars.

**Live-probe proof (2026-07-17):** sending `gorefer_prospect_welcome` returns
`{"code":"Template","description":"template_name field is missing/wrong"}`. So a live send is
correctly *attempted* by the adapter and *fails* (recorded `failed`, never fabricated as delivered).

## Family B — the `gorefer_zerodha_*` templates that DO exist (Refer & Earn) — approved but different

Live status from `wati_list_templates` (MCP, tenant 105355, 2026-07-17):

| Template | Status | Category | Lang | Purpose |
|---|---|---|---|---|
| `gorefer_zerodha_eng_2026_07_10_v2` | ✅ APPROVED | MARKETING | en | KNOWN referrer, English — "Refer & Earn" invite (name var `{{1}}`; dynamic URL button `https://gorefer.in/r/wa/{{client_id}}` + 2 quick-replies) |
| `gorefer_zerodha_hin_2026_07_10_v2` | ✅ APPROVED | MARKETING | hi | KNOWN referrer, Hindi — same as above, Hindi |
| `gorefer_zerodha_eng_leads_2026_07_10` | ✅ APPROVED | MARKETING | en | UNKNOWN referrer (no client_id) — no name var; all 3 buttons quick_reply |
| `gorefer_zerodha_eng_2026_07_10` | 🗑 DELETED | MARKETING | en | superseded by `_v2` (scheme-less disclosure link bug) |
| `gorefer_zerodha_hin_2026_07_10` | 🗑 DELETED | MARKETING | hi | superseded by `_v2` |
| `gorefer_zerodha_referral_2026_07_10` | 🗑 DELETED | MARKETING | en | superseded/rebuilt |
| `gorefer_zerodha_eng_2026_07_10_test` | 🗑 DELETED | MARKETING | en | test artifact |

These are the **Sprint-2 WhatsApp amplification** templates (spec `S2-02`): they go TO a referrer
to recruit them into sharing, and carry the 10%-brokerage-share + 300-points incentive claim and
`Disclosures: https://gorefer.in/d/pifs`. They are the "Refer & Earn" kit, **not** the lead-capture
notifications.

## Also present (not part of either family, for completeness)
- `gorefer_login_otp` — Q-M-OTP AUTHENTICATION template (referrer login OTP). Manifest marks it
  **HOLD — do NOT submit until Abhay's review-go**. Not yet in the live-approved list above.

---

## The gap and the options

**Root cause:** the 3 lead-capture notification templates (Family A) were designed in the manifest
but **never created/approved in Wati**. The code sends their names; Meta rejects them as unknown.
The approved `gorefer_zerodha_*` templates (Family B) are a different feature and can't substitute.

**To make the lead-capture WhatsApp notifications deliver, one of:**

1. **Create Family A** (recommended, and the honest fix): submit `gorefer_office_new_lead`,
   `gorefer_prospect_welcome`, `gorefer_referrer_used` to Meta as **UTILITY** using the manifest
   bodies above (via the `wati-template-create-and-track` skill / API — the Wati MCP cannot create
   templates, only send approved ones). Then track to APPROVED. **Gated on:** Abhay's review-go
   (API-create == submit == publishing), the `zerodha-ap-social-media-compliance` review, and the
   compliance block (AP reg `AP2516003693`, market-risk wording). The prospect body already carries
   the market-risk line; office/referrer are internal/low-risk but still need sign-off.

2. **Re-point the code** only if a role genuinely maps to an existing approved template — it does
   **not** here (Family B is recruitment MARKETING, wrong audience + category for all three roles),
   so this is not viable without new templates.

**Independent of the template gap:** the config-driven-template principle still applies — the names
should move OUT of hardcoded `notify.py` constants into config (a `ReferralProgram` field or a
`rule_template_map`) read at send time, so template versioning never needs a code deploy. See
memory `decide-dont-ask-and-config-driven-templates` and `gorefer-wati-template-name-mismatch`.

**Decision owner:** which templates to create + their exact approved copy is Abhay/DA's call
(compliance content + a Meta submission). The `LiveWatiAdapter` (built 2026-07-17, commit `96aa3cc`)
already does the send + honest terminal-status reconcile correctly once approved templates exist.

## How this was verified (so it needn't be redone)
- Live list: `wati_list_templates` (MCP, tenant 105355) → 100 templates, 7 `gorefer_*`, statuses above.
- Absence of Family A: direct `sendTemplateMessage` probe → `template_name field is missing/wrong`.
- Bodies/design: `apps/integrations/wati/wati-templates.json` (repo manifest).
- Family B history + compliance audit + the live E2E learnings: same manifest's `_compliance_audit_2026_07_10`
  / `_live_family_2026_07_10_v2` blocks, and `docs/sprint2/S2-WhatsApp-Wati-Test-Log-and-Learnings.md`.
