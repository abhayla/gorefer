# GoRefer — Referral UX + Disclosure Architecture (design decisions log)

> **Status:** DESIGN / BACKLOG — captured live with Abhay 2026-07-09. Not all built yet; this is the authoritative record of decisions so no discussion is lost or repeated. Each item marked with a build status. Feeds the Category→Partner→Sub-broker architecture ([[gorefer-architecture-layers]]) and the config cascade (ADR-022).
>
> **Standing rule (Abhay, reinforced 2026-07-09):** capture EVERY design discussion we have into a durable doc + memory, so we learn from it and never skip or re-litigate a settled point. This file is one of those homes.

---

## 1. Referrer bot menu — 3 branches (TO BUILD)

When a referrer sends a referral keyword ("Refer", "get referral message"), the bot presents a **menu (3 quick-reply buttons)** — "How would you like to refer? 👇" — then branches:

1. **📲 Share on WhatsApp** — sends the two messages already built + tested (the forwardable kit + the forward-nudge). LIVE (flow "Referral Message", flowId `647621212b07d108a6686470`).
2. **🔗 Get my link** — replies with `gorefer.in/r/{{client_id}}?s=wa` + "add a personal note when you share." The personal-note nudge is mandatory (Zerodha T&C cl.8.viii — no context-free link spam). EASY.
3. **🤝 Refer directly (we'll assist)** — the assisted-referral branch (§2). REAL BUILD.

**WhatsApp button constraint:** Meta allows *either* up to 3 quick-reply buttons *or* a single CTA-URL — you can't mix them. So all 3 are quick-reply buttons; the "link" branch *sends* the link as a (tappable) message rather than using a URL button.

## 2. Assisted-referral branch (TO BUILD — needs Zoho wiring)

If the referrer picks "Refer directly," the bot captures the prospect's **Name + Mobile** (Email optional), creates a **lead in Zoho** (Ashok's follow-up queue), and confirms "we'll reach out to help them open the account."
- **Consent guardrail (DPDP):** it's a third party's PII → frame as "with their permission, share their name & number"; Ashok obtains + logs the prospect's consent on first contact. **Never collect a password** — name/mobile/email only.
- **Architecture:** the Wati flow posts captured details to **GoRefer's webhook** → GoRefer creates the Zoho lead (same pipeline as the landing-page form, behind `ENABLE_ZOHO_WRITE`). One lead pipeline, not two.
- **Why it was dropped from the rebuild originally:** the old multi-broker flow's "share your friend's details → we contact them" had a DPDP/consent gap and weaker Zerodha mapping than prospect self-signup. The assisted branch re-adds it *with* the consent guardrail; "forward the link" stays the primary CTA.

## 3. `LANDING_MODE` — per-user landing-page bypass (TO SPEC → Engineer)

A **per-tenant (sub-broker) config flag** `LANDING_MODE = page | direct`:
- `page` (default): `/r/{client_id}` renders the PIFS landing page (form + "Continue to Zerodha") — captures the lead + hosts disclosures.
- `direct`: `/r/{client_id}` **logs the click server-side (on-commit), then 302s straight to** `signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}` — frictionless, skips the page. Guardrails unchanged (`?s` stripped, code server-side, no partner code in any client-facing body).
- Fits the config cascade (central default → per-sub-broker override) + the multi-tenant model: some sub-brokers bypass, some show. All tracking value preserved either way.

**Two coupled consequences of `direct` (decisions, not just display):**
- **(a) Lead-capture loss:** direct mode yields a click, not a contact — no name for Ashok. Fine for frictionless conversion; a loss for assisted follow-up.
- **(b) Disclosure relocation (compliance):** the light WhatsApp message relies on §4.4 (full disclosure lives on a linked page). If the landing page is bypassed, that host disappears — UNLESS the per-user disclosure page (§4) exists. **Resolution:** with the disclosure page in place, the message always links to `/d/{id}`, so `direct` mode no longer forces full-inline disclosure. Wire `LANDING_MODE` + message-disclosure-level together so no one gets a bypass link + a light message with no disclosure host.

## 4. Per-user Disclosure Page (NEW — Abhay 2026-07-09) (TO SPEC)

Each GoRefer user (sub-broker/tenant) has a **dedicated disclosure page** — e.g. `gorefer.in/d/{client_id}` — separate from their profile/preference page.
- **Multi-partner aggregation:** the page composes the mandated disclosure block for EVERY partner the user is associated with, in a defined sequence. A Zerodha AP who also does insurance + loans → Zerodha (SEBI/NSE) block, then Insurance (IRDAI) block, then Loans (RBI) block. Each partner in the taxonomy carries its regulator-mandated disclosure template; the page renders the blocks for that user's active partnerships, filled with the user's own values (AP code, ARN, DSA code, etc.).
- **Config-driven:** add a partner → add its disclosure template; add a user's partnership → their page composes it. No code change per user.
- **It is the canonical §4.4 host** — every message/creative/link points here for full disclosures. This makes the light WhatsApp message + the `direct` bypass mode both compliant without inlining the full block. **Elegant fix for the §3(b) coupling.**
- **Distinct from** the profile/preference page (that's the user's settings/stats surface; the disclosure page is public compliance). Both are per-user; different purpose, different route.
- **Consistency with tenancy:** each NSE-broker is its own isolated login/tenant (≤1 broker + any non-NSE partners) — so a tenant's disclosure page reflects exactly that tenant's partner set ([[gorefer-architecture-layers]]).
- **Currency:** if a registration lapses (e.g. insurance), its block drops off; values pulled from the tenant's config so they stay accurate.

## 5. §4.4 disclosure determination (SETTLED — 2026-07-09)

A referrer's forwarded WhatsApp message does NOT need the full SEBI/NSE AP identification block inline, PROVIDED a linked page (landing page and/or the per-user disclosure page) carries the full prescribed disclosures (NSE/COMP/55482 §4.4). The message keeps a short footer: brokerage-limit line (§4.8, when rates are quoted) + verbatim market-risk warning (§4.2). Grounding: Zerodha Client Referral T&C (`zerodha.com/tos/referrals`) + NSE §4.4. Full write-up: `C:\Abhay\5Wealths\Wati-Project\wati-automation-inventory.md` §5d. Remaining external gate: PIFS-authored creative on the AP code needs Zerodha written approval before scaling (T&C cl.8.vii + NSE §3.2).

## 6. Open couplings to enforce in the build
- `LANDING_MODE=direct` ⇒ message-disclosure link must point at a live `/d/{id}` (or carry full inline). Never a bypass link with no disclosure host.
- The disclosure page must exist before `direct` mode or the light message is compliant on their own.
- Assisted branch ⇒ consent captured + logged; no password ever.

---

# BUILDABLE SPEC (QUEUED — build on a new branch AFTER the current sprint is in production, per Abhay's standing rule)

## 8. Config keys (config cascade, ADR-022; per-tenant unless noted)
| Key | Values | Default | Scope | Notes |
|---|---|---|---|---|
| `LANDING_MODE` | `page` \| `direct` | `page` | tenant (sub-broker) | `direct` = log click then 302 straight to Zerodha, skip landing page. |
| `REFERRER_MENU_ENABLED` | bool | `true` | tenant | show the 3-branch menu on a referral keyword vs. send the kit directly. |
| `ENABLE_ASSISTED_REFERRAL` | bool | `false` | tenant | Branch 3 (capture prospect → Zoho lead). Gated with `ENABLE_ZOHO_WRITE`. |
| `DISCLOSURE_PAGE_ENABLED` | bool | `true` | tenant | expose `/d/{id}`. |
| `MESSAGE_DISCLOSURE_LEVEL` | `light` \| `full` | derived | tenant | **derived, not free-set**: `full` if no live `/d/{id}` and `LANDING_MODE=direct`; else `light`. Enforces the §3(b) coupling. |

Partner-level (taxonomy) config: each `ReferralProgram`/partner carries a `disclosure_template` (regulator block with `{placeholders}` for the user's values) + `regulator` label. Per-tenant partnership rows carry the user's values (AP code, ARN, DSA code…) + `status` (active/lapsed).

## 9. Routes
- **`GET /r/{client_id}`** (existing) — record click on-commit → branch on `LANDING_MODE`: `page` → render landing (today); `direct` → 302 to `signup.zerodha.com/api/lead/?c=ZMPHZC&r={client_id}` (strip `?s`, code server-side).
- **`GET /d/{client_id}`** (NEW) — public per-user disclosure page; composes each active partner's `disclosure_template` filled with the tenant's values, in a fixed sequence (regulator order: SEBI/NSE → IRDAI → RBI → …). Crawler-safe; no PII.
- **`POST /api/wati/webhook`** (existing, WM-B) — assisted branch posts captured `{name, mobile, email?, referrer client_id}` → create Zoho lead (behind `ENABLE_ZOHO_WRITE`), dedup, consent flag.

## 10. Data-model deltas (indicative; Engineer finalizes)
- `Partner`/`ReferralProgram`: + `disclosure_template` (text w/ placeholders), + `regulator` (enum), + `disclosure_sequence` (int).
- `TenantPartnership` (tenant × partner): the user's per-partner values (JSON: ap_code/arn/dsa…), + `status` (active/lapsed), + `values_verified_at`.
- `TenantConfig`: `landing_mode`, `referrer_menu_enabled`, `enable_assisted_referral`, `disclosure_page_enabled`.
- `Lead`: assisted-source rows carry `source=whatsapp_assisted`, `consent_status`, `consent_captured_at`.
- All tenant-scoped (single-schema `tenant_id`, ADR-023).

## 11. Acceptance criteria (guardrail tests)
- **Disclosure page:** `/d/{id}` renders every active partner's verbatim block in regulator sequence with the tenant's own values; lapsed partner's block absent; no PII; crawler-excluded from human counts; no `ZMPHZC`/raw Zerodha URL leak.
- **LANDING_MODE:** `direct` → click row written on-commit + 302 `Location` is exactly `…/api/lead/?c=ZMPHZC&r={id}` (no `?s`); `page` → unchanged. Test both.
- **Coupling:** with `LANDING_MODE=direct` AND no live `/d/{id}`, the message MUST be `full`-disclosure — assert config refuses a `direct`+`light`+no-`/d/` combination.
- **Referrer menu:** referral keyword → 3 quick-reply buttons; each branch fires; "Get my link" reply includes the personal-note nudge (cl.8.viii).
- **Assisted branch:** captured name+mobile → one Zoho lead (deduped), `consent_status` set; never stores a password; behind `ENABLE_ZOHO_WRITE` (log-only in demo).
- Postgres-only; demo works offline; config-over-code (no inline copy/disclosure literals).

## 12. ADRs to record (`docs/architecture/02`)
- **ADR-031** — Per-user Disclosure Page (`/d/{id}`) as the canonical §4.4 host; multi-partner composition from per-partner templates + per-tenant values, regulator-ordered; distinct from the profile/preference surface.
- **ADR-032** — `LANDING_MODE` per-tenant landing bypass; click logged server-side then 302; message-disclosure level derived and coupled to a live disclosure host (no bypass-without-disclosure gap).
- **ADR-033** — Referrer 3-branch WhatsApp menu (Share on WhatsApp / Get my link / Refer directly); assisted branch captures prospect → Zoho lead via the Wati→GoRefer webhook with a DPDP consent guardrail; never a password.

## 13. Mission split (QUEUED — do NOT start until current sprint in prod + new branch)
- **Q-M-DISC** — `/d/{client_id}` disclosure page + partner disclosure templates + per-tenant values + regulator sequencing. (Foundational — unblocks the coupling.)
- **Q-M-LAND** — `LANDING_MODE` per-tenant flag + the `/r/` branch + the derived `MESSAGE_DISCLOSURE_LEVEL` coupling. Depends on Q-M-DISC.
- **Q-M-MENU** — referrer 3-branch menu (Wati flow: menu node + 3 branches; branches 1–2 send-message; wiring for branch 3).
- **Q-M-ASSIST** — assisted-referral capture (Wati capture steps) → `POST /api/wati/webhook` → Zoho lead + consent flag. Depends on Q-M-MENU + `ENABLE_ZOHO_WRITE`.

## 14. Preferences / Settings screen (APPROVED 2026-07-09 → BUILD as Q-M-PREF)

**Design APPROVED by Abhay 2026-07-09.** Visual truth: `mockups/preferences-screen-mockup.html` (Variant C · Cobalt). This is the UI home for per-tenant config — critically, `LANDING_MODE` is set HERE (through the screen), not via a backend override. Admin-only in Sprint 1; becomes the sub-broker's self-serve settings when `ENABLE_CUSTOMER_LOGIN` lands.

**Route:** `GET/POST /admin-panel/preferences` (admin, tenant-scoped). Server-rendered Django + HTMX, matches the approved mockup.

**Controls → config keys (all USER/tenant tier of the ADR-022 cascade; save persists to the tenant config):**
- **Landing mode** (segmented: Show landing page ↔ Direct to Zerodha) → `LANDING_MODE = page|direct`. **Compliance guard:** selecting `direct` is only allowed when a live `/d/{slug}` exists for the tenant (else the UI blocks it / forces `page`) — the ADR-032 coupling, enforced at the screen, not just the backend.
- **Show referrer reward** (toggle) → `SHARE_SHOW_REWARD`; **Reward claim text** (input) → `REFERRER_REWARD_CLAIM`.
- **Helpline** (input) → helpline number; **WhatsApp Business number** (input) → the `wa.me` deep-link number.
- **Enabled share channels** (chips) → the channel allow-list (`?s`/path channels).
- **Allow "Refer directly" (assisted)** (toggle) → `ENABLE_ASSISTED_REFERRAL`.
- **Disclosure:** read-only link to the tenant's `/d/{slug}`; **Active partnerships** list (Zerodha · SEBI/NSE now) with **+ Add partnership** → manages the `TenantPartnership` rows that drive `/d/{slug}` composition (add/activate/deactivate a partner).

**Acceptance (guardrail tests):**
- Flipping **Landing mode → Direct via the screen** persists `LANDING_MODE=direct` for the tenant AND live `/r/wa/{id}` then 302s straight to Zerodha (click still recorded, Location clean) — the exact "direct via the preference screen, not the backend" requirement.
- `direct` is **refused in the UI** when the tenant has no live `/d/{slug}` (coupling enforced at the screen).
- Each control persists + takes effect; admin-only (auth-gated); tenant-scoped (no cross-tenant leakage); config-over-code (no inline literals); Postgres-only; demo works offline.
- Adding a partnership makes its block appear on `/d/{slug}`; deactivating removes it.

**ADR-034** — Preferences screen as the UI surface for the user-tier config cascade; `LANDING_MODE` (and the ADR-032 disclosure coupling) is set here, admin-only in Sprint 1, self-serve post customer-login.

## 7. Related records (so nothing is siloed)
- Architecture spine + tenancy + rule cascades: memory [[gorefer-architecture-layers]]; diagram `docs/architecture/gorefer-layered-architecture-diagram.html`.
- Wati automation model + live inventory + the referral rebuild before/after: `Wati-Project/wati-automation-inventory.md`.
- Config cascade: [[gorefer-config-hierarchy]] (ADR-022). Deploy target: [[gorefer-deploy-target]].
- WhatsApp/Wati referral spec: `S2-02`. This doc extends it.
