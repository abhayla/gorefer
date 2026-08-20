# GoRefer API Specification
**Version 1.0 (Draft) — Document 6 of the GoRefer Architecture Repository**
_Sprint-1 REST API surface. Read alongside [01-GoRefer-Foundation-Specification.md](./01-GoRefer-Foundation-Specification.md), 04-System-Architecture (companion, forthcoming), and 05-Database-Design (companion, forthcoming)._

## Revision History
| Version | Date | Author | Remarks |
|---|---|---|---|
| 0.1 | 2026-07-04 | Abhay Kumar Maurya / PIFS — drafted with AI assistance | Initial Sprint-1 API surface |
| 1.0 | Pending | After Architecture Review | Frozen for implementation |

## Status
Working Draft. This document defines the complete HTTP contract for Sprint 1. Endpoint shapes here are binding on both the redirect/capture service and the admin application; the data those endpoints read and write is defined in **05-Database-Design**, and where each endpoint runs (edge worker vs. application API) is defined in **04-System-Architecture**.

---

## 1. Scope & Cross-References

Sprint 1 exposes exactly two families of HTTP surface, consistent with the Foundation Spec (§Product Scope):

1. **Public, unauthenticated surface** — the referral visitor's path: the redirect endpoint, the landing-page data endpoint, lead capture, and share-event logging. These are the hot path and must be fast, cache-aware, and abuse-resistant.
2. **Administrative surface** — the single bootstrap administrator's path: auth, the operational dashboard, and the referral explorer / journey timeline. Plus one machine-to-machine sync endpoint for Zoho.

This spec deliberately contains **no customer-login or self-service endpoints** — those are excluded from Sprint 1 (Foundation Spec §Product Scope) though the data model behind them is reserved.

**Cross-reference map**
- Entities named below (`referral_program`, `participant`, `referral_link`, `click_event`, `referral_lead`, `referral_journey_event`, `admin_user`, `admin_session`) are defined in **05-Database-Design**. This document does not redefine columns; it references them.
- Deployment topology — which handler is a Cloudflare Worker at the edge vs. an origin application route, and how the `client_id`→participant lookup is cached — is defined in **04-System-Architecture**.
- Business rules referenced (60-day attribution window, keep-`r=` Option A, capture-first ordering, no auto-submit of Zerodha's form) are locked in the Build-Spec and summarized in the Foundation Spec.

### 1.1 Identifier scheme used in this spec
This spec is written against the **raw Zerodha `client_id`** identifier scheme, **locked** in ADR-001: the path segment in `/r/{client_id}` **is** the referrer's Zerodha `client_id` — there is **no opaque token and no token→id mapping**. The redirect handler **format-validates** the `client_id` (no ownership check — there is no Zerodha API), **lazily creates** the referrer + journey + click event on first click, and injects the partner code `c=ZMPHZC` **server-side** into the redirect. Future non-Zerodha partners that expose no reusable native id will instead use a GoRefer-**generated** id (minted at referrer login) — a forward-looking note, not Sprint 1.

---

## 2. Conventions

- **Base URLs.** Public surface: `https://gorefer.in` (bare domain + path, **locked** per ADR-005 — no `z.gorefer.in` subdomain; the referral path carries the raw `client_id`). Admin + JSON API: `https://gorefer.in/api`.
- **Content type.** All JSON endpoints accept and return `application/json; charset=utf-8`. The redirect endpoint returns an HTTP redirect or HTML, never JSON.
- **Timestamps.** ISO-8601 UTC, e.g. `2026-07-04T09:30:00Z`.
- **IDs.** Opaque strings. Never expose database primary keys, Zerodha URLs, or the partner code (`c=ZMPHZC`) in any public response body (Foundation Spec principle 4, "Never expose internal logic").
- **Versioning.** All JSON endpoints are served under `/api` and are implicitly `v1`. A breaking change ships under `/api/v2`.
- **Idempotency.** `GET` and the Zoho sync endpoint are idempotent. `POST /api/leads` is de-duplicated server-side (see §5.3).

### 2.1 Standard error format
Every JSON endpoint returns errors in one shape:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Human-readable summary.",
    "details": [
      { "field": "mobile", "issue": "Must be a 10-digit Indian mobile number." }
    ],
    "request_id": "req_8f3a2c9e"
  }
}
```

- `code` — stable machine-readable enum (see §8).
- `message` — safe to show to end users where relevant; never leaks internal identifiers.
- `details` — optional, per-field for validation errors.
- `request_id` — echoes the correlation ID (see §2.2) for support/debugging.

### 2.2 Correlation
Every response carries an `X-Request-Id` header. If the client sends one, it is echoed; otherwise the server generates it. This ID appears in logs and in `error.request_id`.

### 2.3 Rate limiting
All endpoints are rate-limited. Limits are enforced at the edge (see 04-System-Architecture) keyed by client IP, and for the admin surface additionally by session.

| Surface | Limit | Window | Notes |
|---|---|---|---|
| `GET /r/{client_id}` | 120 req | per min per IP | Hot path; generous. Burst of automated hits is classified as `suspicious` (see §4.4), not blocked outright, so genuine sharers on shared NATs aren't lost. |
| `GET /api/landing/{client_id}` | 120 req | per min per IP | Mirrors the redirect. |
| `GET /api/landing/{client_id}/referrer` | 30 req | per min per IP | Nonce-gated name reveal; tighter cap + bot filter to make id→name enumeration impractical (ADR-021). |
| `POST /api/leads` | 10 req | per min per IP | Anti-spam on the capture form. |
| `POST /api/share` | 30 req | per min per IP | |
| `POST /api/auth/login` | 5 req | per 15 min per IP | Brute-force protection; also per-account lockout after 10 consecutive failures. |
| Admin read endpoints | 300 req | per min per session | |
| `POST /api/integrations/zoho/account-status` | 600 req | per min per API key | Machine-to-machine. |

On exceeding a limit the server returns **429** with `code: RATE_LIMITED` and a `Retry-After` header (seconds).

---

## 3. Authentication & Authorization Model

Three trust tiers:

1. **Public / anonymous** — the redirect, landing-data, lead-capture and share endpoints. No credentials. Protected only by rate limiting, input validation, and bot classification. This is mandatory: the redirect must work for any real browser (Build-Spec — the only compliant path is redirecting a real human).
2. **Admin session (JWT)** — every `/api/admin/*` endpoint and `/api/auth/*`. Sprint 1 has exactly **one bootstrap administrator** (Foundation Spec §User Types).
3. **Service key (Zoho sync)** — `POST /api/integrations/zoho/account-status` authenticates with a static, rotatable service API key, not a user session.

### 3.1 Admin session (JWT)
- `POST /api/auth/login` verifies credentials and returns a **short-lived access JWT** (15 min) plus a **refresh token** set as an `HttpOnly; Secure; SameSite=Strict` cookie (7 days).
- The access JWT is sent on each admin request as `Authorization: Bearer <jwt>`.
- JWT claims: `sub` (admin user id), `role` (`admin`), `iat`, `exp`, `jti`. Signed with HS256 using a secret held in the platform secret store (never in source — cf. the hardcoded-token finding in the Wati/Zoho map that this design explicitly avoids).
- On access-token expiry the client calls `POST /api/auth/refresh` (refresh cookie) to mint a new access JWT. Refresh rotation: each refresh invalidates the prior refresh token (`admin_session` row).
- `POST /api/auth/logout` revokes the current `admin_session`.
- Missing/invalid/expired JWT → **401** `UNAUTHENTICATED`. Valid JWT but insufficient role → **403** `FORBIDDEN`.

### 3.2 Service key (Zoho)
- Header `X-GoRefer-Service-Key: <key>`. Keys are stored hashed, are rotatable, and are scoped to the single sync endpoint. Invalid/missing key → **401** `UNAUTHENTICATED`.
- **Interim auth (Sprint 1):** static service key **plus a Zoho-server-IP allowlist** — a source IP outside the allowlist is rejected. This is deliberately the cheap-hygiene minimum, not the full protection: if the static key leaks, the endpoint stays forgeable from an allowlisted IP. The endpoint is only live from M6 (M1–M4 run demo-mode with `ENABLE_ZOHO_WRITE=false`, so there is no live exposure), and the sole writer of `credited_referrer`/conversions must be hardened before a real reward payout depends on it.
- **Deferred (backlog DF-2):** the HMAC "wax-seal" — an `X-GoRefer-Signature` over `body + timestamp + one-time nonce` so a leaked key alone cannot forge or replay status events. Also deferred (backlog DF-1) is the Zoho-API "pull"/polling alternative that would remove the forgeable inbound endpoint entirely.

---

## 4. Public Endpoint — Redirect (the core of the system)

### 4.1 `GET /r/{client_id}`
**Purpose.** The single most important endpoint. Takes the **raw Zerodha `client_id`** directly from the path (no token lookup), **format-validates** it, **lazily creates** the referrer identity + journey + click event on the first click, **logs the click with a bot/confidence classification**, optionally shows a branded landing page, and finally **302-redirects a real browser** to Zerodha's public lead URL with the partner code injected server-side and the referrer code attached. This is the endpoint that gives PIFS the click tracking that does not exist today (Build-Spec R3) while never auto-submitting Zerodha's form (locked decision #4).

**Method / Path.** `GET /r/{client_id}`

**Auth.** None (public).

**Path parameters.**
| Name | Type | Required | Description |
|---|---|---|---|
| `client_id` | string | yes | The referrer's **raw Zerodha `client_id`**, e.g. `RJ4521`. Used directly as `r=` — there is no token and no mapping lookup (ADR-001). |

**Query parameters (all optional, captured for attribution analytics).**
| Name | Type | Description |
|---|---|---|
| `utm_source` | string | Campaign source, e.g. `whatsapp`, `facebook`, `instagram`, `linkedin`, `x`, `email`, `status`. |
| `utm_campaign` | string | Campaign identifier. |
| `utm_medium` | string | Optional medium. |
| `preview` | boolean | If `true`, logs the click as `internal` and does not count it in analytics — but **only** when the request carries a **valid, logged-in GoRefer admin session** (§3.1). A present-but-invalid `Authorization` header is not enough; a request lacking a valid admin session is treated as an ordinary public click, and `preview` is ignored (ADR-023). |

**Behavior (ordered).**
1. **Format-validate** `client_id` against the regex below (reject empty, oversized, or illegal-char values → branded error page, no DB work). **No ownership verification** — there is no Zerodha API to confirm the id belongs to a real client; GoRefer accepts and redirects (a wrong id simply fails to credit that referrer; `c=ZMPHZC` still credits PIFS). Then **lazily create-or-find** the `referral_identity` keyed by `(partner=Zerodha, client_id, id_source=native)` and its `referral_journey`, both from config — nothing was pre-loaded.
2. Derive request signals: IP, `User-Agent`, `Referer`, `Accept` headers, device class, and timing.
3. **Classify the click** into a confidence band (see §4.4) — `human_high`, `human_likely`, `suspicious`, or `bot` — and write a `click_event` row (see 05-Database-Design) with the classification, UTM values, device, browser, and a **hashed** IP. The row carries **`is_bot`** (set from the known bot/preview user-agent list) and **`is_confirmed_human = false`**; it flips to human **only** when the JS-confirmation **beacon** (`POST /api/click/confirm`, §4.3) fires. Bot/preview hits are stored for audit but excluded from human counts (Gap 16).
4. Start or extend the **referral journey**: if this is the first observed event for this link+visitor, create a `referral_journey_event` of type `LINK_CLICKED`; the journey key is the link plus a first-party visitor cookie (`gr_vid`, `HttpOnly` not required since it is not sensitive) so repeat clicks are stitched to one journey.
5. **Landing decision** (per `referral_program.landing_mode`, defined in 05-Database-Design):
   - `redirect_now` → skip the landing page and go straight to step 6.
   - `show_landing` → **302** to `GET /landing/{client_id}` (the HTML page whose data is served by §5.2), preserving UTM params. The visitor sees the branded PIFS page and clicks **Continue**, which returns to `GET /r/{client_id}?continue=1` to perform step 6. `continue=1` is logged as `LANDING_CONTINUE`.
6. **Redirect to Zerodha.** Build the destination server-side (the partner code is **injected server-side** and never exposed to the client until this 302's `Location`):
   `https://signup.zerodha.com/api/lead?c=ZMPHZC&r={client_id}` — where `{client_id}` is the raw value from the path (Option A: `r=` is always preserved so the referrer stays credited — locked decision #2). Respond **302 Found** with that `Location`, and write a `referral_journey_event` of type `REDIRECTED_TO_PARTNER`.

**reCAPTCHA reality (mandatory note).** GoRefer **never** submits Zerodha's form. Step 6 only issues an HTTP redirect that lands a *real human browser* on Zerodha's own reCAPTCHA-gated, lead-capture-only page. Zerodha's page ends at a "thanks, we'll contact you" screen; full KYC is completed later by a human (Ashok) on a call. Any attempt to auto-fill or auto-submit that form is prohibited (Build-Spec locked decision #4; compliance + account risk).

**Success responses.**
- `302 Found` with `Location: https://signup.zerodha.com/api/lead?c=ZMPHZC&r=<client_id>` (direct-redirect mode), **or**
- `302 Found` with `Location: /landing/<client_id>` (landing mode), **or**
- `200 OK` branded error HTML if the `client_id` fails format validation.

**Response headers.**
- `Set-Cookie: gr_vid=<uuid>; Path=/; Max-Age=5184000; SameSite=Lax` (60-day visitor cookie — mirrors Zerodha's 60-day attribution window so a journey can be stitched across the whole eligible period).
- `Cache-Control: no-store` (must re-run classification and logging on every hit).
- `X-Request-Id`.

**Example — direct redirect**
```
GET /r/RJ4521?utm_source=whatsapp&utm_campaign=jul_refer HTTP/1.1
Host: gorefer.in
User-Agent: Mozilla/5.0 (Linux; Android 14; ...) ...

HTTP/1.1 302 Found
Location: https://signup.zerodha.com/api/lead?c=ZMPHZC&r=DA1707
Set-Cookie: gr_vid=6f1c...; Path=/; Max-Age=5184000; SameSite=Lax
X-Request-Id: req_8f3a2c9e
Cache-Control: no-store
```

**Validation.**
- `client_id` must match `^[A-Za-z0-9]{4,16}$` (a Zerodha client id shape). A malformed `client_id` short-circuits to the branded error page (no DB work). This is **format validation only** — GoRefer cannot and does not verify that the id belongs to a real Zerodha client.

**Errors.**
| Status | code | When |
|---|---|---|
| 200 (HTML) | `INVALID_CLIENT_ID` (rendered) | The path segment fails format validation. Friendly page with a "Open a Zerodha account with PIFS" fallback CTA to `/r/open` (the partner-only link). |
| 429 | `RATE_LIMITED` | IP over the per-minute cap. |
| 503 | `PARTNER_UNAVAILABLE` | Destination cannot be built (config missing). Rendered as branded HTML with retry guidance. |

> **Note — the partner-only link.** `GET /r/open` is the same handler with a reserved path segment (`open`) that carries no `r=` (plain `c=ZMPHZC`, injected server-side). It credits PIFS as AP but no referrer (Build-Spec R2). It is documented here as a reserved path, not a separate route.

### 4.2 `GET /open` — partner-direct (no referrer)
**Purpose.** The **PIFS-direct** entry point for a visitor who arrives with **no referrer** (Gap 1). It is a sibling of §4.1 that carries the partner code **only** — `c=ZMPHZC`, **no `r=`** — credits PIFS as AP but no referrer, and **creates a partner-direct journey**.

**Method / Path.** `GET /open` (also reachable as the reserved `GET /r/open`; both resolve to the partner-direct handler).

**Auth.** None (public).

**Query parameters.** Same optional `utm_*` / `preview` as §4.1. There is **no `client_id`** path segment.

**Behavior (ordered).**
1. **No format-validation of a referrer is needed** (there is no `r=`). Lazily create-or-find the **partner-direct journey** with `source=partner_direct` and `referrer = null` (05-Database-Design, `referrals.source`).
2. Derive request signals; set the `gr_vid` visitor cookie; classify the click and apply **bot-UA filtering** exactly as §4.1 (a click only counts human after the §4.3 beacon).
3. Show the branded landing page in `show_landing` mode — the **partner-direct variant** (no referral-id echo; the WhatsApp-share prefill omits the referral id and the eventual redirect omits `r=`).
4. **Redirect** server-side to `https://signup.zerodha.com/api/lead?c=ZMPHZC` (**no `r=`**). Write a `REDIRECTED_TO_PARTNER` journey event.

**Success responses.** `302 Found` to the landing page or, in direct mode, to `https://signup.zerodha.com/api/lead?c=ZMPHZC` (no `r=`). Sets the same `gr_vid` cookie and `Cache-Control: no-store` as §4.1.

**Notes.** A partner-direct journey can still convert: the Zoho sync (§7) will attribute it **referrer-level-only / PIFS-only** since there is no referrer to credit (Gaps 2, 3).

### 4.3 `POST /api/click/confirm` — human-confirmation beacon
**Purpose.** Turn a raw click into a **confirmed human** click (Gap 16). The redirect (§4.1) and partner-direct (§4.2) handlers log every hit, but a hit is counted as human **only after** this JS beacon fires from a real browser that executed page JavaScript — bot/preview crawlers do not run JS and never send it.

**Method / Path.** `POST /api/click/confirm`

**Auth.** None (public), but **bound to a server-issued one-time nonce**; rate-limited and bot-checked. The nonce is minted server-side when the click is first logged (§4.1/§4.2) and handed to the page JS; the beacon must echo it back. A beacon carrying a **forged, absent, expired, or already-used** nonce is **rejected** and does not flip the click to human — client-supplied `visitor_id` + `client_id` alone are not trusted (ADR-022). A successful confirmation consumes the nonce and also unlocks the beacon-gated name reveal (§5.2.1), which reuses the same nonce.

**Request body.**
```json
{ "client_id": "RJ4521", "visitor_id": "6f1c...", "event_ref": "evt_abc123", "nonce": "n_9f2a..." }
```

**Field rules.**
| Field | Type | Required | Validation |
|---|---|---|---|
| `client_id` | string | conditional | The referrer `client_id`; **omitted for partner-direct** (`GET /open`) journeys. |
| `visitor_id` | string | yes | The `gr_vid` cookie value; ties the beacon to the click that set it. |
| `event_ref` | string | no | Correlates to the original `click_event`; if absent, matched by `visitor_id` + recency. |
| `nonce` | string | yes | The fresh, single-use server-issued nonce minted when the click was logged. Rejected if forged, absent, expired, or already consumed. |

**Behavior.** Verifies the `nonce` first; on a valid, unused nonce, locates the pending `click_event` by `visitor_id` (+ `event_ref` when present) and sets **`is_confirmed_human = true`** on the event (05-Database-Design §12.1), consuming the nonce. Idempotent — repeat beacons for the same event are no-ops. Clicks whose beacon never arrives (or arrive without a valid nonce) stay `is_confirmed_human = false` and are **excluded from human counts** (stored for audit). Known-bot UAs are rejected outright with `is_bot = true`.

**Success response — 202**
```json
{ "confirmed": true }
```

**Errors.** `401 UNAUTHENTICATED` (forged/absent/expired/consumed nonce), `422 VALIDATION_FAILED`, `429 RATE_LIMITED`.

### 4.4 Click confidence classification
Every click is stamped with a confidence band so analytics can separate real human interest from scraper/preview traffic (WhatsApp/Facebook link-preview bots hit referral links heavily). Classification inputs: User-Agent against a known-bot list, presence/plausibility of `Accept`/`Accept-Language`, whether the request carries the `gr_vid` cookie on a repeat hit, request timing, and IP reputation.

| Band | Meaning | Counted in headline analytics? |
|---|---|---|
| `human_high` | Real browser signals, cookie round-trip observed. | Yes |
| `human_likely` | Real-browser-shaped but first hit / no cookie yet. | Yes |
| `suspicious` | Datacenter IP or thin headers; ambiguous. | Flagged, shown separately |
| `bot` | Known crawler/preview UA (e.g. WhatsApp, facebookexternalhit). | Excluded from headline metrics |

The classification is stored on the `click_event`; the redirect still happens for every band (a real user behind a preview bot must not be blocked).

---

## 5. Public Endpoints — Landing & Capture

### 5.1 Overview
When a program is in `show_landing` mode the visitor sees a branded **PIFS** page (never a Zerodha clone — locked decision #5). The page HTML is static/edge-served; its dynamic content (referrer's first name, reward wording, disclosure block) comes from §5.2. The "Need help?" form posts to §5.3.

### 5.2 `GET /api/landing/{client_id}`
**Purpose.** Return the data needed to render the branded landing page for a given referrer `client_id` — without exposing any Zerodha URL or the partner code. The page is configured **per partner** (Sprint 1 = Zerodha), so its content/buttons come from the partner's landing config.

**Method / Path.** `GET /api/landing/{client_id}`

**Auth.** None (public).

**Path parameters.**
| Name | Type | Required | Description |
|---|---|---|---|
| `client_id` | string | yes | The referrer's raw Zerodha `client_id` (ADR-001). |

**Referrer name is not returned on initial load.** Because `client_id` values are the raw (and therefore guessable) Zerodha ids, returning the referrer's real first name on this unauthenticated endpoint would let anyone enumerate an id→name map (ADR-021). The initial response is therefore **generic** — it carries `has_referrer` but **no `first_name`**. The referrer's first name is revealed **only** by the follow-up call in §5.2.1, which requires a valid, fresh server-issued nonce obtained **after** the human-confirmation beacon (§4.3) completes. This endpoint is additionally **rate-limited and bot-filtered** so bulk enumeration is economically impractical; the residual first-name-only exposure to a confirmed human is a consciously accepted risk. The short referral link is kept — there is no signed-parameter link bloat.

**Success response — 200**
```json
{
  "client_id": "RJ4521",
  "program": {
    "name": "Zerodha",
    "display_name": "Open your Zerodha account with PIFS"
  },
  "referrer": {
    "has_referrer": true
  },
  "benefits": [
    "Zero account-opening charges",
    "Fast, fully digital KYC",
    "Trusted by millions of investors",
    "Powerful trading platforms"
  ],
  "reward_note": "Referral rewards are governed by Zerodha's Refer & Earn program. T&C apply.",
  "continue_url": "/r/RJ4521?continue=1",
  "help": {
    "enabled": true,
    "helpline": "+91 70806 42020"
  },
  "disclosure": "Zerodha Broking Ltd.: SEBI Registration no.: INZ000031633 | Passive Income Financial Solutions Private Limited | NSE AP reg. no.: AP2516003693",
  "risk_warning": "Investments in securities market are subject to market risks, read all the related documents carefully before investing."
}
```

**Notes.**
- The `referrer` object carries **only** `has_referrer` on initial load — no `first_name` (see the name-reveal note above and §5.2.1).
- `continue_url` points back at `GET /r/{client_id}?continue=1` — the client never sees the Zerodha destination; the server builds it at redirect time.
- `reward_note` wording is served from a single config value so the "10%/300 points" claim can be pulled or reworded in one place if NSE reinstates the ban (Build-Spec §7.1 — keep the claim swappable). The exact incentive figures are intentionally rendered from config, not hardcoded in the client.
- `help.helpline` resolves from config through the 3-tier cascade (central → global → user); the central default is the **WATI business number `+91 70806 42020`**, never Ashok's personal number.
- `disclosure` and `risk_warning` are mandatory on every rendered asset (compliance gate).

**Validation.** Same `client_id` regex as §4.1.

**Errors.**
| Status | code | When |
|---|---|---|
| 400 | `INVALID_CLIENT_ID` | `client_id` fails format validation (JSON here, since this is the data API). |
| 429 | `RATE_LIMITED` | Over cap. |

### 5.2.1 `GET /api/landing/{client_id}/referrer` — beacon-gated name reveal
**Purpose.** Return the referrer's first name for personalising the landing page, but **only** to a real human who has cleared the confirmation beacon — closing the id→name enumeration hole (ADR-021).

**Method / Path.** `GET /api/landing/{client_id}/referrer`

**Auth.** None (public), but **nonce-gated**: the request must carry a valid, fresh, single-use nonce issued by the server after the human-confirmation beacon (§4.3) fired for this visitor. The nonce is the same one-time nonce mechanism used to bind the beacon itself (§4.3). Requests with a missing, expired, forged, or already-used nonce are rejected. Rate-limited and bot-filtered as §5.2.

**Query parameters.**
| Name | Type | Required | Description |
|---|---|---|---|
| `nonce` | string | yes | The fresh, single-use server-issued nonce tied to this visitor's confirmed-human beacon. |

**Success response — 200**
```json
{ "first_name": "Abhay", "has_referrer": true }
```

**Errors.**
| Status | code | When |
|---|---|---|
| 401 | `UNAUTHENTICATED` | Nonce missing, expired, forged, or already consumed. |
| 400 | `INVALID_CLIENT_ID` | `client_id` fails format validation. |
| 429 | `RATE_LIMITED` | Over cap. |

### 5.3 `POST /api/leads`
**Purpose.** Capture-first lead intake (Build-Spec locked decision #1). Creates a lead in GoRefer, mirrors it to Zoho CRM, and starts/extends the referral journey — **before** any hand-off to Zerodha, so the lead is never lost even if the person abandons Zerodha's form. Fires the downstream Wati messages (to Ashok, to the new person, and — only if resolvable — to the referrer) via the integration layer.

**Method / Path.** `POST /api/leads`

**Auth.** None (public), but heavily rate-limited (§2.3) and bot-checked.

**Request body.**
```json
{
  "client_id": "RJ4521",
  "name": "Rahul Sharma",
  "mobile": "9876543210",
  "email": "rahul@example.com",
  "city": "Prayagraj",
  "source": "landing_need_help",
  "submitted_by": "friend",
  "consent": true,
  "utm_source": "whatsapp",
  "utm_campaign": "jul_refer"
}
```

**Field rules.**
| Field | Type | Required | Validation |
|---|---|---|---|
| `client_id` | string | yes | `client_id` regex (§4.1); the raw referrer id. Reserved value `open` allowed (partner-only lead, no referrer). |
| `name` | string | yes | 2–80 chars, letters/spaces/dots. |
| `mobile` | string | yes | 10-digit Indian mobile `^[6-9]\d{9}$`; normalized to `91XXXXXXXXXX` server-side (matches the Wati/Zoho normalization). |
| `email` | string | no | RFC-5322-lite; optional per capture-first minimal-friction goal. |
| `city` | string | conditional | Required only when `source = landing_need_help` if the canonical schema keeps City. **The 2-field (Name/Mobile) vs 3-field (Name/Mobile/City) schema is an OPEN source-doc conflict (Foundation/Build-Spec) — reconcile before build.** Until then the API accepts `city` as optional and validation is config-driven. |
| `source` | enum | yes | One of `landing_need_help`, `whatsapp_bot`, `manual`, `direct_link`. Maps to `referral_lead.source`. |
| `submitted_by` | enum | yes | `friend` (visitor filled own details — clean opt-in) or `referrer` (referrer filled friend's details — opt-in risk; first Wati message must be warm utility, not marketing). |
| `consent` | boolean | yes | Must be `true`; records WhatsApp/contact consent for DPDP + Meta opt-in hygiene. |
| `utm_*` | string | no | Attribution. |

**Behavior (ordered — capture-first).**
1. Validate; take `client_id` directly as the referrer (or the reserved `open` for partner-only). This is the **"Continue to Zerodha"** form submit from the landing page.
2. **Persist the lead in GoRefer first** (`referral_lead` row, status `NEW`, referrer = the `client_id` from the URL, partner = `ZMPHZC`). This write is the source of truth and must succeed before any external call. After it succeeds, the client is redirected to `signup.zerodha.com/api/lead?c=ZMPHZC&r={client_id}` (auto-filling Zerodha's own form with the captured name/email/phone is an OPEN build-time POC, **not** a dependency — the lead is captured regardless).
3. Mirror to **Zoho CRM** (lead pipeline). Zoho failure does **not** fail the request — it is retried asynchronously; the response still returns 201 because the lead is safely captured locally.
4. Append `referral_journey_event` of type `LEAD_CREATED`.
5. Enqueue the **three Wati messages** (each a Meta-approved template): (a) alert Ashok, (b) warm utility notice to the new person naming the referrer + a continue link that keeps `r=`, (c) thank-you to the referrer **only if** their phone is resolvable from Zoho. Enqueue is async. **WATI delivery is a prerequisite and is verified from WATI's terminal delivery status, never HTTP 200 (Gap 12); GoRefer consumes that delivery status and records it on the journey** (the `WATI_NOTIFIED` event's `delivery` field — see §6.4 timeline). A message that fails to deliver leaves the funnel flagged, not silently lost.
6. Return **201**.

**Success response — 201**
```json
{
  "lead_id": "lead_7Yb2Qk",
  "status": "NEW",
  "journey_client_id": "RJ4521",
  "next": {
    "continue_url": "/r/RJ4521?continue=1",
    "message": "Thanks! Our representative will call to help you open your Zerodha account."
  }
}
```

**Validation errors — 422**
```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "One or more fields are invalid.",
    "details": [
      { "field": "mobile", "issue": "Must be a 10-digit Indian mobile number." },
      { "field": "consent", "issue": "Consent is required." }
    ],
    "request_id": "req_1a2b3c"
  }
}
```

**De-duplication.** If the same `mobile` + `client_id` arrives within 24h, the existing lead is returned with `201`-equivalent `200 OK` and `status` unchanged, and no duplicate Wati messages fire (directly addresses the duplicate-send problem noted in the Wati failure analysis). If the **same mobile arrives within 24h under a *different* `client_id`** (a second referrer of the same prospect), the active lead is **not** duplicated, but a **`REFERRER_B_ATTEMPT`** journey event is recorded against the prospect so the second referrer is logged, not silently swallowed — giving an audit trail for referral-overlap disputes. Final credit still follows Zoho single-winner attribution (§7.1); GoRefer never picks a winner from this attempt log.

**Errors.**
| Status | code | When |
|---|---|---|
| 422 | `VALIDATION_FAILED` | Bad/missing fields. |
| 400 | `INVALID_CLIENT_ID` | Referrer `client_id` fails format validation. |
| 409 | `DUPLICATE_LEAD` (soft) | Returned as 200 with existing lead; hard 409 only if a conflicting record exists. |
| 429 | `RATE_LIMITED` | Over cap. |

### 5.4 `POST /api/share`
**Purpose.** Record that a person shared/forwarded referral details on a given channel, so "links shared" analytics (Foundation Spec §6.12) are real and per-channel, not guessed. This backs the landing page's **"Share referral details on WhatsApp"** button.

**Method / Path.** `POST /api/share`

**Auth.** None (public) — called from share buttons on referral assets; rate-limited.

**Request body.**
```json
{
  "client_id": "RJ4521",
  "channel": "whatsapp"
}
```

**Field rules.**
| Field | Type | Required | Validation |
|---|---|---|---|
| `client_id` | string | yes | `client_id` regex; the raw referrer id. |
| `channel` | enum | yes | `whatsapp`, `whatsapp_status`, `facebook`, `instagram`, `linkedin`, `x`, `email`, `copy_link`, `qr`. |

**Behavior.** Writes a `referral_journey_event` (type `LINK_SHARED`; for `channel = whatsapp` from the landing button, the event subtype is **`SharedOnWhatsApp`**) with the channel and appends to share analytics.

> **WhatsApp-share is a client-side deep link to the WATI business number (Gap 13).** The "Share referral details on WhatsApp" button is a **client-side `wa.me` deep link** to the **WATI business number** (the WhatsApp Business API number PIFS operates), pre-filled with **referring** language + the referral id — e.g. `https://wa.me/{wati_business_number}?text=Hi%2C%20I'd%20like%20to%20refer%20someone%20for%20a%20Zerodha%20account.%20Referral%20ID%3A%20{client_id}`. Tapping it fires this `POST /api/share` (emitting `SharedOnWhatsApp`) and then opens WhatsApp. Because the inbound lands on the **WATI business number** carrying the referral id, it is **auto-attributed** to the journey via Wati → a Zoho lead, reconciled by referral id + mobile. For a **partner-direct** share (`GET /open`) the prefill **omits the referral id**. **Accepted downside:** the user can edit the pre-filled text before sending, so this path's attribution is high-but-not-perfect.

**Success response — 202**
```json
{ "recorded": true, "channel": "whatsapp" }
```

**Errors.** `422 VALIDATION_FAILED`, `400 INVALID_CLIENT_ID`, `429 RATE_LIMITED`.

---

## 6. Admin Endpoints

All require a valid admin JWT (§3.1). All are read-heavy; Sprint 1 admin is operational visibility, not data entry.

### 6.1 `POST /api/auth/login`
**Purpose.** Authenticate the single bootstrap administrator and issue a session.

**Auth.** None (this is how you get a session).

**Request body.**
```json
{ "email": "admin@example.com", "password": "••••••••" }
```

**Field rules.** `email` required, valid email; `password` required, 8–128 chars.

**Behavior.** Verify against `admin_user` (password stored as Argon2/bcrypt hash). On success create an `admin_session`, return access JWT + set refresh cookie. On failure increment the per-account failure counter (lockout after 10).

**Success response — 200**
```json
{
  "access_token": "<compact JWS: header.payload.signature>",
  "token_type": "Bearer",
  "expires_in": 900,
  "admin": { "id": "adm_1", "name": "Abhay Kumar Maurya", "role": "admin" }
}
```
Plus `Set-Cookie: gr_refresh=...; HttpOnly; Secure; SameSite=Strict; Max-Age=604800; Path=/api/auth`.

**Errors.**
| Status | code | When |
|---|---|---|
| 401 | `INVALID_CREDENTIALS` | Wrong email/password. |
| 423 | `ACCOUNT_LOCKED` | Too many failures; `Retry-After` returned. |
| 422 | `VALIDATION_FAILED` | Malformed body. |
| 429 | `RATE_LIMITED` | Over the 5/15-min cap. |

**Companion auth endpoints (same family).**
- `POST /api/auth/refresh` — refresh cookie → new access JWT (rotates refresh). Errors: `401 UNAUTHENTICATED`.
- `POST /api/auth/logout` — revokes current session. `204 No Content`.
- `GET /api/auth/me` — returns the current admin profile. `200` / `401`.

> **Bootstrap.** The first admin is provisioned by a one-time seed (env-configured email + password hash), not via a public sign-up endpoint. There is no self-registration in Sprint 1 (Foundation Spec — no public registration). Any other person hitting the login page is told access is by invitation only (see 07-UI-UX §Login).

### 6.2 `GET /api/admin/dashboard`
**Purpose.** The operational at-a-glance panel: fresh activity the admin acts on — new clicks, new leads, new contacts (account-opening events synced from Zoho).

**Auth.** Admin JWT.

**Query parameters.**
| Name | Type | Default | Description |
|---|---|---|---|
| `range` | enum | `today` | `today`, `7d`, `30d`, `custom`. |
| `from`,`to` | date | — | Required if `range=custom`. |

**Success response — 200**
```json
{
  "range": "today",
  "generated_at": "2026-07-04T09:30:00Z",
  "totals": {
    "clicks": 143,
    "human_clicks": 121,
    "bot_clicks": 22,
    "leads": 18,
    "redirects_to_partner": 96,
    "accounts_opened": 4
  },
  "funnel": [
    { "stage": "LINK_SHARED", "count": 210 },
    { "stage": "LINK_CLICKED", "count": 143 },
    { "stage": "LANDING_VIEWED", "count": 88 },
    { "stage": "REDIRECTED_TO_PARTNER", "count": 96 },
    { "stage": "LEAD_CREATED", "count": 18 },
    { "stage": "ACCOUNT_OPENED", "count": 4 }
  ],
  "recent_leads": [
    { "lead_id": "lead_7Yb2Qk", "name": "Rahul Sharma", "mobile_masked": "98•••••210", "referrer": "Abhay (DA1707)", "status": "NEW", "created_at": "2026-07-04T09:05:00Z" }
  ],
  "top_referrers": [
    { "participant": "Abhay", "client_id_masked": "DA••07", "leads": 6, "clicks": 40 }
  ],
  "sync_health": {
    "last_successful_zoho_sync_at": "2026-07-04T09:26:00Z",
    "zoho_status": "ok",
    "wati_status": "ok"
  }
}
```

**Notes.** Mobile numbers and client IDs are **masked** in list responses; full values appear only on the single-journey detail endpoint (§6.4) and are access-logged. `accounts_opened` is populated only from Zoho sync (§7) — GoRefer never fabricates it (Foundation Spec principle 4).

**Sync freshness.** The `sync_health` block guards against **fabrication-by-omission** (data that looks current but isn't when the Zoho worker stalls). It carries `last_successful_zoho_sync_at` (the dashboard renders this as e.g. "Zoho synced 4 min ago ✓ / 2 days ago ⚠") plus a WATI health signal; `zoho_status`/`wati_status` flip to a warning state once staleness exceeds the configured threshold. It pairs with the sync worker (§7) and the per-event source labels (§6.4).

**Errors.** `401 UNAUTHENTICATED`, `403 FORBIDDEN`, `422 VALIDATION_FAILED` (bad custom range).

### 6.3 `GET /api/admin/referrals`
**Purpose.** The Referral Explorer backing endpoint — a filterable, paginated list of referral journeys.

**Auth.** Admin JWT.

**Query parameters (all optional, combinable).**
| Name | Type | Description |
|---|---|---|
| `partner` | string | Program filter. Sprint 1: only `zerodha`. |
| `referrer` | string | Referrer participant name or client_id (exact or prefix). |
| `customer` | string | Lead name (partial match). |
| `mobile` | string | Lead mobile (exact, normalized). |
| `campaign` | string | `utm_campaign`. |
| `status` | enum | `NEW`, `CONTACTED`, `INTERESTED`, `KYC_STARTED`, `ACCOUNT_OPENED`, `REJECTED`. |
| `from`,`to` | date | Created-at window. |
| `sort` | enum | `created_desc` (default), `created_asc`, `status`. |
| `page` | int | 1-based; default 1. |
| `page_size` | int | default 25, max 100. |

**Success response — 200**
```json
{
  "filters_echo": { "partner": "zerodha", "status": "NEW", "from": "2026-07-01" },
  "page": 1,
  "page_size": 25,
  "total": 137,
  "results": [
    {
      "client_id": "RJ4521",
      "lead_id": "lead_7Yb2Qk",
      "customer_name": "Rahul Sharma",
      "mobile_masked": "98•••••210",
      "referrer_name": "Abhay",
      "referrer_client_id_masked": "DA••07",
      "campaign": "jul_refer",
      "source": "landing_need_help",
      "status": "NEW",
      "first_click_at": "2026-07-04T08:40:00Z",
      "created_at": "2026-07-04T09:05:00Z",
      "last_event": "LEAD_CREATED"
    }
  ]
}
```

**Example rows** (illustrative of the list the Referral Explorer renders — the `client_id` **is** the referrer's raw Zerodha id from the path):
| client_id | prospect | referrer | campaign | status | last event |
|---|---|---|---|---|---|
| DA1707 | Rahul Sharma | Abhay (DA••07) | jul_refer | NEW | LEAD_CREATED |
| SU9914 | Priya Verma | Sunita (SU••14) | status_jul | KYC_STARTED | ACCOUNT_STATUS_IMPORTED |
| DA1707 | (no lead yet) | Abhay (DA••07) | fb_jul | — | REDIRECTED_TO_PARTNER |

**Errors.** `401`, `403`, `422 VALIDATION_FAILED` (bad enum/date/page_size).

### 6.4 `GET /api/admin/referrals/{client_id}`
**Purpose.** The Referral Journey detail — the full chronological timeline of every event for one referral link/lead, for support and attribution audits.

**Auth.** Admin JWT.

**Path parameters.** `client_id` (the referrer's raw Zerodha `client_id`).

**Success response — 200**
```json
{
  "client_id": "RJ4521",
  "program": "Zerodha",
  "referrer": { "name": "Abhay", "client_id": "DA1707" },
  "lead": {
    "lead_id": "lead_7Yb2Qk",
    "name": "Rahul Sharma",
    "mobile": "9876543210",
    "email": "rahul@example.com",
    "city": "Prayagraj",
    "source": "landing_need_help",
    "submitted_by": "friend",
    "status": "KYC_STARTED"
  },
  "timeline": [
    { "seq": 1, "type": "LINK_SHARED", "channel": "whatsapp", "at": "2026-07-04T08:10:00Z" },
    { "seq": 2, "type": "LINK_CLICKED", "confidence": "human_high", "device": "Android", "browser": "Chrome", "utm_source": "whatsapp", "at": "2026-07-04T08:40:00Z" },
    { "seq": 3, "type": "LANDING_VIEWED", "at": "2026-07-04T08:40:20Z" },
    { "seq": 4, "type": "LEAD_CREATED", "source": "landing_need_help", "at": "2026-07-04T09:05:00Z" },
    { "seq": 5, "type": "WATI_NOTIFIED", "recipient": "ashok", "template": "gorefer_new_lead_alert", "delivery": "delivered", "at": "2026-07-04T09:05:30Z" },
    { "seq": 6, "type": "REDIRECTED_TO_PARTNER", "at": "2026-07-04T09:07:00Z" },
    { "seq": 7, "type": "ACCOUNT_STATUS_IMPORTED", "status": "KYC_STARTED", "source": "zoho", "at": "2026-07-04T14:20:00Z" }
  ]
}
```

**Notes.** This is the one place unmasked `mobile`/`client_id` are returned; access is logged (who/when) for DPDP accountability. Each timeline entry carries its origin (`gorefer` vs `zoho` vs `wati`), so externally-sourced facts are never confused with GoRefer-observed events (principle 4).

**Errors.** `401`, `403`, `404 REFERRAL_NOT_FOUND` (no journey exists for this `client_id` — e.g. the link was never clicked, so lazy creation never ran).

---

## 7. Integration Endpoint — Zoho Account-Status Sync

The inbound webhook below feeds a **Zoho status-sync worker** (built in M6): it maintains a **watermark** (resume point) so no update is missed, routes updates that fail to apply to a **dead-letter / problem tray** for retry without loss, and **auto-creates off-platform / zero-click conversions** (ADR-016). Combined with the `update_id` idempotency guard (§7.1), delivery is **exactly-once** — normal duplicate webhook deliveries process once. The Zoho-API "pull"/polling fallback is deferred (backlog DF-1); the worker processes the webhook reliably for now.

### 7.1 `POST /api/integrations/zoho/account-status`
**Purpose.** Bring externally-verified account-opening progress back into GoRefer. GoRefer can observe clicks and redirects but **cannot** verify KYC/account approval itself (Foundation Spec principle 4); those facts originate in Zoho and are pushed here. Each import is recorded as a journey event tagged `source: zoho`.

**Method / Path.** `POST /api/integrations/zoho/account-status`

**Auth.** Service key (§3.2): `X-GoRefer-Service-Key`, restricted to Zoho's server IPs by allowlist — the interim minimum until the HMAC "wax-seal" lands (deferred, DF-2).

**Request body.**
```json
{
  "update_id": "zoho_evt_00912",
  "opener_name": "Rahul Sharma",
  "opener_zerodha_id": "RA8842",
  "referrer_zerodha_id": "RJ4521",
  "journey_ref": "grj_7Yb2Qk",
  "status": "ACCOUNT_OPENED",
  "disposition": "opened_via_referral",
  "occurred_at": "2026-07-04T14:20:00Z",
  "account_opened_at": "2026-07-03T11:05:00Z",
  "source": "zoho",
  "meta": { "zoho_record_id": "60019670093-1234", "module": "Contacts" }
}
```

**Field rules.**
| Field | Type | Required | Validation |
|---|---|---|---|
| `update_id` | string | yes | Idempotency key (unique Zoho update id, or a composite `account+referrer+date` fallback); a repeat `update_id` is a no-op returning 200, guarded by the ingest idempotency table (§7, ADR-008-adjacent — matrix #8). |
| `opener_name` | string | no | The account-opener's **name** (best-effort opener→journey link). Conversion data carries **no mobile**. |
| `opener_zerodha_id` | string | yes | The opener's **Zerodha account id** — always present in the conversion data; the **unique upsert key** for the conversion record (one per account, so an account can never become two journeys). |
| `referrer_zerodha_id` | string | no | **The single winning referrer (Gap 3), matched/credited by Zerodha client id** (= the raw `client_id` in the referral link, ADR-001). GoRefer writes this to `referrals.credited_referrer` **verbatim** — Zoho is authoritative; GoRefer never guesses a winner from last redirect/click, and never matches by mobile. Absent/empty ⇒ **no referrer credited** (e.g. partner-direct / PIFS-only). |
| `journey_ref` | string | no | Preferred opener→journey join reference: the GoRefer journey-reference stamped on the Zoho lead and echoed back here (feasibility confirmed at M6). When present it links the conversion to the exact click-journey; else fall back to `opener_name`, else record the conversion under the referrer only. |
| `status` | enum | yes | `CONTACTED`, `INTERESTED`, `KYC_STARTED`, `ACCOUNT_OPENED`, `REJECTED`. Mapped to a GoRefer stage via the published status map below. |
| `disposition` | string | no | The un/converted **reason** (Gap 8); stored to `lead_disposition`. |
| `occurred_at` | timestamp | yes | When this status change was recorded in Zoho (drives `*_synced_at`). |
| `account_opened_at` | timestamp | conditional | The **true account-opening date** (Gap 4b); required when `status = ACCOUNT_OPENED`. Stored **distinct from** `occurred_at`/`synced_at`; **all conversion analytics run off this real date**, not sync time. |
| `source` | string | yes | Must be `zoho` in Sprint 1 (the imported-event `source`). |

**Zoho-status → GoRefer-stage map.** Past the `REDIRECTED_TO_PARTNER` stage, **Zoho is the sole authority** — GoRefer mirrors the mapped stage and **never advances a stage on its own**:

| Zoho `status` | GoRefer stage |
|---|---|
| `CONTACTED` | `CONTACTED` |
| `INTERESTED` | `INTERESTED` |
| `KYC_STARTED` | `KYC_STARTED` |
| `ACCOUNT_OPENED` | `ACCOUNT_OPENED` (terminal by default) |
| `REJECTED` | `REJECTED` |

A **`REWARDED`** stage is reachable **only if** Zoho supplies a reward signal to mirror; the **default terminal stage is `ACCOUNT_OPENED`**. Reward amounts live only in the Zerodha Console — GoRefer never computes or fabricates them (Gap 4/7).

**Behavior.** Dedupe on `update_id` (idempotency guard, §7). Match to an existing `referral_lead`/journey by `journey_ref` when present, else best-effort by `opener_name`; the conversion record is upserted on the opener's **Zerodha account id** (`opener_zerodha_id`) so overlapping/lazy loads can never split one account into two journeys. The **referrer is matched/credited only by `referrer_zerodha_id`** — never by mobile (conversion data has no mobile). If matched, apply the mapped stage, set `credited_referrer` (from `referrer_zerodha_id`) and `account_opened_at`, mirror `disposition` to `lead_disposition`, and append a `referral_journey_event` of type `ACCOUNT_STATUS_IMPORTED` with `source: zoho`. **If no match, this is an off-platform / no-click conversion (Gap 3b): create a new `referral` with `source=zoho_import` and no click rows** (rather than dropping it) and flag it in the dashboard. **Reward status is never written here** — reward truth lives only in the Zerodha Console (Gap 4/7).

**Success response — 200**
```json
{ "matched": true, "lead_id": "lead_7Yb2Qk", "new_status": "KYC_STARTED", "update_id": "zoho_evt_00912" }
```
Unmatched:
```json
{ "matched": false, "stored_as": "unlinked_status_event", "update_id": "zoho_evt_00912" }
```

**Errors.**
| Status | code | When |
|---|---|---|
| 401 | `UNAUTHENTICATED` | Bad/missing service key, or source IP not on the Zoho allowlist. |
| 422 | `VALIDATION_FAILED` | Bad status enum / timestamp. |
| 409 | `DUPLICATE_EVENT` (soft) | Repeat `update_id` → 200 no-op (idempotent). |
| 429 | `RATE_LIMITED` | Over cap. |

> **Direction.** This endpoint is Zoho→GoRefer (inbound). The complementary GoRefer→Zoho lead mirror in §5.3 is an outbound call GoRefer makes to Zoho's own API and is specified in 04-System-Architecture (integration layer), not here.

---

## 8. Error Code Reference

| HTTP | `code` | Meaning |
|---|---|---|
| 400 | `BAD_REQUEST` | Malformed JSON / unparseable body. |
| 401 | `UNAUTHENTICATED` | Missing/invalid/expired credentials. |
| 401 | `INVALID_CREDENTIALS` | Login: wrong email/password. |
| 403 | `FORBIDDEN` | Authenticated but not permitted. |
| 400 | `INVALID_CLIENT_ID` | Referrer `client_id` fails format validation. |
| 404 | `REFERRAL_NOT_FOUND` | No journey exists for this `client_id` (never clicked → never lazily created). |
| 404 | `NOT_FOUND` | Generic resource missing. |
| 409 | `DUPLICATE_LEAD` / `DUPLICATE_EVENT` | Idempotent replay (usually surfaced as 200). |
| 422 | `VALIDATION_FAILED` | Field-level validation errors (see `details`). |
| 423 | `ACCOUNT_LOCKED` | Login lockout. |
| 429 | `RATE_LIMITED` | Over rate limit; see `Retry-After`. |
| 500 | `INTERNAL_ERROR` | Unhandled server error (never leaks internals). |
| 503 | `PARTNER_UNAVAILABLE` | Redirect destination not buildable. |

---

## 9. Endpoint Summary (Sprint 1)

| # | Method | Path | Auth | Purpose |
|---|---|---|---|---|
| 1 | GET | `/r/{client_id}` | none | Format-validate raw `client_id` → lazily create referrer+journey+click → set `gr_vid` cookie + bot-UA filter → log classified click (`is_confirmed_human=false` until beacon) → optional landing → 302 to Zerodha (`c=ZMPHZC` server-side `&r={client_id}`). |
| 1b | GET | `/open` (a.k.a. `/r/open`) | none | **Partner-direct** (Gap 1): `c=ZMPHZC` only, **no `r=`** → creates a `partner_direct` journey (no referrer). |
| 1c | POST | `/api/click/confirm` | none (one-time nonce) | **JS human-confirmation beacon** (Gap 16): nonce-bound; flips a click to `is_confirmed_human=true`; only-then counted as human. |
| 2 | GET | `/api/landing/{client_id}` | none | Data for the branded PIFS landing page (per-partner config; partner-direct variant). **Generic — no referrer name.** |
| 2b | GET | `/api/landing/{client_id}/referrer` | none (one-time nonce) | Beacon-gated referrer first-name reveal (ADR-021); nonce required. |
| 3 | POST | `/api/leads` | none | Capture-first lead intake → Zoho mirror → 3 Wati messages (delivery status consumed). |
| 4 | POST | `/api/share` | none | Log a share event by channel; `wa.me` to the **WATI business number** (Gap 13). |
| 5 | POST | `/api/auth/login` | none | Bootstrap admin login → JWT + refresh. |
| 6 | POST | `/api/auth/refresh` | refresh cookie | Rotate access JWT. |
| 7 | POST | `/api/auth/logout` | admin JWT | Revoke session. |
| 8 | GET | `/api/auth/me` | admin JWT | Current admin profile. |
| 9 | GET | `/api/admin/dashboard` | admin JWT | Operational at-a-glance (clicks/leads/contacts). |
| 10 | GET | `/api/admin/referrals` | admin JWT | Filterable list of referral journeys (Referral Explorer). |
| 11 | GET | `/api/admin/referrals/{client_id}` | admin JWT | Full journey timeline (Referral Journey detail). |
| 12 | POST | `/api/integrations/zoho/account-status` | service key + Zoho-IP allowlist | Inbound account-status sync (Zoho-sourced event, `source: zoho`); referrer credited by Zerodha id, `update_id` idempotency, fed by the M6 sync worker (watermark + DLQ + off-platform auto-create). |

---

## 10. Open Items Affecting This Spec
1. **Identifier scheme — RESOLVED/LOCKED (ADR-001):** raw Zerodha `client_id` in the path (`/r/{client_id}`); no opaque token, no token→id mapping. This item is closed. (Future non-Zerodha partners will use a GoRefer-generated id minted at referrer login — not Sprint 1.)
2. **Lead schema — City required?** `POST /api/leads` treats `city` as config-driven-optional until the 2-field vs 3-field conflict is resolved (Foundation/Build-Spec).
3. **Domain / URL scheme — LOCKED (ADR-005):** `gorefer.in` bare path with the raw `client_id` in the segment; no `z.gorefer.in` subdomain.
4. **The new-lead alert WhatsApp number (Ashok)** is a config value resolved through the 3-tier cascade — not a hardcoded id; customer-facing surfaces default to the WATI business number `+91 70806 42020` at the central tier (Build-Spec §6, matrix #15).
5. **"Continue to Zerodha" form → Zerodha auto-fill** — an OPEN, build-time POC (currently believed not possible). The form still captures the lead regardless; auto-fill is **not** a dependency.

_End of 06-API-Specification.md — Sprint 1._
