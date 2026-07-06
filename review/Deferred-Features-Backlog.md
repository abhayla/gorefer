# GoRefer — Deferred Features Backlog

Running list of features/decisions consciously deferred out of Sprint 1, to be implemented later.
Owner: Abhay/PIFS. Each entry: what, why deferred, trigger to revisit.

---

## From external-review matrix

### DF-1 — Zoho API "pull" for status sync (polling)
- **What:** GoRefer periodically calls the Zoho API (OAuth login) to fetch account-opening/reward status, instead of relying on Zoho pushing a webhook. Removes the forgeable inbound endpoint entirely; reads straight from source of truth.
- **Why deferred (Abhay, July 2026):** keeping the existing webhook ("hook") for now; not reworking the sync mechanism yet.
- **Revisit when:** hardening the Zoho integration (M6+), or if the webhook proves unreliable / instant-vs-delayed tradeoff needs revisiting. Folds into matrix item #7 (Zoho sync worker → polling-first).

### DF-2 — Wax-seal (HMAC + timestamp + nonce replay protection) on the Zoho status webhook
- **What:** Upgrade the Zoho→GoRefer "account opened" message from a single static key to an HMAC signature over payload+timestamp+one-time-nonce, verified by GoRefer (rejects forged, stale/replayed, or reused messages). Needs a small Zoho-side (Deluge) signing function.
- **Why deferred (Abhay, July 2026):** keeping the basic webhook without the wax-seal for the time being.
- **Interim minimum while deferred:** keep the static shared key AND restrict the endpoint to Zoho's server IPs (allowlist) as cheap hygiene — not the full wax-seal, just a basic lock. (Endpoint is only live from M6; Sprint 1 M1–M4 runs demo-mode with ZOHO_WRITE off, so no live exposure yet.)
- **Revisit when:** before the Zoho status webhook goes live in production (M6), or immediately if a real referrer-reward payout depends on it. This was originally a Claude P0 (sole writer of conversions/credited_referrer; a leaked static key = fabricated conversions).

### DF-3 — Edge / distributed runtime model
- **What:** Run GoRefer across many small servers near users ("the edge") for lower redirect latency and very high throughput, instead of the single central app+DB.
- **Why deferred (Abhay, July 2026):** decided #5 in favour of the SIMPLE CENTRAL model (one app + one DB). At current volume (~250–1,000 clicks/day, ~4 inserts/sec peak, ~0.5–3M rows/yr) a single Postgres instance runs at ~0.1% capacity; edge would be over-engineering and would complicate event ordering.
- **Revisit when:** sustained load approaches ~1,000,000 clicks/month (roughly 100× today), or global redirect latency becomes a measured problem. Until then, get reliability from a managed DB + backups + standby + health check, not from edge distribution.

### DF-4 — Full bulk historical backfill (all-time, since 2016)
- **What:** a one-off script to bulk-load ALL historical account-openings/mappings (back to 2016) from Zoho, dated to true open dates, so all-time GLOBAL dashboards (grand totals, all-time top referrers across everyone) are complete from day one.
- **Why deferred (Abhay, July 2026):** primary mechanism is now LAZY per-referrer fetch (matrix #9) — each referrer's history loads when they first become active in GoRefer. Bulk is only needed for complete all-time GLOBAL aggregates at launch, which Abhay is fine to let fill in over time.
- **Revisit when:** you want complete all-time global dashboards from day one, or for a periodic full reconciliation sweep.

### DF-5 — Per-partner configurable page fields/layout (landing + dashboard)
- **What:** let each partner/tenant configure which fields, details, and branding appear on their landing page and admin dashboard (field-level UI config, beyond the value-level config cascade A1).
- **Why deferred (Abhay, July 2026):** Sprint 1 is single-tenant PIFS with a fixed field set; per-partner UI-field configurability is a later-phase (Sprint 2+ / multi-tenant A2) capability. Requirement raised while reviewing the landing + dashboard mockups.
- **Revisit when:** onboarding a second tenant, or when partners need distinct landing/dashboard fields.

### DF-6 — Mobile number OTP verification on the capture form
- **What:** verify the prospect's mobile via OTP (SMS/WhatsApp) on the GoRefer capture form — correctness / anti-typo, reduces junk leads.
- **Why deferred (Abhay, July 2026):** Sprint 1 does client-side FORMAT validation only (Indian +91, 10 digits). OTP adds an OTP flow + cost + friction — later phase.
- **Revisit when:** mistyped/junk leads become a problem, or higher lead quality is needed.
