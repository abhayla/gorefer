# GoRefer Sprint 2 — Referral Share Amplification & Customer Portal (Zerodha)

> **⚠ SCOPE UPDATE (2026-07-08): Sprint 2 is now WhatsApp-only** — see **`S2-02-WhatsApp-Wati-Referral-Amplification-Spec.md`**. The multi-platform launcher, web customer-portal, Google login, and poster in THIS doc are **deferred to Sprint 3** (not discarded). The OG preview page (M11) and the config/compliance/attribution principles below still apply.

> **Owner:** Abhay Kumar Maurya / PIFS (Zerodha Authorised Person). **Compiled:** 2026-07-08. **Status:** APPROVED for build (spec-at-a-glance signed off by Abhay 2026-07-08 via an 8-question grill-me; QR dropped per that sign-off).
> **Grounding:** builds on Sprint 1 (M1–M10, merged). Spec is authoritative; when in doubt, STOP and ask via `COORDINATION.md`. Visual truth = `mockups/` (Variant C · Cobalt Clean-Fintech).

---

## 1. Purpose & scope

Enable referrers (PIFS's Zerodha clients) to **share their referral link across social media and messaging with ready, compliant creatives**, track every share **by platform**, and give referrers a **self-serve login** to their own referral view + a share tool. Zerodha only; architecture stays provider-agnostic and multi-tenant-ready.

**Not** a paid-ads tool. **Not** a new referral program — it rides the existing `c=ZMPHZC` + `r={client_id}` link and Zerodha's client referral scheme.

---

## 2. Actors

- **Referrer** — a PIFS Zerodha client (e.g. RJ4111) who shares their link. New self-serve login persona.
- **Prospect / new user** — the person who clicks and opens a Zerodha account.
- **Admin** — Abhay / Ashok. Full visibility + verification fallback.

---

## 3. Two-sided message model (LOCKED — decision Q1)

Two distinct audiences, two distinct value props:

- **Partner → referrer** (private, 1:1, e.g. WhatsApp): sells the **referrer's** benefit — "earn 10% brokerage share + 300 reward points." Private 1:1 is outside advertising scope (per the compliance skill). NOT part of the public share creatives.
- **Referrer → prospect** (public share creative): sells the **prospect's** benefit — the Zerodha product terms:
  - ₹0 account opening
  - ₹0 equity-delivery brokerage
  - 1st-year AMC free (accounts opened from 1 Jun 2026; time-bound → config)
  - ₹20 flat intraday & F&O · free Kite app
  - Direct mutual funds on Coin
  - Headline: **"Open a free Zerodha account"** (NO "with PIFS" in the hook; PIFS named only in the mandatory disclosure).
  - **No reward-to-user claim** (Zerodha gives the referred user no referral bonus; only the referrer earns points) → also keeps it clear of NSE §5.5 (no advertised incentive-for-account-opening).

Reward wording is a **single config toggle** (`SHARE_SHOW_REWARD`, default off) with a service-only and a with-reward variant, so if Zerodha approves reward wording it flips without a code change.

---

## 4. Compliance — the hard gate (LOCKED — decision Q2)

A public share carrying `c=ZMPHZC` is a **PIFS advertisement** (audience = broadcast, not 1:1). Therefore:

- **Zerodha's written approval is required before any creative goes live** (NSE/COMP/55482 §3.2 — an AP cannot self-approve; Zerodha T&C cl.8.vii). External dependency — see §16.
- **Disclosure + market-risk warning baked into every creative**, un-removable (§4.1/§4.2). Byte-exact canonical strings (same as Sprint 1 `AP_DISCLOSURE_BLOCK` / `MARKET_RISK_WARNING`). Tight formats (e.g. a tweet) may use a "Disclosures & registration ↗" link (§4.4).
- **No paid boosting / sponsored ads** of the link on any platform (Zerodha T&C cl.15 — leads from paid promo are terminated).
- **No context-free link spam** (T&C cl.8.viii) — the launcher requires/encourages a personal message, never a bare link.
- No superlatives (§5.1), no NSE/Zerodha logo, no assured returns (§5.10), no MCX, no celebrity, no real-person photo (avoids Annexure-C).
- Every creative + any change runs through the `zerodha-ap-social-media-compliance` skill before publish.

**Nothing in Sprint 2 publishes to a public channel until the creative set has passed the skill AND Zerodha approval.** The software can be fully built and demoed behind this gate.

---

## 5. Surfaces & routes

### 5.1 Referral Profile — ONE layout, role-scoped (LOCKED — decision Q3/Q6)
- `/admin-panel/referrer/{client_id}` (admin) and `/my/referrals` (referrer) render the **same template**.
- **Admin role:** look up any referrer; full detail; all PII; admin chrome (search, nav).
- **Referrer role:** locked to own record; **`PII_MASK_FOR_CUSTOMER_VIEW` on** (city not raw IP, no other people's names/contact); admin chrome hidden; a prominent **"Share / Invite"** button.
- Difference is pure config (role → masking + action visibility), not a second screen.

### 5.2 Share Launcher (LOCKED — decision Q3/Q6) — `/my/referrals/share`
- Opened from the Profile's "Share / Invite" button. **Message-customization + share only** — NO stats (stats live on the Profile).
- Contains: their link (copy), the **8-template picker** with live preview, an **editable message/caption**, the **share row**, and a **"how to share" compliance note** (organic only, add context, no paid boosting).

### 5.3 OG share/preview page (LOCKED — decision, Phase 1) — the `/r/{client_id}` destination for crawlers
- Serves **Open Graph + Twitter Card** meta (title/description/image) so Facebook/LinkedIn/X/WhatsApp render a proper, compliant preview card.
- **Preview crawlers** (facebookexternalhit, LinkedInBot, Twitterbot, WhatsApp, Telegrambot, Slackbot) get the card but are **excluded from human-click counts** (extends the Sprint-1 bot filter). A crawler fetch never creates a journey/redirect.

### 5.4 Customer login — `/login` (Google) + binding (see §8).

---

## 6. Creative templates (LOCKED — decision Q4) — 8, fully config-driven

The 8 approved designs (see `mockups/share-creatives-shortlist.html`): Bold Hero, Assisted, 3-Step, Benefit List, Story, WhatsApp-first, Ultra-minimal Text, App-style Teaser.

**Everything is data, not baked art** (`CreativeTemplate` config): headline, the 5 benefit lines, CTA text, disclosure/risk block ref, brand mark (GoRefer default; PIFS/none switchable), accent colors, format (link-card / IG square / story / text), and an on/off flag. Editable from config now; an admin "Creative Templates" screen later (small scope call). No code edit to change copy.

---

## 7. Attribution (LOCKED — decision Q5)

- Each share button appends `?s={platform}` to the link (`s` ∈ fb, x, li, wa, tg, ig, email, copy; manual → other). Param name is config.
- The `/r/{client_id}` view **records `s` as the click's share-channel** (reuses the Sprint-1 Channel column), then **strips it before the 302 to Zerodha** (never leaks; destination stays clean).
- Optionally log a **ShareEvent** when the referrer taps a share button (referrer, platform, template, timestamp) → powers "shares vs clicks" per platform.
- Analytics: a **clicks/leads-by-platform** breakdown per referrer on the (admin) Profile.

---

## 8. Customer login & client-ID binding (LOCKED — decision Q8)

- **Google OAuth** sign-in (flips `ENABLE_CUSTOMER_LOGIN=true`; adds Google as the first provider — more later).
- First login: referrer enters **Zerodha Client ID + registered mobile**.
- **Auto-verify:** if the **Google email OR the entered mobile** matches the Zoho record for that Client ID → bind instantly (both normalized; phone one canonical way per CLAUDE.md).
- **Mismatch:** no auto-bind → a **"pending verification"** state; request goes to an **admin queue** where Ashok sees entered-vs-on-file email/mobile and Approves & links (or rejects). Anti-impersonation gate; needs no Zerodha API.
- No Zerodha password ever handled. Mobile-OTP self-serve = deferred (DF-6).
- Flow visual: `mockups/customer-login-flow-mockup.html`.

---

## 9. Data model additions (indicative — Engineer finalizes)

- `CustomerUser` (google_sub, email, name) ↔ `Referrer`/`client_id` binding, with `verify_status` (verified / pending / rejected) + `verify_method` (email / mobile / admin).
- `ShareEvent` (referrer, platform, template_id, ts) — append-only, PII-free (fits the event-log rule).
- `Click.share_channel` — already exists (Sprint 1 Channel); populated from `?s=`.
- `CreativeTemplate` config (data, not a hardcoded set).
- All tenant-scoped; no schema-per-tenant (ADR-023 single-schema tenant_id holds).

---

## 10. Phase plan

0. **Compliant creative + Zerodha approval** (BLOCKING, external) — finalize the 8 via the compliance skill; submit for Zerodha sign-off.
1. **OG preview page + crawler-not-a-click** (§5.3).
2. **Share launcher + buttons + `?s=` attribution** (§5.2, §7).
3. **Customer login + binding + role-scoped self Profile** (§5.1, §8) + per-platform analytics (§9).
4. **Poster (branded downloadable image, NO QR)** — deferred; the image half of a creative, downloadable in IG/Story/WhatsApp-status sizes; server-render later. *(QR removed per Abhay 2026-07-08.)*

---

## 11. Config-over-code inventory (hard requirement)
Creative templates + all their copy/brand/colors; `SHARE_SHOW_REWARD` toggle; benefit lines; the `?s=` param name + platform list; helpline/WATI numbers (from Sprint 1 config); OG title/description/image per template; masking format; enabled-platform list; login providers list. Text/brand changes must need **no** code edit.

---

## 12. In-scope (Sprint 2) vs deferred
- **In:** OG preview page; 8 configurable creatives; launcher; share buttons + `?s=` attribution; per-platform analytics; Google login + Client-ID binding (email/mobile verify + admin fallback); role-scoped self Profile.
- **Deferred:** poster/branded-image rendering (Phase 4); mobile-OTP self-verify (DF-6); additional login providers; multi-partner share (architecture ready, UI Zerodha-only).

---

## 13. New ADRs to record (in `docs/architecture/02`)
- **ADR-025** — Public share = AP advertisement; Zerodha pre-approval + baked disclosures + no-paid-ads are hard gates; reward wording behind a config toggle.
- **ADR-026** — One role-scoped Profile template (admin/self) via masking config; launcher is a separate share-only surface.
- **ADR-027** — Customer identity: Google OAuth + Client-ID binding auto-verified by Zoho email-or-mobile match, admin fallback; no Zerodha API.
- **ADR-028** — Share attribution via `?s=` channel tag, recorded then stripped pre-redirect.

---

## 14. Guardrails / DoD (in addition to Sprint 1's)
- Guardrail #3 still holds on **public** pages (no `ZMPHZC`/raw Zerodha URL on `/`, `/r/{id}`, `/open`, dashboard, explorer, launcher, OG card). Admin Profile may show the code.
- Crawler user-agents excluded from human-click counts (test).
- `?s=` never present in the outbound Zerodha 302 (test).
- Every creative + OG card carries the verbatim disclosure + risk warning (test); reward wording absent unless `SHARE_SHOW_REWARD` on (test).
- Customer-login binding: email-or-mobile match binds; mismatch routes to admin queue and does NOT bind (test).
- Postgres only (M10); demo works offline (Zoho flags off → fixtures); config-over-code (no inline copy).

---

## 15. External dependency (blocks go-live, not the build)
**Zerodha written approval** of the AP-coded social share flow + the creative set (mirroring their own `/refer` page as precedent). Build and demo behind the gate; publish only after approval.

---

## 16. Mockups (visual truth)
- `mockups/share-creatives-shortlist.html` — the 8 approved creatives + social-post simulations.
- `mockups/referrer-share-launcher-mockup.html` — the launcher (customize + share).
- `mockups/customer-login-flow-mockup.html` — Google login + Client-ID + email/mobile verify + admin fallback.
- `mockups/referral-profile-mockup.html` — the shared Profile layout (admin/self).
- (Phase 4 poster — no separate mockup; it's the creative image, downloadable.)
