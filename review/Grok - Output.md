**GoRefer has a solid technical and compliance foundation, but as a product and growth engine it is dangerously under-powered in Sprint 1.** It risks becoming an expensive internal dashboard that tracks a leaky, low-engagement funnel rather than a self-reinforcing referral machine. The spec is heavy on "never fabricate," "compliance gate," and "Zoho is truth" — all correct — but light on the actual human psychology and economic incentives that make referrals happen at scale.

### Core Business Assumption That Is Fragile
The biggest unstated assumption is: **"If we give existing customers a trackable link and capture leads cleanly, they will keep sharing and the volume will grow."**

This is optimistic. Zerodha already has its own Refer & Earn program with real money (10% brokerage + 300 points) flowing to the referrer's account. GoRefer's value-add for the *referrer* in Sprint 1 is almost zero visible benefit:
- No self-serve dashboard ("My Referrals" is explicitly disabled).
- No conversion notifications.
- No leaderboards, milestones, or social proof.
- No easy way to see "your referrals turned into X accounts."

**Result:** You are asking busy people to do extra work (share a GoRefer link instead of a direct Zerodha one, or use your form) for *no incremental reward or feedback*. Most will do it once for the WATI campaign and then stop. Referral programs live or die on **repeated, habitual sharing** by the referrer, not one-time blasts.

### The Leaky Top of the Funnel (Existential)
You have already identified the ~33% WATI delivery failure. This is not a "prerequisite workstream." It is **the single largest risk to the entire business case**.

If one in three campaign messages never arrives, you are paying to acquire and warm an audience that never sees the referral ask. GoRefer then beautifully tracks the 67% that do arrive. This is classic "optimizing the wrong part of the funnel." Fix deliverability (opt-in hygiene, deduplication, Utility vs Marketing templates) *before* you spend engineering effort on beautiful journey timelines. Otherwise you are instrumenting a broken pipe.

### Friction vs. Conversion Reality Check
The capture-first form on the landing page ("Need Help?") is a **double-edged sword**:

**Good:** You own the lead even if the person abandons Zerodha's form. You get structured data + consent. Ashok gets alerted instantly.

**Bad (and likely dominant):** You are adding a mandatory form step in front of Zerodha's already reCAPTCHA-gated page. Many people who would have clicked through a simple redirect will bounce at your form. 

You have no A/B test planned in the spec between:
- Direct redirect path (lower data quality, higher abandonment risk later)
- Form-first path (higher data quality, higher immediate abandonment)

Without that measurement, you cannot know if GoRefer is *net positive* or *net negative* on actual account openings. The "save the lead first" philosophy is emotionally satisfying but may be commercially expensive.

### Referrer Psychology & Missing Growth Loop
Healthy referral systems create a **visible, reinforcing loop** for the referrer:
1. Share → 2. See some signal of progress (clicks, leads, or at least "your link was opened") → 3. Get rewarded or recognized → 4. Share again.

GoRefer Sprint 1 breaks this at step 2. The referrer gets a link via WATI and then… radio silence until (maybe) a future "thank you" message. No dashboard, no "X people clicked your link this week," no "3 of your referrals are in KYC."

This is why most corporate referral programs fail even when the financial incentive exists. The **social/ status/ progress** reward is often more powerful than the money for habitual sharers.

**Recommendation (blunt):** Even if you keep "My Referrals" disabled for self-service login, give *some* visible feedback mechanism in Sprint 1 (e.g., a simple WhatsApp status message "Your referral for Rahul is now in KYC" or a weekly digest). Otherwise you are training referrers to ignore your links.

### Human Bottleneck (Ashok)
Every converted lead appears to route through Ashok calling the prospect. This works beautifully at 5–15 leads per week. It becomes a disaster at 50+ per week.

The spec has no plan for:
- Self-serve KYC assistance paths
- Tiered support (chatbot → junior → Ashok)
- Capacity signaling ("high volume this week, expect 48h callback")

You are building a high-touch model inside a low-touch product category (discount brokerage signup). This does not scale without explicit headcount or automation plans.

### Regulatory & Incentive Concentration Risk
You correctly made the 10% brokerage claim swappable and put compliance on a hard gate. Good. But you are still structurally dependent on **one revocable incentive** (Zerodha's Refer & Earn) whose rules can change with one NSE circular.

If NSE reinstates the ban on non-AP referrer sharing, your entire referrer motivation layer collapses unless you have a Plan B (PIFS-funded micro-incentive? Status/reputation mechanics? Better tracking + recognition only?).

Most specs in this bundle treat the incentive as a constant. It is not.

### What Is Missing (Product/Growth Lens)

1. **Referrer activation & retention plan** — How do you turn a one-time WATI recipient into a habitual sharer? What education, creative assets, or micro-rewards exist?

2. **Clear differentiation vs. direct Zerodha link** — Why should a referrer use your link instead of just forwarding Zerodha's own referral URL? "Better tracking for PIFS" is an admin benefit, not a referrer benefit.

3. **Pilot & measurement framework** — Before full build, run a 4–6 week pilot with 100–200 customers. Measure: form vs direct conversion rate, time-to-close, referrer repeat-share rate, actual WATI delivery-to-open rate. The spec has almost no pre-launch validation plan.

4. **Fraud/abuse model** — What stops a referrer from spamming their own link to fake mobiles, or creating low-quality leads to game any future leaderboard? Bot filtering exists; economic incentive abuse does not.

5. **Future partner expansion realism** — "Configuration over code" sounds good until you onboard insurance or property, where the landing experience, compliance language, and conversion events are radically different. The architecture may support it; the product and content model probably does not without significant new work.

6. **Monetization path for GoRefer itself** — This is currently an internal cost center for PIFS. If it becomes a platform, what is the business model? White-label for other APs? Revenue share on tracked brokerage? The spec never addresses this.

### Verdict — What Makes It Succeed or Fail

**It will succeed if:**
- WATI deliverability is fixed to >90% before launch.
- You add even lightweight referrer feedback in Sprint 1 (or very early Sprint 2).
- You treat the landing form as an experiment, not a sacred "capture-first" principle, and measure its real impact on funded accounts.
- You keep the compliance obsession (it is your moat in a regulated category).

**It will fail (or become an expensive internal tool) if:**
- You launch with the current WATI leak and no referrer visibility loop.
- The form adds more friction than value and conversion drops vs. direct Zerodha links.
- Ashok becomes the bottleneck and leads go cold.
- Referrers treat GoRefer links as "one more thing to forward" rather than a better tool for them.

**Bottom line:** The technical and data architecture is thoughtful and defensible. The product and growth architecture in Sprint 1 is thin. You have built an excellent **observation layer**. You have not yet built a strong **activation and reinforcement layer** for the people whose behavior actually drives volume (the referrers).

Fix the top-of-funnel leak and give referrers a reason to care about their GoRefer link *beyond* Zerodha's existing incentive, and this has real potential. Otherwise it risks being a beautifully instrumented system that mostly measures its own under-performance. 

The compliance discipline is already a competitive advantage. Now apply the same rigor to the growth loops and referrer psychology.



User Prompt - Design referrer feedback loops

**Referrer Feedback Loops Design for GoRefer**  
**Version 0.9 (Sprint-1 focused, forward-compatible)**  
**Date:** 2026-07-05  
**Owner:** Abhay Kumar Maurya / PIFS  
**Status:** Design ready for implementation review. Aligns with Foundation Spec (Gap 5 deferred to Sprint 2), Constitution (measure everything observable, never fabricate, mobile-first, configuration over code), and 08-Zoho-WATI Integration.

### Why This Matters (Blunt Assessment)
Your current Sprint 1 design creates a **one-way street**: WATI blast → referrer shares or submits form → radio silence. This breaks the core psychology of referral programs. Research and real-world examples (fintech, WhatsApp-based, Dropbox/Uber-style) consistently show that **silence after sharing kills repeat behavior**. Referrers need visible proof their effort mattered ("my link worked," "my friend is in KYC," "I'm making progress").

Without feedback loops:
- Repeat-share rate stays low.
- Referrers treat GoRefer links as "one more campaign forward" rather than a better tool.
- You lose the self-reinforcing growth loop that turns one-time sharers into habitual advocates.

**This design fixes it** with minimal new surface area in Sprint 1 (mostly WATI utility pushes + one new background worker). It uses data you already capture (events, Zoho sync, leads). It stays compliant (utility category, warm tone, no spam, purpose-limited). It scales when you flip the `feature.customer_portal` flag for the "My Referrals" dashboard.

### Design Principles (Non-Negotiable)
1. **Close the loop fast and visibly** — Notify on lead capture and key status changes. Silence is the enemy.
2. **Never fabricate; source everything** — Use only GoRefer-verified events + Zoho as authoritative status. Label sources.
3. **Utility-first, frequency-capped** — All messages are helpful context ("Your referral for Rahul..."), not marketing. Max 1 progress update per journey per day + 1 digest per referrer per week.
4. **Mobile/WhatsApp primary** — Everything works via WATI utility templates (Meta-approved). Pre-filled, one-tap where possible.
5. **Progressive enhancement** — Sprint 1 = push notifications. Sprint 2+ = rich self-serve dashboard pulling the same data.
6. **Idempotent & resilient** — Respect WATI delivery status. If ~33% delivery leak persists, loops still function on the delivered subset and surface the leak in analytics.
7. **Psychology-backed** — Reinforcement (thank you + progress), social proof (aggregate impact), and gentle re-prompt to share again after success.
8. **Compliance baked in** — Warm tone naming PIFS/Zerodha context. No superlatives. Auto-inject minimal disclosure only if page-rendered. All templates pass `zerodha-ap-social-media-compliance` gate.

### The Four Core Feedback Loops

#### Loop 1: Instant Confirmation (on Lead Created) — Ship in Sprint 1
**Trigger:** Successful `POST /api/leads` (or equivalent Zoho lead creation) **where referrer phone is resolvable** from Zoho `Contacts` via `client_id` (existing join in 08-B4).

**Channel:** WATI utility template (new template: `gorefer_referral_registered`).

**Example message (warm, contextual):**
```
Thank you, [Referrer First Name]! 

Your referral for [Friend Name] has been captured via PIFS and sent to our team (Referral ID: [client_id]). 

Ashok or the team will reach out to them shortly to help open the Zerodha account. We'll keep you updated on progress.

Shared via your PIFS referral link.
```

**Why it works:** Immediate positive reinforcement. Names the friend (if appropriate) and sets expectation. Prompts nothing further yet.

**Edge cases:**
- Partner-direct journeys (`source=partner-direct`): Skip (no specific referrer).
- No resolvable phone: Silent skip (as already in spec for message c).
- Duplicate lead (24h de-dup): Still send once (idempotent on `lead_id` or `event_ref`).

#### Loop 2: Progress Milestone Updates (on Zoho Status Changes) — Ship in Sprint 1
**Trigger:** `POST /api/integrations/zoho/account-status` or Zoho sync worker detects meaningful transition in `lead_status_history` or `referrals.status` / `conversion_status` (e.g., `KYC_STARTED`, `ACCOUNT_OPENED`, `REJECTED` with disposition). Only fire on high-value changes, not every `NEW`.

**Channel:** WATI utility template (new: `gorefer_referral_progress`).

**Example messages (tailored by status):**
- KYC Started: "Update on your referral for [Name]: Status is now **KYC Started**. Our team is assisting with documents. Great progress!"
- Account Opened: "🎉 Excellent news! Your referral for [Name] has **opened their Zerodha account** via PIFS. Thank you for helping them start investing. (True open date: [account_opened_at from Zoho])"
- Rejected/Unconverted (with disposition): "Update on your referral for [Name]: It didn't convert this time ([disposition from Zoho, e.g. 'existing client' or 'not interested']). Thanks for trying — your link is still active for others."

**Rules:**
- Only one progress update per journey per 24–48h (prevent spam on rapid Zoho changes).
- Always include "as of [synced_at]" or source label.
- For off-platform / zero-click conversions (Gap 3b): Still notify if referrer was credited by Zoho.

**Why it works:** Shows real impact without the referrer having to ask. Uses the exact Zoho data you already import. Directly addresses the "did it work?" question that kills motivation.

#### Loop 3: Weekly Performance Digest — Ship in Sprint 1.5 (simple worker)
**Trigger:** Scheduled background job (new, lightweight; runs Sunday evening or configurable). Aggregates per `referral_identity` (or `credited_referrer`).

**Data pulled (all already in schema):**
- Human-confirmed clicks (from `events` with `is_confirmed_human=true`, last 7 days + lifetime).
- Leads created.
- Conversions / accounts opened (from Zoho-synced `account_opened_at`).
- Top channel or simple trend if available.

**Example message:**
```
Your PIFS Referral Summary (last 7 days)

• 12 human clicks on your links
• 2 new leads captured
• 1 account opened (true date this week)
• Lifetime with PIFS: 47 clicks • 9 leads • 4 accounts opened

You're making a real difference helping friends open better investing accounts. Your link is still active: gorefer.in/r/[client_id]

Keep sharing?
```

**Why it works:** Gives the "scoreboard" feeling without a dashboard. Social proof + gentle nudge to re-share. Uses `daily_metrics` + events rollups (already planned).

**Frequency cap:** Once per week per referrer. Skip if zero activity that week (or send very light "your links are ready" variant).

#### Loop 4: Social Proof & Visibility (Passive + On Success) — Ship in Sprint 1 (landing) + enhanced later
**On landing page (`GET /api/landing/{client_id}` and partner-direct variant):**
- Add aggregate, anonymized stat (from `daily_metrics` or events, non-PII):  
  **"Join 127+ friends who opened Zerodha accounts via PIFS referrals this month"** (or program-level rolling 30d).
- Per-referrer (future, when data model allows lightweight cache): "Your links have helped X friends so far."

**On successful share or lead event:** Optional light follow-up prompt in confirmation (Loop 1) or separate low-volume message: "Thanks for sharing! Want a fresh poster/QR with your latest impact stats?"

**Why it works:** Social proof on the page the friend sees. Subtle status for the referrer without extra UI.

### Implementation Notes (Minimal Delta on Existing Spec)
- **New WATI templates:** 2–3 utility templates (`gorefer_referral_registered`, `gorefer_referral_progress`, optional digest). Submit for Meta approval **in parallel** with build (hours–2 days). Category: UTILITY. Test with allowlist first.
- **Triggers:**
  - Loop 1 & 2: Hook into existing lead creation path + Zoho sync worker / `POST /api/integrations/zoho/account-status` (already designed in 06-API §7 and 08).
  - Loop 3: New simple scheduled worker (or use existing analytics rollup worker). Read from `events`, `referrals`, `leads`, `daily_metrics`.
- **Idempotency & state:** Store `last_notified_status` or `last_digest_sent_at` per `referral` / `referral_identity`. Check before sending.
- **Phone resolution:** Reuse existing Zoho `Contacts.ClientId` → mobile lookup (08-B4). Only send if resolvable and not opted out.
- **Partner-direct handling:** Skip personal messages. Optionally surface PIFS-level aggregates in admin dashboard only.
- **Error / delivery resilience:** Read WATI terminal status. If delivery fails repeatedly for a referrer, pause their loops and flag in admin (makes the ~33% leak visible).
- **When `feature.customer_portal = true` (Sprint 2):** All the same data powers the "My Referrals" dashboard (timeline already in 07-UI §7, plus new progress bars, share buttons with pre-filled updated copy, exportable CSV, milestone badges). One-tap re-share from dashboard becomes powerful.
- **Admin visibility:** New section or filter in Referral Explorer / Dashboard: "Referrers with recent feedback sent" + open rates (from WATI).

### Risks & Mitigations (Addressed)
- **Message fatigue / Meta throttling:** Strict caps + utility tone only. Monitor aggregate send volume.
- **Stale or wrong status:** Always pull fresh from Zoho sync; label "synced [time]". Never guess.
- **WATI delivery leak:** Loops are resilient; the leak becomes a visible metric instead of hidden failure.
- **Privacy / DPDP:** No friend PII leaked to referrer beyond what's appropriate (name in context of their own referral). Consent on original form covers updates. 12-month purge applies to unconverted.
- **Over-claiming impact:** All numbers are either GoRefer-observed (clicks) or Zoho-sourced (status). No fabricated rewards.
- **Regulatory:** All templates go through compliance gate. Tone is helpful/assistive, not promotional of incentives.

### Success Metrics for These Loops
- **Primary:** Referrer repeat-share rate (unique referrers with ≥2 `POST /api/share` events in 30 days) — target +30–50% lift post-launch.
- **Secondary:** WATI open/read rate on feedback messages (>60% target for utility). Time from lead/status change → referrer notification (<10 min).
- **Qualitative:** Simple pulse via one WATI question after 30 days ("Do these updates help you feel informed? Yes/No + optional comment").
- **Business:** Correlation between feedback-receiving referrers and higher downstream conversion/volume. Reduction in "cold" leads (referrers self-nudge when informed).
- **Admin:** % of journeys with at least one feedback event sent.

### Phased Rollout Recommendation
- **Sprint 1 MVP (this week/next):** Loops 1 + 2. Highest impact, lowest new surface. Uses existing paths.
- **Sprint 1.5 (parallel or immediate after):** Loop 3 (digest). One new worker.
- **Sprint 2 (when auth enabled):** Full dashboard + enhanced Loop 4 + self-serve re-share. Flip the flag — no redesign needed.
- **Future (Sprint 3+):** Light gamification (visible milestones in dashboard/WA), A/B test message framing, referrer feedback survey loop back into product.

This design turns GoRefer from a **tracking layer** into a **relationship layer** that makes referrers feel valued and informed — exactly what drives habitual sharing in successful programs. It respects every locked decision (raw `client_id`, Zoho truth, no auto-submit, compliance gate, WATI as pipe) while directly fixing the growth-loop weakness I flagged in the review.

Ready to turn into a formal repo document (e.g., `09-Referrer-Feedback-Loops.md`) or implementation tickets. Which part do you want to prioritize first — template wording, worker spec, or dashboard wireframe for Sprint 2?


User Prompt - Detail the Zoho status sync worker

**Zoho Status Sync Worker — Detailed Design**  
**For GoRefer Sprint 1+**  
**Date:** 2026-07-05  
**Owner:** Abhay Kumar Maurya / PIFS  
**References:** 04-System-Architecture §5.2, 06-API-Specification §7.1 (`POST /api/integrations/zoho/account-status`), 08-Zoho-WATI-Integration (Parts B & D), ADR-016/017, Gap 2/3/3b/4/4b/8/9/16, and the Referrer Feedback Loops design (Loop 2).

### Purpose & North Star
The **Zoho Status Sync Worker** is the **single reliable bridge** that brings externally verified truth (account opening, KYC progress, referrer credit, disposition) from Zoho into GoRefer without GoRefer ever fabricating or guessing.

It must:
- Be **idempotent** and auditable.
- Preserve the **true `account_opened_at`** (ADR-017) so analytics and timelines never show fake day-1 spikes from bulk/historical imports.
- Support **both push (webhook-style via the existing endpoint) and polled fallback**.
- Trigger high-value downstream effects cleanly: referrer progress notifications (new Feedback Loop 2), journey event appends, dashboard freshness, and future stale-lead flags.
- Handle the messy reality of Zerodha/Zoho (off-platform conversions, multiple modules, inconsistent opt-out fields, delayed imports).

**Golden rule:** Zoho is always right. GoRefer only reflects and enriches.

### High-Level Architecture

```
Zoho CRM (Contacts / Leads / Custom modules)
          │
          │ 1. Webhook (preferred, if configured) 
          │    OR
          │ 2. Polled query (fallback / catch-up)
          ▼
┌─────────────────────────────────────────────────────────────┐
│           Zoho Status Sync Worker (background)              │
│  - Idempotency guard (event_id or composite key)            │
│  - Matching engine (mobile + reference / match_client_id)   │
│  - True-date handling (account_opened_at vs synced_at)      │
│  - Journey enrichment + event append                        │
│  - Enqueue feedback notifications (Loop 2)                  │
│  - Unmatched → create minimal referral (Gap 3b)             │
│  - Audit / metrics emission                                 │
└─────────────────────────────────────────────────────────────┘
          │
          ├──► PostgreSQL (referrals, referral_journey_event, leads, daily_metrics)
          │
          └──► Notification Engine → WATI utility progress messages
               (Feedback Loop 2: KYC Started / Account Opened / etc.)
```

The existing `POST /api/integrations/zoho/account-status` (06-API §7) is the **push ingestion point**. The worker owns reliable processing, polling, retries, and side effects.

### Core Responsibilities

| Responsibility | Details | Why it matters |
|---------------|---------|----------------|
| **Ingestion (push + poll)** | Accept authenticated pushes; poll Zoho on schedule or after detected lag | Webhooks are best-effort; polling is the safety net for bulk/historical/off-platform data |
| **Idempotency** | `event_id` (from Zoho) is the primary key. Composite fallback: `(mobile normalized + credited_referrer + occurred_at)` | Prevents duplicate journey events or double notifications on retries/replays |
| **Matching** | Preferred: `match_client_id` or `credited_referrer` + mobile. Fallback: mobile + GoRefer journey reference stamped on Zoho lead | Handles Gap 2 (join key) and Gap 3 (single winner) deterministically |
| **True date preservation** | Store `account_opened_at` exactly as provided by Zoho; never overwrite with `now()` or `synced_at` | ADR-017 — analytics and cohort reporting stay honest |
| **Journey enrichment** | Update `referrals` (status, conversion_status, credited_referrer, lead_disposition, account_opened_at, conversion_synced_at). Append immutable `referral_journey_event` with `source: zoho` | Single source of truth + full audit trail |
| **Off-platform handling** | If no matching journey/clicks exist → lazily create minimal `referral` record (`source=zoho_import`, no click rows) | Gap 3b — every credited conversion is visible, even with zero GoRefer clicks |
| **Downstream triggering** | Enqueue WATI progress messages (Feedback Loop 2) only for meaningful status transitions. Update analytics rollups | Closes the referrer feedback loop without blocking the sync |
| **Error & observability** | Dead-letter queue for failed matches/enrichments. Emit metrics (matched %, unmatched %, processing latency). Admin-visible in dashboard | Trust + debuggability in a regulated environment |

### Detailed Processing Flow (for one status event)

1. **Receive / Poll**
   - Push path: `POST /api/integrations/zoho/account-status` (service key + optional HMAC signature).
   - Poll path: Worker queries Zoho (Contacts/Leads with recent status changes or custom "GoRefer sync" fields). Use incremental watermark (`last_synced_at` or Zoho `Modified_Time`).

2. **Idempotency Check**
   - If `event_id` already processed → return 200, no-op (already documented).
   - Composite key check as secondary guard.

3. **Matching Logic** (priority order)
   - **Best:** `match_client_id` present → find journey by that `client_id` + recent activity.
   - **Strong:** `credited_referrer` + normalized mobile → match to existing `referral_lead` or `referrals`.
   - **Fallback:** Mobile only + GoRefer reference stamped on the Zoho record.
   - **No match:** Treat as off-platform conversion (Gap 3b). Create minimal referral record with `source = zoho_import`, `credited_referrer` as provided, and `account_opened_at`.

4. **Enrichment**
   - Update or create `referrals` row.
   - Set `account_opened_at` **only from Zoho** (never derive).
   - Mirror `disposition` → `lead_disposition`.
   - Record `source = 'zoho'`, `conversion_synced_at = now()`.
   - Append `referral_journey_event`:
     ```json
     {
       "type": "ACCOUNT_STATUS_IMPORTED",
       "source": "zoho",
       "status": "KYC_STARTED" | "ACCOUNT_OPENED" | ...,
       "disposition": "...",
       "account_opened_at": "2026-07-03T11:05:00Z",
       "meta": { "zoho_record_id": "...", "module": "Contacts" }
     }
     ```

5. **Downstream Side Effects (non-blocking)**
   - If status is a **meaningful transition** (KYC_STARTED, ACCOUNT_OPENED, REJECTED with disposition) → enqueue Feedback Loop 2 WATI message to the referrer (if phone resolvable).
   - Update `daily_metrics` / `campaign_stats` rollups (or mark for later rollup job).
   - Emit admin dashboard signals (new "accounts opened" in KPI, fresh timeline in journey detail).

6. **Error Handling**
   - Transient Zoho API errors → retry with backoff (exponential, max 5 attempts).
   - Permanent failure (bad data, unresolvable match) → dead-letter queue + admin alert row.
   - Never drop the event — log it as unmatched for manual review.

### Polling Strategy (Fallback / Catch-up)
- **Frequency:** Every 15–30 minutes during business hours; hourly overnight (configurable).
- **Scope:** Only records modified since last successful watermark. Filter on Zoho `Modified_Time` or a custom "GoRefer last sync" field if added in Zoho.
- **Bulk safety:** Process in small batches (e.g., 50–100 records). Use the true `account_opened_at` so historical imports land in correct periods.
- **Lag detection:** If poll finds records older than X hours with no corresponding GoRefer event → flag as "sync lag" in admin dashboard.

**Recommendation:** Configure Zoho workflow/webhook on status change fields (`Status`, `KYC Status`, `Account Opened Date`) to call the push endpoint first. Use polling only as safety net and for bulk backfills.

### Integration with New Referrer Feedback Loops (Loop 2)
The worker is the **natural trigger point** for progress notifications:
- On successful enrichment of a meaningful status → enqueue `gorefer_referral_progress` WATI template.
- Pass: referrer phone (resolved), friend name (masked or first name only), new status, true open date if applicable, Referral ID.
- Respect caps already defined in feedback design (max 1 progress update per journey per 24–48h).
- If WATI delivery fails for a referrer repeatedly → pause further progress messages for that referrer and surface in admin.

This makes status changes immediately visible to the referrer without any UI change in Sprint 1.

### Data Model Touches (Minimal)
No new tables needed. Leverage existing:
- `referrals.account_opened_at`, `conversion_synced_at`, `credited_referrer`, `lead_disposition`, `source`
- `referral_journey_event` (append-only with `source: zoho`)
- `leads.status_synced_at`, `account_opened_at`
- Optional: Add `last_zoho_sync_watermark` in a config/settings table for the worker.

### Performance & Scale Considerations
- Events table is the largest object — appends are cheap; keep indexes on `referral_id + timestamp` and `source`.
- Worker should be lightweight and horizontally scalable if volume grows.
- Bulk historical imports (Gap 3b) must not create analytics spikes — true date + rollup jobs protect this.
- Rate limit the push endpoint (already in 06-API: 600/min per API key).

### Observability & Admin Surface
- Dashboard widget: "Zoho Sync Health" (last successful poll, unmatched events count, average processing latency).
- Referral Explorer filter: "Source = zoho_import" or "Has Zoho status".
- Journey detail timeline already shows `ACCOUNT_STATUS_IMPORTED` with full meta — this worker just populates it reliably.

### Open Items / Recommendations
1. **Webhook vs Poll decision** — Confirm whether Zoho can reliably webhook on the exact fields we care about (`Status`, `Account Opened Date`, `Disposition`). If yes, make push primary and polling secondary.
2. **Zoho field mapping** — Finalize exact field names in Contacts/Leads for `Client_Id`, `Account_Opened_Date`, `Disposition/Reason`, `KYC_Status`. The worker adapter must handle the inconsistency noted in 08-B4.
3. **Unmatched event workflow** — Decide on manual review queue vs auto-create minimal referral. Current design leans toward auto-create (Gap 3b) with admin flag.
4. **Testing harness** — Use the existing `wati-send-and-verify-delivery` pattern for end-to-end sync + notification tests. Include off-platform conversion scenario.
5. **Historical backfill plan** — One-time script to import past 12–24 months of opened accounts so "lifetime" numbers are accurate from day one (use true dates).

### Success Criteria for the Worker
- Every Zoho status change that reaches the push endpoint or poll appears in the correct journey timeline within 5 minutes (p99).
- No duplicate events or double notifications on retries.
- Off-platform credited conversions are visible in Referral Explorer and count toward referrer totals.
- Referrer progress messages (Loop 2) fire reliably for meaningful transitions.
- Analytics never show fake spikes from import timing.

This worker is the **operational heart** that makes the "Zoho is the single source of truth" principle real in production. It turns the existing API contract into a living, reliable system and directly powers the referrer feedback that was missing in the original Sprint 1 scope.

Would you like me to produce:
- The exact worker implementation outline / pseudocode?
- Updated sequence diagram for the full sync + feedback path?
- The WATI template wording for the progress messages triggered by this worker?
- Or turn this into a formal repo document (`04b-Zoho-Status-Sync-Worker.md`)?


User Prompt - Detail the idempotency guard logic

**Idempotency Guard Logic — Zoho Status Sync Worker & Endpoint**  
**Detailed Design**  
**Date:** 2026-07-05  
**Scope:** `POST /api/integrations/zoho/account-status` (06-API §7.1) + Zoho Status Sync Worker (push + poll paths) + downstream effects (especially Referrer Feedback Loop 2)

### Purpose
The idempotency guard ensures that **re-processing the same Zoho status event never creates duplicate journey events, duplicate referrer notifications, or corrupted analytics**. This is critical because:
- Zoho (or the caller) may retry on transient errors.
- Webhooks can be delivered more than once.
- Polling can re-fetch the same record during catch-up or lag.
- Bulk/historical imports can overlap with live events.
- Duplicate WATI progress messages would annoy referrers and risk Meta throttling.

**Core contract (already stated in 06-API):**  
If the same logical event is received again, return **200 OK** with a no-op response and **do not mutate state or trigger side effects**.

### Primary Idempotency Key
**`event_id`** (string, required in the request body)

- Provided by Zoho (or the integration caller) as a stable, unique identifier for that specific status change event.
- Examples: `zoho_evt_00912`, `60019670093-1234-status-2026-07-04T14:20:00Z`, or any durable ID Zoho can emit.
- Stored in `referral_journey_event.meta.event_id` (or a dedicated column for fast lookup).

**Rule:** `event_id` is the **first and strongest** guard. If it has been seen before → immediate no-op.

### Fallback Composite Key (when `event_id` is missing or untrusted)
Used for:
- Older Zoho records without `event_id`
- Polling path (where we may not have a clean `event_id`)
- Defensive programming

**Composite key:**
```
normalized_mobile + credited_referrer (or match_client_id) + occurred_at (truncated to minute or second) + status
```

Normalization rules:
- Mobile: remove spaces, `+`, `(`, `)`, `-`; prefix `91` if Indian number.
- `occurred_at`: Use the value from the payload (Zoho’s recorded time), not `now()`. Truncate to minute for tolerance on clock skew/retries.
- If `credited_referrer` is absent → fall back to `match_client_id` or treat as partner-direct / PIFS-only.

This composite is stored alongside `event_id` (when present) for auditability.

### Storage & Lookup Mechanism
**Recommended table (new, lightweight, append-only for audit):**

```sql
CREATE TABLE zoho_sync_idempotency (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT UNIQUE,                    -- primary key when present
    composite_key TEXT,                      -- fallback / secondary
    zoho_record_id TEXT,
    mobile_normalized TEXT,
    credited_referrer TEXT,
    status TEXT,
    occurred_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source TEXT,                             -- 'push' | 'poll'
    result TEXT,                             -- 'matched' | 'unmatched' | 'no-op'
    journey_event_id BIGINT REFERENCES referral_journey_event(id),
    feedback_enqueued BOOLEAN DEFAULT false
);

CREATE UNIQUE INDEX idx_zoho_sync_event_id ON zoho_sync_idempotency(event_id) WHERE event_id IS NOT NULL;
CREATE UNIQUE INDEX idx_zoho_sync_composite ON zoho_sync_idempotency(composite_key) WHERE composite_key IS NOT NULL;
```

**Why a dedicated table?**
- Fast `EXISTS` / `INSERT ... ON CONFLICT DO NOTHING` checks.
- Full audit trail of every sync attempt (even duplicates).
- Can store `feedback_enqueued` flag to prevent duplicate WATI messages even if journey event was already created.

Alternative (lighter): Add `event_id` + `composite_key` columns directly to `referral_journey_event` with a partial unique index. The dedicated table is cleaner for high-volume polling + side-effect tracking.

### Decision Logic (Pseudocode)

```python
def process_zoho_status_event(payload):
    event_id = payload.get("event_id")
    composite = build_composite_key(payload)  # normalized_mobile + credited_referrer + occurred_at + status

    # 1. Fast path - event_id
    if event_id:
        existing = db.query("SELECT * FROM zoho_sync_idempotency WHERE event_id = %s", event_id)
        if existing:
            log("Duplicate event_id received - no-op", event_id=event_id)
            return 200, {"matched": existing.result == "matched", "event_id": event_id, "duplicate": True}

    # 2. Fallback - composite key
    existing = db.query("SELECT * FROM zoho_sync_idempotency WHERE composite_key = %s", composite)
    if existing:
        log("Duplicate composite key - no-op", composite=composite)
        return 200, {"matched": ..., "duplicate": True}

    # 3. New event - process
    record = db.insert("zoho_sync_idempotency", {
        "event_id": event_id,
        "composite_key": composite,
        "mobile_normalized": ...,
        "credited_referrer": payload.get("credited_referrer"),
        "status": payload.get("status"),
        "occurred_at": payload.get("occurred_at"),
        "source": "push" if request else "poll"
    })

    # Perform actual matching + enrichment (the real work)
    result = enrich_referral_journey(payload)   # updates referrals, appends referral_journey_event, etc.

    record.update({
        "result": result.matched ? "matched" : "unmatched",
        "journey_event_id": result.journey_event_id
    })

    # 4. Side-effect guard (Feedback Loop 2)
    if result.matched and is_meaningful_transition(payload.status):
        if not record.feedback_enqueued:
            enqueue_wati_progress_message(referrer_phone, payload)
            record.update({"feedback_enqueued": True})
        else:
            log("Feedback already enqueued for this event - skipped duplicate")

    return 200, {"matched": result.matched, "lead_id": result.lead_id, "new_status": payload.status}
```

### Handling Downstream Side Effects (Critical for Feedback Loops)
The guard must protect **more than just the database write**:

- **WATI progress message (Loop 2):** Use the `feedback_enqueued` flag in `zoho_sync_idempotency`. Only enqueue once per logical event.
- **Analytics rollups:** The `referral_journey_event` append is already idempotent (append-only). The guard prevents duplicate appends.
- **Dashboard KPIs:** Because we use true `account_opened_at` and event sourcing, duplicate processing does not inflate counts.

### Error & Retry Scenarios

| Scenario | Guard Behavior | Outcome |
|----------|----------------|---------|
| Same `event_id` retried (transient Zoho error) | Immediate lookup hit | 200 no-op, no duplicate notification |
| Polling re-fetches same record | Composite key hit | 200 no-op |
| Bulk historical import overlaps with live webhook | Both keys checked | No duplicate events or double WATI messages |
| Clock skew on `occurred_at` | Truncate to minute + status in composite | Tolerates small timing differences |
| Zoho re-sends same status change with new `event_id` | Treated as new (correct, different event) | Processes normally |
| Partial failure after journey update but before feedback enqueue | `feedback_enqueued = false` on retry | Re-enqueues safely (idempotent enqueue) |
| Unmatched event retried | Composite or event_id hit | Still no-op (prevents repeated "unmatched" logging spam) |

### Implementation Recommendations

1. **Database transaction** — Wrap the lookup + insert + enrichment in a single transaction with `INSERT ... ON CONFLICT DO NOTHING` (or equivalent) for atomicity.
2. **Early return on duplicate** — Do the idempotency check **before** any Zoho data enrichment or matching logic to save CPU and avoid unnecessary joins.
3. **Logging** — Every duplicate must be logged with `request_id`, `event_id`/`composite`, and source (`push` vs `poll`) for audit and to detect flapping webhooks.
4. **Metrics to emit**
   - `zoho_sync_duplicate_rate` (target < 5% in steady state)
   - `zoho_sync_idempotency_lookup_latency`
   - `feedback_duplicate_prevented_count`
5. **Cleanup** — The `zoho_sync_idempotency` table can be partitioned by `processed_at` (monthly) and old partitions archived after 90–180 days (retention aligned with DPDP where applicable).

### Edge Cases Specific to GoRefer

- **Off-platform conversions (Gap 3b):** Still create the minimal referral record on first receipt. Subsequent identical events hit the guard and become no-ops.
- **Status regression (rare but possible in Zoho):** If Zoho sends a lower status later, the composite key (which includes `status`) treats it as a new event. Business decision: allow it or add extra guard on `occurred_at` monotonicity.
- **Partner-direct journeys:** The guard still applies; we simply skip referrer-specific feedback.
- **High-volume bulk import:** The guard + batch processing + true `account_opened_at` prevents both duplicate data and analytics distortion.

### Summary — One-Screen Checklist for Developers

- Primary key = `event_id` (fast path)
- Secondary key = normalized composite (defensive)
- Dedicated `zoho_sync_idempotency` table with `feedback_enqueued` flag
- Check **before** any enrichment
- Protect WATI enqueue with the same guard
- Log every duplicate for observability
- Return clean 200 no-op response

This logic makes the entire Zoho → GoRefer → Referrer feedback path **safe to retry at every layer** while keeping data and notifications exactly-once in effect.

Would you like the full SQL migration + index strategy, the exact enrichment function pseudocode that sits after the guard, or the updated sequence diagram showing the guard in the worker flow?