# Wati templates GoRefer uses

> The WhatsApp templates GoRefer's own notification path sends, their Meta status/category, and the
> role→template config mapping. **Only GoRefer's templates are listed here** — the full account-wide
> catalogue (including Zoho's `zoho_auto_*` sending templates) lives in
> `C:\Abhay\5Wealths\Wati-Project\docs\wati-templates.json`.
>
> Wati acct `105355`. Verified against the live account 2026-07-19.

---

## 1. Role → template mapping (the live config defaults)

Source of truth in code: `NOTIFY_TEMPLATE_DEFAULTS` in `apps/config/preferences.py`. Every one of
these is **overridable per tenant on the Settings screen with no deploy**.

| Role | Lang | Template (`elementName`) | Editable on Settings as |
|---|---|---|---|
| office | en | `gr_brokers_zerodha_office_lead_alert_en_2026_07_17` | Office / Ashok alert (English) |
| office | hi | *(maps to the en name — no Hindi variant)* | — |
| prospect | en | `gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v2` | Prospect welcome (English) |
| prospect | hi | `gr_brokers_zerodha_prospect_welcome_hi_2026_07_17_v2` | Prospect welcome (Hindi) |
| referrer | en | `gr_brokers_zerodha_referrer_thankyou_en_2026_07_17` | Referrer thank-you (English) |
| referrer | hi | `gr_brokers_zerodha_referrer_thankyou_hi_2026_07_17` | Referrer thank-you (Hindi) |

Resolution: `notify_template_name(role, lang=…)` → cascade (tenant override → central default).
Unknown language falls back to English; an unknown **role raises** (a new role must register a
default rather than silently resolving to something wrong).

**Login OTP (M13, separate from the role map):** the referrer-login OTP template name resolves
via `OTP_WHATSAPP_TEMPLATE` (settings/env default → per-tenant Preferences override), default
**`gr_platform_gorefer_login_otp_en_2026_07_21`** (AUTHENTICATION, copy-code button). Staged in
`apps/integrations/wati/wati-templates.json` on **HOLD — drafted, NOT yet submitted to Meta**;
submission happens only on Abhay's explicit review-go (M13 owner decision 2026-07-21). Until it is
APPROVED, `ENABLE_OTP_LOGIN` must stay off in prod (the send would fail template-not-found).

---

## 2. The approved `gr_*` templates in the Wati account

| elementName | Lang | Category | Status | `waTemplateId` |
|---|---|---|---|---|
| `gr_brokers_zerodha_office_lead_alert_en_2026_07_17` | en | ⚠️ **MARKETING** | APPROVED | `2085330198687561` |
| `gr_brokers_zerodha_prospect_welcome_en_2026_07_17` | en | ⚠️ **MARKETING** | APPROVED | `1403403211837882` |
| `gr_brokers_zerodha_prospect_welcome_hi_2026_07_17` | hi | ⚠️ **MARKETING** | APPROVED | `1080468977988332` |
| `gr_brokers_zerodha_referrer_thankyou_en_2026_07_17` | en | ⚠️ **MARKETING** | APPROVED | `1046549474582913` |
| `gr_brokers_zerodha_referrer_thankyou_hi_2026_07_17` | hi | ⚠️ **MARKETING** | APPROVED | `2132802414252307` |
| **`gr_brokers_zerodha_prospect_welcome_en_2026_07_17_v2`** | en | ✅ UTILITY | APPROVED | `1711546776760651` |
| **`gr_brokers_zerodha_prospect_welcome_hi_2026_07_17_v2`** | hi | ✅ UTILITY | APPROVED | `1956926981638623` |
| `gr_brokers_zerodha_office_lead_alert_en_2026_07_19` | en | ✅ UTILITY | APPROVED | `1049428880884247` |
| `gr_brokers_zerodha_referrer_update_en_2026_07_19` | en | ✅ UTILITY | APPROVED | `1367694621989458` |
| `gr_brokers_zerodha_referrer_update_hin_2026_07_19` | hi | ✅ UTILITY | APPROVED | `1282268567125664` |

### 2.1 The MARKETING reclassification — why `_v2` exists

The original 2026-07-17 five were submitted as **UTILITY** but **Meta reclassified them to
MARKETING**. That matters operationally, not cosmetically:

- MARKETING is subject to Meta's **per-user marketing cap (error 131049)** — the single largest
  failure mode on this account.
- A **welcome message must arrive**. Sending a must-arrive lifecycle message on a capped
  MARKETING template is the wrong trade.

So the prospect-welcome pair was **re-cut as `_v2` with the promotional phrasing removed**, and
those re-submissions **hold UTILITY**. The code therefore points prospect/en + prospect/hi at the
`_v2` names (see §1). The office alert was likewise re-cut under a fresh `_2026_07_19` name as
UTILITY.

⚠️ **Still on MARKETING and still wired in §1:** the two **referrer thank-you** templates. They are
lower-stakes than a welcome (a missed thank-you doesn't break the funnel) but they remain exposed to
131049. The UTILITY `referrer_update_*_2026_07_19` pair exists and is approved — **swapping the
referrer role onto it is a one-field Settings change, no deploy.** Worth doing.

### 2.2 Naming convention

`gr_<partnerGroup>_<partner>_<purpose>_<lang>_<YYYY_MM_DD>` — the language segment (`en` / `hi`,
occasionally `hin`) is mandatory immediately before the date. Older `gorefer_zerodha_*` names are
grandfathered. Authoring standards: the `wati-template-design-best-practices` skill; submission +
approval tracking: `wati-template-create-and-track`.

---

## 3. Parameter contract

Callers build **semantic** named params; the adapter remaps them to Wati's **positional** `"1"`,
`"2"`, `"3"` by order at the API boundary (see the contract doc §2). The three-variable shape used
by the lead-capture family, with fallbacks so a missing value never renders blank:

| Position | Meaning | Fallback |
|---|---|---|
| 1 | prospect / recipient name | — |
| 2 | referrer name | `"not on file"` |
| 3 | referral client id | — |

Email, where used, falls back to `"not provided"`. The resolved params are snapshotted onto
`Notification.template_params` at create time, so a later customer-record edit cannot retroactively
change what was actually sent. That field holds PII (name/email) — it is part of the **erasable**
operational record, deliberately not the immutable event log.

---

## 4. Related

- Send/verify mechanics: [`Wati-Integration-Contract.md`](./Wati-Integration-Contract.md)
- Full account catalogue + approval history: `Wati-Project/docs/wati-templates.json`,
  `Wati-Project/docs/wati-shared-template-category-rules.md`
- Delivery health (52.29% and the 131049 story): `Wati-Project/docs/`
