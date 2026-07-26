# WhatsApp Template Coverage Matrix

> **Generated 2026-07-26** from the live Wati inventory (100 records: 74 APPROVED, 25 DELETED,
> 1 PENDING) cross-referenced against template names **resolved on prod** (tenant 1) and the
> GoRefer code paths that send them.
>
> **The HTML conversation map is SSOT** — see `CLAUDE.md` §6c. This matrix is a *derived
> reconciliation view*: it exists to make config-vs-Meta drift visible. Where this matrix and the
> map disagree, the map states intent and the difference is a defect.
>
> **Regenerate** whenever a template is added, versioned, rewired, or deleted.
> Note: Wati's `wati_list_templates` **ignores `page_number`** (page 2 returns page 1), so 100 is
> the whole set, not a page.

## How to read this

- **Owner** = what actually triggers the send. `GoRefer code` = this repo. `Zoho/Wati journey` =
  driven outside GoRefer (Zoho Deluge functions / Wati flows) — *inferred from naming, verify before
  relying on it*. `UNWIRED / superseded` = approved at Meta but no known sender.
- **Cat** — `UTIL` (UTILITY) messages are not subject to the marketing per-user cap; `MARK`
  (MARKETING) are. `AUTH` = authentication. **Category is a deliverability decision, not cosmetic:**
  delivery has been running ~43% with Meta error `131049` (per-user marketing cap) dominating, so
  moving a must-arrive message from UTILITY to MARKETING actively harms it.

| Template | Status | Cat | Lang | Vars | Btn | Owner | Scenario | Config key |
|---|---|---|---|---|---|---|---|---|
| `gorefer_referrer_prospect_pending_en_2026_07_25_v3` | APPROVED | MARK | en | 3 | 0 | GoRefer code | S6.1 referrer nudge - idle prospect (EN) | `followup rule` |
| `gorefer_referrer_prospect_pending_hi_2026_07_25_v3` | APPROVED | MARK | hi | 3 | 0 | GoRefer code | S6.1 referrer nudge - idle prospect (HI) | `followup rule` |
| `gr_brokers_zerodha_office_lead_alert_en_2026_07_19` | APPROVED | UTIL | en | 4 | 0 | GoRefer code | Lead captured -> office/Ashok alert | `notify_template_office_en` |
| `gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v2` | APPROVED | UTIL | en | 3 | 0 | GoRefer code | Lead captured -> prospect welcome (EN) | `notify_template_prospect_en` |
| `gr_brokers_zerodha_prospect_welcome_hi_2026_07_17_v2` | APPROVED | UTIL | hi | 3 | 0 | GoRefer code | Lead captured -> prospect welcome (HI) | `notify_template_prospect_hi` |
| `gr_brokers_zerodha_referrer_update_en_2026_07_19` | APPROVED | UTIL | en | 2 | 0 | GoRefer code | Lead captured -> referrer update (EN) | `notify_template_referrer_en` |
| `gr_brokers_zerodha_referrer_update_hin_2026_07_19` | APPROVED | UTIL | hi | 2 | 0 | GoRefer code | Lead captured -> referrer update (HI) | `notify_template_referrer_hi` |
| `gr_platform_gorefer_login_otp_en_2026_07_21` | APPROVED | AUTH | en | 2 | 1 | GoRefer code | Referrer login OTP (M13) | `otp_whatsapp_template` |
| `gorefer_zerodha_eng_2026_07_10_v2` | APPROVED | MARK | en | 2 | 3 | Wati broadcast | Referral invite campaign | - |
| `gorefer_zerodha_eng_leads_2026_07_10` | APPROVED | MARK | en | 0 | 3 | Wati broadcast | Referral invite campaign | - |
| `gorefer_zerodha_hin_2026_07_10_v2` | APPROVED | MARK | hi | 2 | 3 | Wati broadcast | Referral invite campaign | - |
| `gr_platform_gorefer_delivery_report_en_2026_07_21` | APPROVED | UTIL | en | 11 | 0 | Wati-Project daily_report | 21:30 IST delivery report | - |
| `gr_platform_gorefer_funnel_report_en_2026_07_21` | APPROVED | UTIL | en | 15 | 0 | Wati-Project daily_report | 21:30 IST funnel report | - |
| `gorefer_prospect_day14_en_v2` | APPROVED | MARK | en | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day14_en_v3` | APPROVED | UTIL | en | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day14_hi_v2` | APPROVED | MARK | hi | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day14_hi_v3` | APPROVED | UTIL | hi | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day3_en_v2` | APPROVED | MARK | en | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day3_en_v3` | APPROVED | UTIL | en | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day3_hi_v2` | APPROVED | MARK | hi | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day3_hi_v3` | APPROVED | UTIL | hi | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day7_en_v2` | APPROVED | UTIL | en | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_prospect_day7_hi_v2` | APPROVED | UTIL | hi | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_referrer_day10_en_v2` | APPROVED | MARK | en | 2 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_referrer_day10_hi_v2` | APPROVED | MARK | hi | 2 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_referrer_day3_en_v2` | APPROVED | MARK | en | 2 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_referrer_day3_hi_v2` | APPROVED | MARK | hi | 2 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_zerodha_prospect_day1_en` | APPROVED | MARK | en | 1 | 1 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_zerodha_prospect_day1_hi` | APPROVED | UTIL | hi | 1 | 1 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_zerodha_reopen_en` | APPROVED | UTIL | en | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_zerodha_reopen_hi` | APPROVED | UTIL | hi | 1 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_zerodha_welcome_en` | APPROVED | UTIL | en | 2 | 2 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_zerodha_welcome_hi` | APPROVED | UTIL | hi | 2 | 2 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gr_brokers_zerodha_prospect_welcome_en_2026_07_17` | APPROVED | MARK | en | 3 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v3` | APPROVED | MARK | en | 3 | 2 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gr_brokers_zerodha_prospect_welcome_hi_2026_07_17` | APPROVED | MARK | hi | 3 | 0 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gr_brokers_zerodha_prospect_welcome_hi_2026_07_17_v3` | APPROVED | MARK | hi | 3 | 2 | Zoho/Wati journey *(inferred - verify)* | Lifecycle nudge | - |
| `gorefer_referrer_prospect_pending_en_2026_07_25` | PENDING | MARK | en | 3 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gorefer_referrer_prospect_pending_en_2026_07_25_v2` | APPROVED | MARK | en | 3 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gorefer_referrer_prospect_pending_hi_2026_07_25` | APPROVED | MARK | hi | 3 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gorefer_referrer_prospect_pending_hi_2026_07_25_v2` | APPROVED | MARK | hi | 3 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gr_brokers_zerodha_office_lead_alert_en_2026_07_17` | APPROVED | MARK | en | 4 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gr_brokers_zerodha_referrer_thankyou_en_2026_07_17` | APPROVED | MARK | en | 2 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gr_brokers_zerodha_referrer_thankyou_hi_2026_07_17` | APPROVED | MARK | hi | 2 | 0 | **UNWIRED / superseded** | not sent by any known path | - |
| `gr_brokers_zerodha_referrer_update_en_2026_07_19_v2` | APPROVED | UTIL | en | 2 | 1 | **UNWIRED / superseded** | not sent by any known path | - |
| `gr_brokers_zerodha_referrer_update_hin_2026_07_19_v2` | APPROVED | UTIL | hi | 2 | 1 | **UNWIRED / superseded** | not sent by any known path | - |

**Totals:** 46 live templates - Zoho/Wati journey *(inferred - verify)*: 24; **UNWIRED / superseded**: 9; GoRefer code: 8; Wati broadcast: 3; Wati-Project daily_report: 2

## Findings from the 2026-07-26 reconciliation

1. **FIXED (was P0).** Prod `otp_whatsapp_template` was `gorefer_login_otp` — a name that has
   **never existed** at Meta in any status. Live probe returned **HTTP 400 / `accepted=False`**, so
   every WhatsApp login OTP failed and silently cascaded to the `manual` channel while
   `ENABLE_OTP_LOGIN` read ON. The adapter's correct hardcoded default
   (`gr_platform_gorefer_login_otp_en_2026_07_21`) was bypassed because the bad config value was
   truthy. Corrected in the config cascade and verified `accepted=True` with a live send.
2. **9 templates are approved but unwired**, including both `prospect_welcome_*_v3` and both
   `referrer_update_*_v2`. Each is a Meta-approved asset nobody sends — decide: wire, or delete.
3. **`prospect_welcome` v2 is UTILITY, v3 is MARKETING.** Bumping to v3 would push a must-arrive
   transactional welcome into the capped bucket. Do not treat that bump as routine.
4. **`gorefer_referrer_prospect_pending_en_2026_07_25` (v1) is the account's only PENDING template**
   and is superseded by v2/v3. Withdraw/delete it.
5. **The Hindi office alert points at the older English template.** `notify_template_office_hi` has
   no override, so it falls back to `..._en_2026_07_17` while EN resolves to `..._en_2026_07_19`.
   Harmless today (office sends use EN) but it is latent drift.
6. **24 of 46 templates are owned outside GoRefer.** A GoRefer-only E2E run can never cover them;
   covering "all templates in all scenarios" requires driving the Zoho journeys and Wati flows too.
