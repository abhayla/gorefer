# GoRefer UI/UX Specification
**Version 1.0 (Draft) — Document 7 of the GoRefer Architecture Repository**
_Sprint-1 screens, layouts, states, and interaction rules. Read alongside [01-GoRefer-Foundation-Specification.md](./01-GoRefer-Foundation-Specification.md) and [06-API-Specification.md](./06-API-Specification.md)._

## Revision History
| Version | Date | Author | Remarks |
|---|---|---|---|
| 0.1 | 2026-07-04 | Abhay Kumar Maurya / PIFS — drafted with AI assistance | Initial Sprint-1 UI/UX surface |
| 1.0 | Pending | After Design Review | Frozen for implementation |

## Status
Working Draft. This document defines every screen shipped in Sprint 1, plus one architecture-ready-but-disabled screen. Each screen is described by its purpose, layout (desktop + mobile), the **one primary action**, all interaction states (loading / empty / error / success), and which **06-API** endpoints it consumes.

---

## 1. Design Principles (binding on every screen)

These follow the GoRefer Constitution and the Foundation Spec's product philosophy:

1. **Mobile-first, not merely responsive.** Most referrals start on WhatsApp on a phone. Design the phone layout first; the desktop layout is the enhancement. Minimum comfortable target: 44×44px tap area.
2. **One primary action per screen.** Every screen has exactly one visually dominant call-to-action. Secondary actions are present but visually quieter. If a screen seems to need two equal primary actions, it is two screens.
3. **Expose only today's capabilities.** No "Coming Soon", no placeholder menus, no disabled buttons visible to end users (Foundation principle 2). The one exception in this document — the future "My Referrals" view — is gated behind a **feature flag that keeps it entirely out of the navigation and routing** for real users; it is documented here for architecture readiness only.
4. **Never expose internal logic.** Visitors never see Zerodha URLs, the partner code `c=ZMPHZC`, or database IDs. (The referrer `client_id` in the path is intentionally visible — it is already public in Zerodha's own links, ADR-001.) The redirect to Zerodha, with `c=ZMPHZC` injected, happens server-side (06-API §4).
5. **Device-aware affordances.** Detect device class and adapt: on mobile, **de-emphasize QR codes** (you cannot scan a QR with the same phone that is displaying it) and promote one-tap Share/Open; on desktop, QR is a first-class affordance.
6. **Zero friction.** Prefer one tap. No "download this PDF then upload it", no copying long links, no forcing a login where none is needed.
7. **Compliance is visible and auto-injected (Gap 14).** The AP disclosure block and the market-risk warning are **auto-injected on every page** (homepage footer, landing page, partner-direct variant) from a shared component — not hand-placed per screen. This is a **hard publish gate**: a page rendered without them does not ship. This block is a **compliance lock**: although most page content is config-driven through the 3-tier cascade, the disclosure and risk warning are pinned at the CENTRAL tier and **cannot be weakened, overridden, or removed by any GLOBAL (admin) or USER override** — enforced by construction in the render/asset path, plus a hard blocking pre-publish gate.
8. **Trust through honesty.** Never show a metric GoRefer cannot verify (e.g. "account opened") unless it came from a synced source; label externally-sourced facts. Conversion metrics **mirror Zoho's current mappings as the single truth** — there is **no "provisional" vs "final" labelling anywhere**; whatever Zoho has mapped is already final, and later reconciliation simply fills gaps or reverses un-mappings. To keep this honest, every screen that shows synced data carries a **sync-freshness indicator** so stale data can never masquerade as current.

### 1.1 Visual identity (Sprint 1 baseline)
- **Brand:** GoRefer, operated by Passive Income Financial Solutions (PIFS). The referral flow is **PIFS-branded** and must **not** clone or resemble Zerodha's signup page (locked decision #5; misrepresentation risk under NSE/COMP/55482).
- **Tone:** trustworthy, plain, uncluttered. This is a regulated financial context — no hype, no superlatives ("best", "No.1", "guaranteed"), no income projections.
- **Layout system:** single-column mobile; max content width ~1120px on desktop with a centered container.
- **Accessibility:** WCAG AA contrast; every interactive element keyboard-reachable and labelled; forms fully usable with a screen reader.

---

## 2. Screen Inventory (Sprint 1)

| # | Screen | Route | Audience | Auth | Ships in Sprint 1? |
|---|---|---|---|---|---|
| a | Marketing Homepage | `/` | Public | none | Yes |
| b | Login | `/login` | Admin (bootstrap) | none → session | Yes |
| c | Admin Dashboard | `/admin` | Admin | JWT | Yes |
| d | Referral Explorer | `/admin/referrals` | Admin | JWT | Yes |
| e | Referral Journey detail | `/admin/referrals/{client_id}` | Admin | JWT | Yes |
| h | Referral Profile (User Referral Screen) | `/admin-panel/referrer/{client_id}/` | Admin | JWT | **Yes (M9)** |
| f | "My Referrals" (customer) | `/me` | Customer | (future) | **No — feature-flag disabled** |
| g | Referral Landing Experience | `/landing/{client_id}` | Referral visitor | none | Yes |

> **Visual language (2026-07-08, DA DESIGN LOCKED).** All screens are built in **"Variant C · Cobalt Clean-Fintech"** — Inter; background `#f4f6fb`; cobalt-600 `#2F5BFF` primary accent; ink ramp `#0f1729/#334155/#64748b/#94a3b8`; thin `#e9edf3` lines; `rounded-2xl` cards with a soft shadow; pill buttons/tabs; rounded-full filter chips; circular SVG KPI rings; sortable table headers. Tokens are CSS variables (so DF-10 theming is a later config layer). The `mockups/*.html` are the visual truth. The compliance disclosure + market-risk warning stay verbatim on every customer page regardless of skin.

---

## 3. (a) Public Marketing Homepage — `gorefer.in`

**Purpose.** Explain what GoRefer is, build trust, and give the admin a way in (top-right Login). This is a marketing/brochure page — **not** a signup funnel and **not** a place with "Coming Soon" teasers. Sprint 1 supports exactly one program: **Zerodha**.

**Primary action.** None transactional for the public (there is no public signup in Sprint 1). The single dominant element is the **hero explanation**; the only clickable navigation of note is **Login** (top-right), which is intentionally quiet, not a giant CTA — the homepage's job is to inform, not convert a visitor into an account here.

**Layout — desktop**
```
┌───────────────────────────────────────────────────────────────┐
│  GoRefer                                     [ Login ]  (top-right)│
├───────────────────────────────────────────────────────────────┤
│  HERO                                                          │
│  "Refer smarter. Track everything."                           │
│  One line: GoRefer helps you manage & track referrals.        │
│  (No signup form. No QR. Just the value statement.)           │
├───────────────────────────────────────────────────────────────┤
│  WHAT IS GOREFER   |   WHY GOREFER                              │
│  3 short cards         3 short cards                            │
│  (manage / share /     (attribution / tracking / one link)     │
│   track)                                                        │
├───────────────────────────────────────────────────────────────┤
│  SUPPORTED PROGRAMS                                             │
│  [ Zerodha ]   (single card — only program live today)         │
├───────────────────────────────────────────────────────────────┤
│  FOOTER                                                         │
│  PIFS entity line · AP disclosure block · market-risk warning  │
│  contact · © PIFS                                              │
└───────────────────────────────────────────────────────────────┘
```

**Layout — mobile**
```
┌───────────────────────────┐
│ GoRefer            [Login] │   (Login stays top-right, compact)
├───────────────────────────┤
│ HERO (stacked)            │
│ headline                  │
│ one-line value            │
├───────────────────────────┤
│ WHAT IS GOREFER (stacked) │
│ card · card · card        │
├───────────────────────────┤
│ WHY GOREFER (stacked)     │
│ card · card · card        │
├───────────────────────────┤
│ SUPPORTED PROGRAMS        │
│ [ Zerodha ]               │
├───────────────────────────┤
│ FOOTER                    │
│ disclosure + risk warning │
└───────────────────────────┘
```

**Sections in detail.**
- **Hero.** Headline + one-sentence value statement. No form. No QR on mobile.
- **What / Why.** Two short bands. "What": manage, share, track referrals in one place. "Why": preserve attribution, real click tracking, one short link instead of long fragile ones. Plain language, no jargon.
- **Supported programs.** A single **Zerodha** card. Because only Zerodha is live, there is exactly one card — no greyed-out "more coming" tiles (Foundation principle 2). When a second partner goes live, a second card appears; until then, one.
- **Footer.** Carries the mandatory **AP disclosure block** verbatim: `Zerodha Broking Ltd.: SEBI Registration no.: INZ000031633 | Passive Income Financial Solutions Private Limited | NSE AP reg. no.: AP2516003693`, plus the market-risk warning: `Investments in securities market are subject to market risks, read all the related documents carefully before investing.`

**States.**
- Default (static content) — no loading needed; server-rendered.
- **Login** hover/focus — standard focus ring.
- No empty/error states (static marketing content).

**API.** None. Purely static/edge-served.

---

## 4. (b) Login — `/login`

**Purpose.** Let the bootstrap administrator (Abhay) sign in. Sprint 1 has **no public registration and no customer login** (Foundation Spec). Anyone who is not the bootstrap admin is told access is by invitation only.

**Primary action.** **Sign in** button.

**Layout — desktop & mobile (single centered card, identical intent; mobile is full-width)**
```
┌───────────────────────────┐
│         GoRefer           │
│      Admin sign-in         │
│  ┌─────────────────────┐  │
│  │ Email               │  │
│  ├─────────────────────┤  │
│  │ Password        [👁] │  │
│  └─────────────────────┘  │
│      [   Sign in   ]      │   ← single primary action
│  Access is currently by   │
│  invitation only.         │
└───────────────────────────┘
```

**Copy rule.** Below the form, always show: **"Access is currently by invitation only."** There is no "Create account" or "Sign up" link (there is no such endpoint in Sprint 1). A non-admin who somehow has credentials-shaped curiosity simply cannot proceed.

**States.**
- **Default** — empty fields, Sign in enabled once both fields are non-empty.
- **Submitting** — button shows spinner, inputs disabled.
- **Invalid credentials** — inline error under the card: "Email or password is incorrect." (maps to `401 INVALID_CREDENTIALS`).
- **Locked** — "Too many attempts. Try again in N minutes." (maps to `423 ACCOUNT_LOCKED`, honoring `Retry-After`).
- **Rate limited** — "Too many attempts. Please wait and retry." (`429`).
- **Success** — redirect to `/admin`.

**API.** `POST /api/auth/login` (06-API §6.1). On success, access JWT held in memory, refresh token in `HttpOnly` cookie.

**Mobile note.** Password reveal toggle is large enough to tap; keyboard type for email field is `email`.

---

## 5. (c) Admin Dashboard — `/admin`

**Purpose.** The operational at-a-glance view: what happened recently that the admin may act on — new clicks, new leads, new contacts (account-status events synced from Zoho). Not a data-entry screen; Sprint 1 admin is visibility.

**Primary action.** **Open Referral Explorer** (the natural next step from any summary is to drill in). Everything else on this screen is read-only glance.

**Layout — desktop**
```
┌───────────────────────────────────────────────────────────────┐
│ GoRefer Admin        [Today ▾]        Abhay ▾ (logout)         │
│  Zoho synced 4 min ago ✓            (sync-freshness indicator) │
├───────────────────────────────────────────────────────────────┤
│  KPI ROW                                                       │
│  [Clicks 143] [Human 121] [Leads 18] [Redirects 96] [Opened 4]│
├───────────────────────────────────────────────────────────────┤
│  FUNNEL (shared→clicked→landing→redirect→lead→opened)          │
│  horizontal bars                                              │
├───────────────────────────┬───────────────────────────────────┤
│  RECENT LEADS             │  TOP REFERRERS                     │
│  name · mobile(masked) ·  │  name · client_id(masked) ·        │
│  referrer · status · time │  leads · clicks                    │
├───────────────────────────┴───────────────────────────────────┤
│              [ Open Referral Explorer → ]                      │
└───────────────────────────────────────────────────────────────┘
```

**Layout — mobile**
```
┌───────────────────────────┐
│ GoRefer Admin   [Today ▾] │
│                    Abhay ▾ │
│ Zoho synced 4 min ago ✓   │
├───────────────────────────┤
│ KPI cards (2-up grid,     │
│  scroll): Clicks · Human  │
│  · Leads · Redirects ·    │
│  Opened                   │
├───────────────────────────┤
│ FUNNEL (stacked bars)     │
├───────────────────────────┤
│ RECENT LEADS (list)       │
│  row · row · row          │
├───────────────────────────┤
│ TOP REFERRERS (list)      │
├───────────────────────────┤
│ [ Open Referral Explorer ]│
└───────────────────────────┘
```

**Controls.**
- **Range selector** (`Today / 7d / 30d / Custom`) — drives the whole page.
- **KPI cards** — clicks, human clicks (bot-filtered), leads, redirects-to-partner, accounts opened. "Accounts opened" is shown only from synced data and carries a small "from Zoho" tag so it's never mistaken for a GoRefer-observed number. These figures reflect **Zoho's current mapped truth** — there is no provisional/final distinction; the value shown is final as of the last sync.
- **Sync-freshness indicator** — a small header line ("Zoho synced N min ago ✓ / N days ago ⚠") backed by `last_successful_zoho_sync_at`; it turns to a warning state once staleness crosses the threshold, so a stalled sync can never make old data look current.
- **Funnel** — the six stages from 06-API §6.2.
- **Recent leads / Top referrers** — masked identifiers; tap a row → its Journey detail. The **Top Referrers** panel is populated **lazily, per referrer, as each becomes active** (first click or first Zoho-imported conversion triggers that referrer's history fetch). Consequently **all-time global totals may be incomplete at launch** and fill in as referrers become active; a complete all-time leaderboard depends on the deferred bulk backfill (backlog DF-4).

**States.**
- **Loading** — skeleton cards.
- **Empty** — "No activity in this range yet." with a hint to widen the range. No fabricated demo numbers.
- **Error** — "Couldn't load the dashboard. Retry." (non-blocking banner).
- **Session expired** — silent refresh via `/api/auth/refresh`; if that fails, redirect to `/login`.

**API.** `GET /api/admin/dashboard` (06-API §6.2). Row taps → §6/§7 below.

---

## 6. (d) Referral Explorer — `/admin/referrals`

**Purpose.** Find and scan referral journeys with rich filters. This is the admin's working surface.

**Primary action.** **Apply filters** (the search that produces the list). Each result row's tap-through to the Journey detail is the secondary action.

**Columns / referrer display (updated 2026-07-07).** The **Referral ID** column = the referrer's raw Zerodha `client_id` (ADR-001). The **Referrer** column shows the referrer's **name when known** (from a `Customer` row or Zoho); when the name is not on file it shows **"— name not on file —"**, and **NOT** a duplicate of the client_id. (Sprint-1 reality: names light up only once Customer data is loaded or Zoho supplies them, so most Referrer cells read "— name not on file —" for now — this is why the two columns looked identical.) Each **Referrer** cell links to that referrer's **Referrer Profile** page (new screen — §6(e), pending Abhay's UI sign-off).

**Layout — desktop**
```
┌───────────────────────────────────────────────────────────────┐
│ Referral Explorer                                             │
├───────────────────────────────────────────────────────────────┤
│ FILTER BAR                                                    │
│ [Partner: Zerodha ▾] [Referrer ___] [Customer ___]           │
│ [Mobile ___] [Campaign ___] [Status ▾] [From] [To] [Apply]   │
├───────────────────────────────────────────────────────────────┤
│ RESULTS TABLE                                                 │
│ client_id│ prospect │ mobile* │ referrer │ campaign │ status │…│
│ DA1707   │ Rahul S. │98•••210 │ Abhay    │ jul_refer│ NEW    │→│
│ SU9914   │ Priya V. │…        │ Sunita   │ status…  │ KYC…   │→│
│ DA1707   │ (no lead)│ —       │ Abhay    │ fb_jul   │ —      │→│
├───────────────────────────────────────────────────────────────┤
│ ‹ Prev   Page 1 of 6   Next ›            25 / page ▾          │
└───────────────────────────────────────────────────────────────┘
```

**Layout — mobile**
```
┌───────────────────────────┐
│ Referral Explorer         │
│ [ Filters ▾ ]  (collapsed)│
├───────────────────────────┤
│ RESULT CARD               │
│ Rahul Sharma   [NEW]      │
│ 98•••••210 · jul_refer    │
│ ref: Abhay · 9:05am    →  │
├───────────────────────────┤
│ RESULT CARD               │
│ Priya Verma  [KYC_STARTED]│
│ … · status_jul            │
├───────────────────────────┤
│ ‹ Prev · 1/6 · Next ›     │
└───────────────────────────┘
```
On mobile, the filter bar collapses into a **Filters** sheet (tap to expand, apply, collapse). Rows become cards. This keeps one primary action visible.

**Filters.** partner, referrer, customer (name), mobile (exact), campaign, status (`NEW / CONTACTED / INTERESTED / KYC_STARTED / ACCOUNT_OPENED / REJECTED`), from/to date. Combinable. Filter state is reflected in the URL query so a filtered view is shareable/bookmarkable among admins.

**Example rows** (as rendered):
| client_id | prospect | mobile* | referrer | campaign | status |
|---|---|---|---|---|---|
| DA1707 | Rahul Sharma | 98•••••210 | Abhay (DA••07) | jul_refer | NEW |
| SU9914 | Priya Verma | 91•••••882 | Sunita (SU••14) | status_jul | KYC_STARTED |
| DA1707 | (no lead yet) | — | Abhay (DA••07) | fb_jul | REDIRECTED |

**States.**
- **Loading** — table/card skeletons.
- **Empty (no matches)** — "No referrals match these filters." + a "Clear filters" reset.
- **Error** — inline retry.
- **Too broad** — if `page_size` exceeded or query invalid, show validation hint (maps to `422`).

**API.** `GET /api/admin/referrals` (06-API §6.3), paginated.

---

## 7. (e) Referral Journey detail — `/admin/referrals/{client_id}`

**Purpose.** Show the full chronological timeline of every event for one referral — for support, dispute resolution, and attribution audits.

**Primary action.** None mutating in Sprint 1; the screen's job is to **read** the timeline. (The dominant element is the timeline itself.) A **Back to Explorer** control is the main navigation.

**Layout — desktop & mobile (single column; naturally mobile-friendly)**
```
┌───────────────────────────────────────────────┐
│ ‹ Back to Explorer                            │
├───────────────────────────────────────────────┤
│ HEADER                                        │
│  client_id DA1707 · Program: Zerodha          │
│  Referrer: Abhay (DA1707)                     │
│  Lead: Rahul Sharma · 9876543210 · Prayagraj  │
│  Status: KYC_STARTED                          │
├───────────────────────────────────────────────┤
│ TIMELINE (newest at bottom or top, one axis)  │
│  ● LINK_SHARED (whatsapp)        08:10        │
│  ● LINK_CLICKED (human_high,     08:40        │
│      Android/Chrome, utm=whatsapp)            │
│  ● LANDING_VIEWED                08:40        │
│  ● LEAD_CREATED (need_help)      09:05        │
│  ● WATI_NOTIFIED → Ashok         09:05        │
│      (template, delivery: delivered)          │
│  ● REDIRECTED_TO_PARTNER         09:07        │
│  ● ACCOUNT_STATUS_IMPORTED       14:20        │
│      (KYC_STARTED · source: zoho)             │
└───────────────────────────────────────────────┘
```

**Detail rules.**
- This is the **only** screen that shows **unmasked** mobile and client_id; that access is logged for DPDP accountability.
- Each timeline node shows its **origin** — GoRefer-observed (click, redirect), Wati (message + delivery status), or Zoho (imported status). Externally-sourced facts are visually tagged so they're never confused with GoRefer's own observations (Foundation principle 4).
- Confidence band is shown on the click node (`human_high`, etc.).

**States.**
- **Loading** — timeline skeleton.
- **Partial journey** — a link that was clicked but never produced a lead shows a short timeline ending at `REDIRECTED_TO_PARTNER` with a "No lead captured yet" note (honest, not empty-faked).
- **Not found** — "This referral could not be found." (maps to `404 REFERRAL_NOT_FOUND` — no journey exists for this `client_id`, e.g. never clicked). Invalid-format ids map to `400 INVALID_CLIENT_ID`.
- **Error** — inline retry.

**API.** `GET /api/admin/referrals/{client_id}` (06-API §6.4).

---

## 7e. (h) Referral Profile — "User Referral Screen" — `/admin-panel/referrer/{client_id}/` (M9)

**Purpose.** The single-referrer 360 view: **everything referred by one Zerodha client id** — the referrer's Zoho-enriched identity, per-partner referral links, every click they generated (with geo/device/traffic), and the people they referred. Admin-only in Sprint 1; the same layout supports the future customer "My Referrals" (§8) with PII masked. **Visual truth:** `mockups/referral-profile-mockup.html` (Variant C).

**Primary action.** None mutating — this screen **reads**. Its dominant elements are the identity band + the two data tabs.

### Data sources
- **Zoho READ enrichment (read-only; WRITE stays OFF — `ENABLE_ZOHO_READ`).** A referrer is matched to their Zoho **Contact by `ClientId`**; the top band + Referred-People tab read Zoho. In demo/CI (flag off) a **fixture-backed** adapter returns seeded data — the whole screen works offline. Zoho WRITE is **not** enabled (PIFS enters Zoho leads manually — DF-9); this is enrichment only, never a status write (guardrail #2 preserved). Missing Zoho value → **"— not on file —"**.
- **GoRefer's own captured data.** Clicks/leads/accounts aggregates, and the **Clicks tab** per-row detail (geo from the click Event's country/state, **city + raw IP from the erasable `VisitorPII`**, device/OS/browser parsed from the user-agent, channel from the click), come from GoRefer's event stream — never Zoho.

### Layout (Variant C; matches the mockup)
1. **Breadcrumb** back to the Referral Explorer + the client_id.
2. **Identity band** — avatar/initials, name (Zoho `Full_Name`, else "— name not on file —"), client_id chip, **Active-Investor** chip; enrichment chips: City/State, Profession, Account Status, Opened date (TRUE Zoho open date, ADR-017), Reward wording (from `REFERRAL_INCENTIVE_CLAIM`). Plus **4 headline aggregates** — **Clicks, Unique visitors** (approx, bot-filtered, labelled `*`), **Leads, Accounts** — the first three rendered as circular SVG KPI rings.
3. **Per-link summary strip** — one card per **real, enabled** partner link (partner name, partner code, `gorefer.in/r/{client_id}`, per-link clicks/leads/accounts). Today: **Zerodha only** — the illustrative "Loan" card in the mockup is **NOT shipped** (it only demonstrates the multi-partner layout). The structure is config/data-driven, so N partners render with no redesign (ties to DF-5/DF-9).
4. **Two tabs on one screen:**
   - **Clicks** — one row per click: **Date/time · Partner/Link · Channel · City · Region · Country · IP · Device · OS/Browser · Traffic (Human/Bot) · Outcome**. Filters above the table: **All / Human / Bot / Mobile / Desktop / WhatsApp** + a free-text **city/IP** search; sortable headers. **Bot/preview rows are dimmed and excluded** from the click & visitor totals (logged, not counted — ADR-019).
   - **Referred People** — one row per identified person (from Zoho): **Name · City · Profession · Partner · Account Status · Opened · Reward**. A person appears only after they submit the form or Zoho records them.

### Config-over-code
- **No hardcoded copy or columns.** The Clicks/People **column sets**, the filter set, and user-facing strings (the "approx / bot-filtered" note, the "— not on file —" marker) come from a **config constant** (`PROFILE_CONFIG`), not inline literals — per-partner column tuning is a config change (DF-5 pattern). Reward wording continues to come from the single `REFERRAL_INCENTIVE_CLAIM` field.

### PII masking (built now, applied later)
- The **admin** view shows **full IP + phone**. A config rule **`PII_MASK_FOR_CUSTOMER_VIEW`** (built now, dormant) masks IP → city-only and phone → partial in the **future** customer/referrer view; it activates only when `ENABLE_CUSTOMER_LOGIN` turns on. No dead UI now.

### Entry points
1. The **Referrer cell in the Referral Explorer** (§6/(d)) links here.
2. A **search** entry (`/admin-panel/referrers/`, the "Referral Profile" nav item) — search by client_id or name; an exact client_id jumps straight in.
3. Future: the top-referrers leaderboard rows (dashboard) link here.

### States
- **Valid referrer** — full screen as above (Zoho-enriched where a Contact matches; GoRefer aggregates always).
- **No footprint** — a well-formed client_id with **no** GoRefer referral and **no** Zoho conversion → **404** (not a fabricated empty profile). A malformed client_id → 404 (validator).
- **Zoho unmatched** — the screen still renders from GoRefer's own data; Zoho fields show "— not on file —".

### Self-click note (deferred — NOT built)
- A later polish: if a click's mobile later matches the referrer's known Zoho mobile, tag it **"self-click"** and exclude from conversion counts. Logged as a backlog note; **not** in this mission.

**API / implementation.** Server-rendered (Django, HTMX/Variant C), route `/admin-panel/referrer/{client_id}/`. The Clicks table filters/sorts client-side from a server-rendered JSON payload; column config is passed as JSON (config-over-code). Zoho READ adapter behind the doc-08 contract (`apps/integrations/zoho/read.py`).

---

## 8. (f) "My Referrals" — Customer View — `/me` — **DISABLED (feature flag)**

> **Status: architecture-ready, UI disabled in Sprint 1.** This screen is **not** shipped. It is documented so the data model, routing, and API can be designed to accommodate it without a later redesign (Foundation principle 1, "build once, scale forever"). Per Foundation principle 2 ("expose only today's capabilities"), it is gated behind a feature flag `feature.customer_portal = false` that removes the route from the router and hides all entry points — there is **no disabled button, no greyed menu, no "Coming Soon"** anywhere a real user can see. This section is design intent only.

**Intended purpose (future).** Let an existing customer see their own referral link, QR code, share buttons, click count, and the status of friends they've referred.

**Intended primary action (future).** **Share my referral link** (one-tap, channel-aware).

**Intended layout (future, mobile-first)**
```
┌───────────────────────────┐
│ My Referrals              │
│ Your link:                 │
│  gorefer.in/r/{client_id}  │
│ [ Share ]  (primary)      │
│ [ Copy ]  [ QR ]*         │   *QR de-emphasized on mobile
├───────────────────────────┤
│ Your stats                │
│ clicks · leads · opened   │
├───────────────────────────┤
│ Friends you referred      │
│ name · status             │
└───────────────────────────┘
```

**Why it's disabled now.** Sprint 1 explicitly excludes customer login, public registration, and self-service dashboards (Foundation Spec §Product Scope). Enabling this later flips the flag and adds customer authentication (a future auth tier not in 06-API v1). Until then it does not exist to users.

**API (future).** Would consume a customer-scoped variant of the referral endpoints; **not defined in 06-API v1.**

---

## 9. (g) Referral Landing Experience — `/landing/{client_id}`

**Purpose.** The branded page shown after the first click on `gorefer.in/r/{client_id}` (when the program is in `show_landing` mode, 06-API §4.1 step 5). It reassures the visitor, states benefits, and carries the compliance block. It must be clearly **PIFS-branded and must NOT clone or resemble Zerodha's signup page** (locked decision #5). The `{client_id}` in the URL is the **raw referrer id** (ADR-001).

**Configurable per partner.** The page is **config, not code** — content and buttons differ per partner. For **Zerodha** it shows Zerodha-specific content, the SEBI/NSE **AP disclosure block**, and the **two buttons** below. The same page serves **both** a referrer opening their own link **and** a friend opening a shared link (audiences A and B, one page).

**Referrer personalization is beacon-gated.** On initial load the page shows a **generic greeting only — no referrer name**. The optional "[Referrer] referred you" personalization is revealed **only after the JS human-confirmation beacon completes** (and only to a request carrying a valid, fresh server-issued nonce). This keeps the short raw-`client_id` link (ADR-001) unchanged while preventing unauthenticated enumeration of the id→name map: `GET /api/landing/{client_id}` returns no name on first load, so guessing ids harvests nothing. The residual first-name-only exposure after a confirmed human click is consciously accepted.

**Partner-direct variant (Gap 1).** The same page has a **partner-direct** rendering for the PIFS-direct entry (`/open`, 06-API §4.2) where there is **no referrer**: the "[Referrer] recommended this to you" line and the **"Referral ID"** echo are **hidden**, the WhatsApp-share prefill **omits the referral id**, and the eventual redirect omits `r=` (plain `c=ZMPHZC`). Everything else — benefits, disclosure, both buttons — is identical.

**Referral ID echo (Gap 11/13).** On the referrer path, a small, quiet line **"Referral ID: {client_id}"** is shown near the buttons so the visitor (and the WhatsApp prefill) carry the reference. It is **display-only**, never a raw error, and is **omitted** in the partner-direct variant.

**Two actions.**
1. **"Continue to Zerodha"** — opens a short form (name, email, phone). On submit, GoRefer saves the lead (referrer = the `client_id` from the URL, partner = `ZMPHZC`) to GoRefer **and** Zoho, then redirects the real browser to `signup.zerodha.com/api/lead?c=ZMPHZC&r={client_id}`. Auto-filling Zerodha's own form with the captured name/email/phone is an **OPEN, build-time POC** (currently believed not possible); the form still captures the lead regardless — it is **not** a dependency. (The form-first choice is Abhay's decision and may be removed later.)
2. **"Share referral details on WhatsApp"** — a **client-side `wa.me` deep link** to a **config-driven WhatsApp number**, resolved through the 3-tier configuration cascade (CENTRAL default = the WATI business number `+91 70806 42020` PIFS operates → overridable at GLOBAL/admin and, later, USER tier). The personal number `+91 73888 82020` is **never** a hardcoded customer-facing value. The link is pre-filled with **referring** language + the referral id — e.g. `wa.me/{wati_business_number}?text=Hi, I'd like to refer someone for a Zerodha account. Referral ID: {client_id}` (**not** "I want to open an account" — the actor is *referring*). Tapping it fires a `SharedOnWhatsApp` event (`POST /api/share`, channel `whatsapp`) and opens WhatsApp. Because the inbound lands on the WATI business number carrying the referral id, it is **auto-attributed** via Wati → a Zoho lead, reconciled to the journey by referral id + mobile. In the **partner-direct variant** the prefill omits the referral id. **Accepted downside:** the person can edit the pre-filled text before sending, so attribution here is high-but-not-perfect.

**Helpline "call" line (2026-07-08).** Below the two buttons the landing page shows a quiet **"Prefer a call? Free, fully-assisted account opening — call {SUPPORT_HELPLINE_PHONE}"** line with a `tel:` link. The number is the **config value `SUPPORT_HELPLINE_PHONE`** (default `+91 73888 82020`, Ashok) — **distinct** from the WhatsApp-share WATI number (`WATI_BUSINESS_NUMBER`, `917080642020`), and config-driven (no inline literal). (There is **no separate thank-you page** in Sprint 1 — the capture flow saves the lead then redirects to Zerodha per M3; if a post-submit interstitial is ever added it reads the same config.)

**Link-preview card + share-channel attribution (M11 / ADR-028, S2-01 §5.3/§7).** The same `/r/{client_id}` page carries **Open Graph + Twitter-Card** meta (`og:title`, `og:description`, `og:image`, `og:url`, `twitter:card=summary_large_image`) so a forwarded link renders a compliant **preview card** in WhatsApp/Facebook/LinkedIn/X. The card content is **config, not code** (`OG_TITLE` / `OG_DESCRIPTION` / `OG_IMAGE` / `OG_SITE_NAME`, with `PUBLIC_BASE_URL` for absolute URLs); it is PIFS-branded, **carries no partner code and no raw Zerodha URL, and must not resemble/clone Zerodha**. A **preview crawler** (facebookexternalhit, Twitterbot, LinkedInBot, WhatsApp, Telegrambot, Slackbot) receives the card but is **excluded from human-click counts and creates no journey/redirect** (extends the Sprint-1 bot filter). A shared link may append **`?s={channel}`** (`wa, fb, x, li, tg, ig, email, copy`; unknown → `other`; absent → none) — the redirect **records it as the click's Channel** (the existing Referral-Profile Clicks "Channel" column, `metadata["channel"]`) and then **strips `s` before the 302**, so the Zerodha `Location` is always exactly `…/api/lead/?c=ZMPHZC&r={client_id}` (never carries `s=`). The param **name** is config (`SHARE_CHANNEL_PARAM`, default `s`).

**Layout — mobile-first (this page is overwhelmingly viewed on mobile from WhatsApp)**
```
┌───────────────────────────┐
│ Passive Income Financial   │
│ Solutions                  │
│ "Open your Zerodha account │
│  with PIFS"                │
├───────────────────────────┤
│ [Referrer] referred you.   │   (revealed only AFTER the human-
│                            │    confirmation beacon; generic
│                            │    greeting, no name, on load)
├───────────────────────────┤
│ BENEFITS                   │
│ ✔ Zero account-opening fee │
│ ✔ Fast digital KYC         │
│ ✔ Trusted by millions      │
│ ✔ Powerful platforms       │
├───────────────────────────┤
│ Referral ID: {client_id}   │  (echo; hidden in partner-direct)
│ [ Continue to Zerodha ]    │  ← Button 1 (opens short form)
│                            │
│ [ Share referral details   │  ← Button 2 (wa.me to WATI
│   on WhatsApp ]            │     business no., referring prefill)
├───────────────────────────┤
│ DISCLOSURE BLOCK (auto-    │
│  injected on every page)   │
│ SEBI INZ000031633 | PIFS | │
│ NSE AP AP2516003693        │
│ Market-risk warning line   │
└───────────────────────────┘
```

**Layout — desktop.** Same content, two-column: benefits + the two buttons on the left, help/contact panel on the right; disclosure spans the footer. QR may appear on desktop (a visitor on a laptop can scan to continue on their phone); QR is **suppressed on mobile** (principle 5).

**Continue-to-Zerodha flow.** Tapping **Continue to Zerodha** reveals the short form (Name, Email, Phone). Submitting posts to `POST /api/leads` with `source=landing_need_help`; GoRefer saves the lead **first** (referrer = `client_id`, partner = `ZMPHZC`), mirrors to Zoho, fires the Wati messages, then redirects the browser to `https://signup.zerodha.com/api/lead?c=ZMPHZC&r={client_id}`. GoRefer **never** auto-submits Zerodha's reCAPTCHA-gated form — a real human lands on Zerodha's page (locked decision #4); a human (Ashok) can also complete KYC on a call.

**Share-on-WhatsApp flow (message updated 2026-07-07).** Tapping **Share referral details on WhatsApp** emits `share_clicked` (`SharedOnWhatsApp`) and opens the person's WhatsApp to `wa.me/{WATI business number}` (config-driven) with the message below pre-filled (URL-encoded). `{name}` / `{phone}` / `{email}` are filled from the landing form inputs when the visitor has entered them, else left blank for them to type in WhatsApp; `{client_id}` is the referral id from the URL:

```
Hi, I'd like to refer for a Zerodha account. My Referral ID: {client_id}
*Here are referral details*
Name: {name}
Phone Number: {phone}
Email: {email}
```

(The partner-direct variant omits the `My Referral ID` line.)

**States.**
- **Loading** — branded skeleton (logo + spinner), no Zerodha branding ever.
- **Valid `client_id`** — full page as above; content (reward wording, disclosure) from `GET /api/landing/{client_id}` (generated from config; lazy creation means any format-valid id renders). The referrer first name is **not** in the initial payload — it is fetched only after the human-confirmation beacon completes (see "Referrer personalization is beacon-gated" above).
- **Invalid `client_id` (format)** — friendly branded page: "This referral link isn't valid. You can still open a Zerodha account with PIFS." + a Continue that uses the partner-only path (`/r/open`). Never a raw error.
- **Form submitting** — button spinner; on success, redirect to Zerodha (and a "we've saved your details" confirmation); on validation error, inline field messages (maps to `422`).
- **Consent (DPDP, Gap 15)** — the Continue form requires an **explicit consent checkbox** before submit, next to a short **consent notice** ("I agree to be contacted about opening a Zerodha account and to PIFS processing my details") and a **Privacy Policy link**. Submit is disabled until it is ticked (Meta opt-in hygiene; `consent:true` in 06-API §5.3). The notice states retention in plain language (details anonymized if no account is opened).

**Compliance (hard gate).** The disclosure block and market-risk warning render on every state of this page and are a **compliance lock** — pinned at the CENTRAL config tier, they cannot be weakened or removed by any admin or user override. The reward wording ("300 points / 10% brokerage") is pulled from a single config value so it can be reworded or removed in one place if NSE reinstates the ban — the UI must not hardcode the incentive figures.

**API.** `GET /api/landing/{client_id}` (data), `POST /api/leads` (Continue-to-Zerodha form), `POST /api/share` (Share-on-WhatsApp / `SharedOnWhatsApp`), and the `wa.me/{office}` client-side deep link. See 06-API §4–5.

---

## 10. Cross-Screen Behaviors

- **Device detection.** A lightweight server + client check sets a device class (`mobile` / `tablet` / `desktop`). QR affordances are hidden on `mobile`; Share uses the native share sheet on mobile and copy-to-clipboard fallback on desktop.
- **Masking.** Mobile numbers and client IDs are masked everywhere except the single Journey detail screen (§7), where access is logged.
- **Error surfaces.** Public pages (homepage, landing) never render raw errors or JSON — always a branded human message. Admin pages may show concise technical retry banners.
- **Auth transitions.** Admin screens attempt a silent token refresh before bouncing to `/login`.
- **No dead ends.** Every not-found or revoked state offers a forward action (partner-only open, retry, or back).

---

## 11. Screen ↔ API Map

| Screen | Route | Primary API(s) (06-API) |
|---|---|---|
| Homepage | `/` | none (static) |
| Login | `/login` | `POST /api/auth/login` |
| Admin Dashboard | `/admin` | `GET /api/admin/dashboard` |
| Referral Explorer | `/admin/referrals` | `GET /api/admin/referrals` |
| Journey detail | `/admin/referrals/{client_id}` | `GET /api/admin/referrals/{client_id}` |
| My Referrals (disabled) | `/me` | (future — not in v1) |
| Landing Experience | `/landing/{client_id}` | `GET /api/landing/{client_id}`, `POST /api/leads`, `GET /r/{client_id}?continue=1` |

---

## 12. Open Items Affecting This Spec
1. **Lead form fields** — whether the Need-help form is Name/Mobile (2) or Name/Mobile/City (3). Rendered as config-driven-optional until resolved (Foundation/Build-Spec).
2. **Domain scheme** — `gorefer.in` bare path (recommended) vs `z.gorefer.in`; copy that shows a link (e.g. landing "your link") must read from config, not hardcode the host (Build-Spec §6).
3. **Reward wording** — must remain a single swappable config string, never hardcoded in any screen (compliance §7.1).
4. **Contact/callback number** on the landing "Need help?" panel — this is a **config value resolved through the 3-tier cascade**, with the CENTRAL default = the WATI business number `+91 70806 42020` (overridable at GLOBAL/admin). No personal number is hardcoded on any customer-facing surface (Build-Spec §6; config-cascade A1).

_End of 07-UI-UX-Specification.md — Sprint 1._
