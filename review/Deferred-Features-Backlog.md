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

### DF-7 — Schema-per-tenant (or per-tenant DB) physical isolation
- **What:** move a tenant (or all tenants) from the single-schema `tenant_id` discriminator model to Postgres schema-per-tenant (e.g. django-tenants) or a dedicated per-tenant database, for hard physical isolation.
- **Why deferred (Abhay/DA, July 2026 — resolves COORDINATION Q-M1-1):** Sprint 1+ uses **single-schema tenant_id discriminator** (matches ADR-023 + 05-Database-Design; simpler, better platform-wide analytics, sufficient isolation via tenant-scoped managers + composite constraints at this scale).
- **Revisit when:** a specific enterprise/regulated tenant demands physical isolation, or cross-tenant leakage risk/compliance requires it. Migrating one tenant to its own schema/DB later is possible without a full rebuild.

### DF-8 — Physical monthly partitioning of the `events` table
- **What:** apply Postgres declarative partitioning (by month) to the immutable `events` table for query/maintenance efficiency at scale, and enable cold-archival of old partitions (rollups kept forever).
- **Why deferred (DA, M4, July 2026):** at Sprint-1 volume (~0.5–3M rows/yr) it's unnecessary. M4 already delivers the correctness that matters — append-only events + daily/monthly rollups with dirty-day recompute (fully foldable), so analytics don't scan the raw firehose. Physical partitioning is an ops/DB step best applied when the table actually grows.
- **Revisit when:** the `events` table gets large (tens of millions of rows) or query/vacuum times degrade. Pairs with the cold-archive horizon in the data-retention decision.

### DF-10 — Runtime theming / theme-switcher (later stage)
- **What:** allow the GoRefer UI look (colors, accent, surface style) to be switched at runtime via a theme layer, rather than one hardcoded skin. Feasible because the UI is Tailwind + CSS variables — define theme tokens (accent, surface, line, text) as CSS custom properties and swap a `data-theme` attribute; per-tenant/per-user theme selectable from the config cascade (ties to DF-5/DF-9 config-over-code).
- **Why deferred (Abhay, 2026-07-07):** first pick ONE finalized visual language from the variant mockups and ship all screens in it. Theming (multiple selectable skins) is a later-stage capability, not Sprint 1.
- **Revisit when:** onboarding tenants who want their own branding, or after the single chosen skin is live and stable. Build the chosen skin with CSS-variable tokens NOW so theming later is a config layer, not a rewrite.

### DF-9 — Pluggable per-user "Lead Destination" adapter (centrally configured)
- **What:** each GoRefer user/tenant configures **where a captured lead is written** — options: **none/manual, Zoho CRM, Google Sheet, webhook, CSV export, or other** — selected from the **central config** (config-over-code, no code change per user). A registry of outbound "lead sink" adapters behind a common interface; the user's chosen sink(s) fire on form submit. Mirrors the provider-agnostic pattern already used for redirect destinations.
- **Why deferred (Abhay, 2026-07-07):** raised during the User Referral Screen design. **Abhay's own Zerodha tenant deliberately writes to NO destination** — Ashok enters leads into Zoho **manually**, and that process must not change. So for PIFS Sprint 1, `ENABLE_ZOHO_WRITE` stays **off** (Zoho **READ** enrichment/status stays on). Other GoRefer users will want different sinks (some Google Sheet, some Zoho, some elsewhere), so the destination must be per-user configurable — but that's a later build.
- **Consequence to remember:** with no GoRefer→Zoho write, GoRefer cannot stamp its journey-id onto the Zoho lead, so the journey↔Zoho-contact link is **match-based** (mobile/email/ClientId), not exact stitching. Documented as an accepted limitation.
- **Revisit when:** onboarding a second GoRefer user/tenant whose lead-capture destination differs from PIFS, or when auto-write to any sink is wanted. Relates to DF-1 (Zoho pull), DF-5 (per-partner fields), and the config cascade (A1).

### DF-OTP-SMS — SMS OTP provider (fallback channel for referrer login)
- **What:** choose + wire a real SMS provider (MSG91 / Twilio / Gupshup / Kaleyra / …) behind the existing `SmsOtpAdapter` interface so `sms` becomes a live OTP channel (primary or fallback), selectable per-tenant on the Preferences screen (Q-M-OTP / ADR-035).
- **Why deferred (Engineer, Q-M-OTP, 2026-07-12):** Q-M-OTP built the SMS adapter as an **interface + log-only stub** (returns `failed` so a mis-set `sms` primary cascades cleanly). WhatsApp-via-Wati is the decided PRIMARY (auth template ≈ ₹0.115/msg, reportedly < half the cheapest SMS OTP), with `manual` as the shipped fallback — so no SMS provider is needed to ship the OTP layer.
- **Revisit when:** referrers without WhatsApp become common enough that a machine SMS fallback beats the manual/assisted path, or a provider is chosen. Surfaced as COORDINATION Q-M-OTP-1. Relates to ADR-035, DF-6 (OTP), [[wati-setup-reference]].

### DF-11 — Self-click tagging on the Referral Profile
- **What:** on the Referral Profile Clicks tab, if a click's mobile later matches the referrer's own known Zoho mobile, tag that click **"self-click"** and exclude it from conversion counts (a referrer opening their own link shouldn't inflate their conversions).
- **Why deferred (DA, M9, 2026-07-08):** raised in the User Referral Screen mission as a later polish, explicitly **not** built in M9. Needs a reliable click→mobile link (mobile only appears on lead submit) and the referrer's own mobile from Zoho READ.
- **Revisit when:** self-referral inflation becomes a real concern, or after the customer/referrer view ships. Relates to ADR-018 (mobile-authoritative identity), the Zoho READ enrichment (M9), and DF-6 (OTP).
