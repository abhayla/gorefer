The Claude.md is a review prompt: act as a Principal Software Architect and critique the GoRefer spec. Let me read the actual spec documents rather than the truncated bundle so my review is grounded in the real design.You've built 16 ADRs, a constitution, and a 16-gap resolution log on top of two decisions you haven't actually closed — the hot-path deployment model and one real PII leak — and the governance ceremony is now outpacing the load-bearing engineering. That's the thing to fix before another document gets written.

The design is genuinely strong where it counts on *principle* (event-sourcing, lazy creation, Zoho-as-truth, never-fabricate, secrets hygiene, compliance-awareness). My job here is the opposite of praise, so here's the prioritized findings list. Confidence tagged per item; locked decisions (raw `client_id`, Zoho SoT, no Zerodha API) are left alone — everything below hardens the chosen design.

## P0 — fix before implementation

**1. Unauthenticated PII enumeration on `GET /api/landing/{client_id}`. [Certain]**
The endpoint is public and returns `referrer.first_name` (`"Abhay"`). `client_id` validates as `^[A-Za-z0-9]{4,16}$`, and real Zerodha IDs are low-entropy (`DA1707`, `RJ4521` — two letters + four digits ≈ a few million values). Anyone can walk the space and harvest a `client_id → real first name` map of your entire known-customer base, plus learn which IDs are "known customers" (name present) vs strangers.

I disagree with the implicit reasoning that "client_id is already public (ADR-001), so exposing it is fine." The client_id isn't the leak — the *binding of client_id to a named human* is new PII that Zerodha's own `r=` links never expose. ADR-001's public-identifier argument doesn't cover this.
**Instead:** don't emit real names from an unauth endpoint keyed by a guessable ID. Options, cheapest first — (a) drop the name, render "Your friend invited you"; (b) only personalize when the visitor arrives with a server-issued, single-use landing token minted during the `/r/` redirect, not by hitting `/api/landing/{id}` cold; (c) require the `gr_vid` continuity cookie set on a prior real click. **Risk if unfixed:** a DPDP-reportable data leak of your own client relationships, from a broker AP's own domain. 120/min/IP rate-limiting doesn't stop a distributed crawl.

**2. The edge-redirect scalability claim contradicts the API spec's own ordering. [Certain]**
`04 §8` sells a thin, stateless, edge-friendly redirect ("one lazy upsert + one append event," ingestion async). But `06 §4.1` orders steps 1–4 — upsert `referral_identity`, create `referral_journey`, write `click_event` — *synchronously before* the 302. You can't have both. Either the edge round-trips to Postgres on every click (kills "edge-friendly," couples edge→origin DB), or the identity/journey are materialized async (then landing personalization can't assume they exist yet).

This is the same decision `09 Deployment` marks **"TBD / not locked."** You've frozen 16 ADRs on top of the one decision that determines the entire runtime shape.
**Instead:** make this the next ADR, before code. My recommendation for a one-person op: edge worker emits a single append-only click event to a durable queue and 302s immediately; a consumer does the lazy identity/journey materialization; landing personalization reads from origin (finding #1 pushes you toward a token anyway, which decouples it cleanly). **Risk:** if you build to `06`'s literal ordering, your "instant edge redirect" is actually a synchronous cross-region DB write on the revenue hot path.

**3. Zoho inbound sync — the one channel that assigns real money — has optional integrity. [Certain]**
`POST /api/integrations/zoho/account-status` is the *sole* writer of `credited_referrer` (verbatim, ADR-016) and conversions. Auth is a static service key; HMAC signing is listed as "additionally recommended." For the endpoint that decides who gets paid brokerage, "recommended" is wrong.
**Instead:** mandatory HMAC over the raw body **and** replay protection beyond `event_id` (reject `occurred_at` outside a ±5-min window; nonce). A leaked key otherwise lets an attacker fabricate conversions and mis-credit referrers — financial fraud through a *trusted* channel, i.e. the exact "fabrication" your constitution forbids, laundered as legitimate.

## P1 — resolve before freeze

**4. Rollups aren't forward-foldable, but the spec treats them as if they are. [Likely]**
`is_confirmed_human` flips *after* the click (late beacon, or never), and ADR-017 backdates conversions to a true `account_opened_at` in prior periods. So `campaign_stats`/`daily_metrics` can't be an append-only fold — a late beacon or a backdated import mutates a historical day. The rollup worker must re-aggregate any touched day, not just "today."
**Fix:** define rollups as a windowed re-compute (last N days + any day a backdated import lands on), and store a `dirty_dates` set the import/beacon paths push into. Otherwise dashboards silently drift from `events`, and "rebuildable from events" becomes true only in theory.

**5. `account-status` payload is genuinely ambiguous — a mis-credit bug waiting to happen. [Certain]**
Sample: `client_id: "DA1707"`, `match_client_id: "RJ4521"`, `credited_referrer: "RJ4521"`. Field rules call `client_id` "referrer client id (for cross-check)" — but then it differs from the credited referrer in your own example. Which field is the *new account's* client_id vs the *referrer's*? Nail this down in the spec; an integrator will guess wrong and silently mis-attribute rewards.

**6. Off-platform (`zoho_import`) referrals have no uniqueness guard. [Likely]**
`leads.zoho_lead_id` is unique — good. But a `zoho_import` `referral` (Gap 3b, no clicks) is matched "by mobile + reference, else referrer-level-only." When `KYC_STARTED` then `ACCOUNT_OPENED` arrive as two `event_id`s for the same person with no `match_client_id`, nothing forces them onto the same `referral` row → phantom duplicate journeys.
**Fix:** deterministic upsert key for imported conversions (e.g. unique `(program_id, mobile)` for `source=zoho_import`, or route through `zoho_lead_id`).

**7. Three overlapping state machines, unclear authority past "Redirected." [Likely]**
`referrals.status` (…→`confirmed`→`rewarded`), `leads.status` (…`account_opened`), and Zoho's own. BR-006 says GoRefer verifies only to `Redirected`; everything after is Zoho. So `signup_completed`/`confirmed`/`rewarded` on `referrals.status` are only ever externally set — but the import endpoint writes *lead* status + `credited_referrer` + date, and never clearly advances `referrals.status`. With `reward_status` "display-only, never computed," the `rewarded` referral state is effectively unreachable.
**Fix:** publish an explicit Zoho-status → `referrals.status` map and mark states GoRefer may never set itself.

**8. `POST /api/leads` 24h dedup on `(mobile, client_id)` silently swallows the second referrer. [Likely]**
Two different referrers referring the same friend within 24h is *exactly* the ADR-016 scenario — but the lead endpoint returns the existing lead and fires no message for referrer B, so B's attempt becomes invisible before Zoho ever adjudicates.
**Fix:** keep the lead dedup, but still record referrer B's attempt as a share/referral-attempt event so the single-winner logic upstream has the full picture.

## P2 — hardening / missing requirements

**9. `POST /api/click/confirm` trusts client-supplied `visitor_id`+`client_id` to set `is_confirmed_human=true`. [Certain]** A script can forge confirmed-human beacons for any referrer. Bind the beacon to a server-issued nonce stamped at click time, not just the cookie value. (Your unique counts are already "best-effort," so this is about not letting anyone trivially inflate a specific referrer's confirmed clicks.)

**10. `events` immutability vs DPDP anonymization collide on `metadata` JSONB. [Likely]** ADR-020 strips PII at 12 months, but `events` has no `updated_at`/soft-delete. If any PII ever enters `events.metadata`, `ip`, or `user_agent`, you can't scrub it without breaking append-only. Add a hard rule + CI check: no PII keys in event metadata; PII lives only in mutable `prospects`/`leads`.

**11. Hashed IP is not a real privacy control. [Certain]** An IPv4 space is ~4.3B values — a plain hash is brute-forced in seconds, so calling it a DPDP safeguard is compliance theater. Use keyed HMAC with a secret salt, or just store `/24` + derived city and drop the rest.

**12. No sync-freshness observability = silent fabrication-by-omission. [Likely]** If the Zoho worker stalls, dashboards keep showing "no conversions," which *implicitly asserts* nothing converted — violating "never fabricate" by silence. Surface `last_successful_zoho_sync_at` on the dashboard and alert on staleness. Same for the noted ~33% WATI delivery leak.

**13. Compliance gate (ADR-014) is declared "enforced in the pipeline" but no pipeline enforces it. [Likely]** For Kit-engine-generated `marketing_assets`, there's no automated pre-publish check shown — it's a human skill-run labeled non-negotiable. Either wire a blocking check into asset generation or stop calling it pipeline-enforced.

**14. Landing publishes Ashok's *personal* number (`+91 73888 82020`) while Gap 13 deliberately routes capture to the WATI business number to avoid exactly that. [Certain]** Inconsistent, untracked (calls to a personal mobile bypass attribution), and a spam magnet. Use the business number everywhere.

**15. `preview=true` on the public edge redirect gated by "Bearer token present." [Likely]** Mixing an admin credential into an unauth edge worker is odd, and "token present" isn't "token valid." Verify the signature or move internal-test tagging to an admin-only path.

---

Recommendation as the person trying to build this lean: close findings **#2, #1, #3** this week — they're the deployment ADR, the leak, and the money-integrity gate, and nothing downstream is real until they are. Everything else is P1/P2 you can burn down during the build. Resist writing document 17 until #2 is locked; the paperwork is currently the *comfortable* work substituting for the decision that's actually hard.

Two things I'd want before I'd sign off, since I'm inferring from docs, not code: what does the Zoho side *guarantee* it stamps back (the journey-reference on the lead — finding #24-adjacent), and is the edge truly Cloudflare Workers with no DB, or an origin route? Those two answers move half this list.

