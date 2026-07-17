# WATI Template Naming Convention (AUTHORITATIVE)

> **Locked by Abhay, 2026-07-17.** GoRefer is multi-partner across multiple partner groups, so
> template names must sort and filter by group → partner → purpose. Every **newly created** template
> follows this. Read `WATI-TEMPLATE-CREATION-RULE.md` for the whole-flow checklist; this file is only
> the naming rule.

---

## Format

```
gr_<partnerGroup>_<partner>_<purpose>_<lang>_<YYYY_MM_DD>
```

| Segment | Meaning | Rules | Examples |
|---|---|---|---|
| `gr` | GoRefer — fixed prefix | literal `gr` | `gr` |
| `<partnerGroup>` | The partner's category | one lowercase token | `brokers` · (future: `insurance`, `mutualfunds`, `loans`, `properties`) |
| `<partner>` | The specific company | **one lowercase token, no internal `_`** | `zerodha` · `angelone` · `groww` |
| `<purpose>` | What the template is for | short, `_`-joined words | `office_new_lead` · `prospect_welcome` · `referrer_used` · `refer_earn` |
| `<lang>` | Language — **MANDATORY**, just before the date | **always present**: `en` (English) or `hin` (Hindi). Never omitted — even the default English template carries `en`. | `en` · `hin` |
| `<YYYY_MM_DD>` | Creation date | always **last** | `2026_07_17` |

**Meta constraints honoured:** names are lowercase letters + digits + underscore only, and well under
Meta's 512-char limit. All segments are `_`-separated; because `<partner>` is a single token
(`angelone`, not `angel_one`), the name splits cleanly into fixed positions.

## Decisions (2026-07-17)
- **Language is MANDATORY and sits just before the date**: `en` or `hin` — **always present, even for
  the default English template.** Codes are `en` / `hin`. (Position finalised 2026-07-17: language is the
  segment immediately before the date, not the 2nd level.)
- **Partner token:** single token, no internal underscore — `angelone`, NOT `angel_one` — so parsing
  the 6 segments on `_` is unambiguous.
- **Existing templates are NOT renamed.** The already-approved `gorefer_zerodha_eng_2026_07_10_v2`,
  `gorefer_zerodha_hin_2026_07_10_v2`, `gorefer_zerodha_eng_leads_2026_07_10` (Refer & Earn family) keep
  their old names — renaming would mean fresh Meta submissions + re-approval + code/reference updates
  for no functional gain. The new convention applies to **newly created** templates only.

## Worked examples

**The 3 lead-capture templates (Zerodha):**
```
gr_brokers_zerodha_office_new_lead_en_2026_07_17       (English, internal)
gr_brokers_zerodha_prospect_welcome_en_2026_07_17      (English)
gr_brokers_zerodha_prospect_welcome_hin_2026_07_17     (Hindi)
gr_brokers_zerodha_referrer_used_en_2026_07_17         (English)
gr_brokers_zerodha_referrer_used_hin_2026_07_17        (Hindi)
```

**Same purpose, a future partner (Angel One):**
```
gr_brokers_angelone_prospect_welcome_en_2026_07_17
gr_brokers_angelone_prospect_welcome_hin_2026_07_17
```
Group + partner cluster together under `gr_brokers_*`, and each purpose has its `_en_`/`_hin_` pair
right before the date.

**A future non-broker group (illustrative):**
```
gr_insurance_someinsurer_prospect_welcome_en_2026_08_01
```

## Versioning
- A body/button change = a **new template** (Meta won't let you edit an approved one in place). Bump by
  using a **later date** in the name (preferred over `_v2`, since the convention already carries the
  date). If two versions land the same day, append `_v2` before the date — e.g.
  `gr_brokers_zerodha_prospect_welcome_en_2026_07_17` → a same-day rebuild becomes
  `gr_brokers_zerodha_prospect_welcome_en_v2_2026_07_17`.
- **Never hardcode these names in code.** They live in config (a `ReferralProgram` field / a
  `rule_template_map` keyed by partner + role + language) and are read at send time, so a version bump
  or a new partner never needs a code deploy.

## Change log
- **2026-07-17** — Convention created (Abhay). Initial form `gr_<group>_<partner>_<purpose>_[lang]_<date>`.
- **2026-07-17 (rev 2)** — Abhay: **language is MANDATORY** (always present, even English), and its
  **final position is just before the date**. Final form:
  `gr_<partnerGroup>_<partner>_<purpose>_<lang>_<YYYY_MM_DD>` (e.g.
  `gr_brokers_zerodha_prospect_welcome_en_2026_07_17`). Partner = single token; existing `gorefer_zerodha_*`
  grandfathered.
