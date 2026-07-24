# 14 — 24h-Window Follow-up Engine (per-AP configurable, CRUD-able)

> **Status: DESIGN. Phase 1 (tenant-scoped, PIFS-as-sole-AP) is buildable now; the multi-tier
> (partner-group / partner) resolution is MODEL-ONLY per doc-13 §5 — it binds the multi-AP mission,
> not Sprint 1.** Supersedes `docs/whatsapp-reminder-scheduler-plan.md` and `Wati-Project/wati-insession-nudge-queue-plan.md`.
> Author: session 2026-07-24, grounded in a read of the actual current code (file:line refs throughout).

## 0. The capability in one line
Every **Authorized Partner (AP = tenant)** can define, edit, pause and delete their OWN follow-up
cadence (e.g. nudge at +15 min, again at +2 h) that fires to a prospect **while the WhatsApp 24-hour
window is still open** (free-form, cap-free) — and out-of-window falls back to a template or skips.

## 1. Grounding — how scheduling & config work TODAY (verified in code)
- **Scheduler = django-q2, ORM broker** (`gorefer/settings.py:118-126`). Recurring `MINUTES` jobs are
  registered idempotently in `apps/events/management/commands/setup_schedules.py` — 6 today, incl.
  **`wati_reconcile_pending` every 15 min** (`apps.integrations.wati.tasks.reconcile_pending_deliveries`)
  which **sweeps due rows** (`updated_at__lte=now-3min`). This "recurring sweep over a due-table" is the
  exact idiom the follow-up engine reuses. (No `Schedule.ONCE` primitive is used — and we deliberately
  don't add one; a swept due-table is cheaper on the ORM broker AND is what makes CRUD trivial.)
- **Per-AP config = 3-tier cascade** (ADR-022, `apps/config/cascade.py` → `resolve(key, tenant_id, user_id)`:
  Central → Global-per-tenant → User, most-specific-wins; `COMPLIANCE_LOCKED_KEYS` resolve central-only).
  Doc-13 §4: *"per-AP timings/formats are plain config-cascade keys at tenant tier — no new machinery."*
- **Send path = Wati adapter** (`apps/integrations/wati/adapter.py`, `LiveWatiAdapter`) — **template-only
  today** (`send_template`), fail-closed recipient allowlist (`_recipient_allowed`). Inbound webhook exists
  (`apps/integrations/wati/webhook.py`). No stored inbound timestamps, no session-send method.
- **AP = tenant is the isolation cut** (doc-13 / ADR-036): own number (ADR-040), own opt-out (G-4), own
  templates/timings. PIFS is currently the **only** AP.
- **Two send systems coexist:** this GoRefer engine (django-q + Wati adapter) vs the existing **Zoho
  `WA_Send_Queue` + Deluge journey senders** (Day-0/1/3/7/14 templates). See §8 for the boundary.

## 2. Architecture (5 pieces, all reusing the above)

### (A) FollowupRule — the AP's editable cadence (per-AP config)
New tenant-scoped model `apps/followups/models.FollowupRule`:
`{tenant(FK), step_key, offset_minutes, channel(SESSION|TEMPLATE), template_name?, body_en, body_hi,
enabled, only_if_window_open(bool), stop_on_reply(bool), order}`.
- One AP → many steps (e.g. step1 +15 min SESSION, step2 +120 min SESSION). **This IS the per-AP config**
  — tenant-scoped, so it honours AP=tenant isolation. It is NOT the speculative PartnerGroup hierarchy §5
  forbids; it's a real feature table at the *existing* tenant tier.
- Simple on/off/global knobs (`followups_enabled`, default copy) stay as **cascade keys**
  (`config.cascade`) — only the multi-step editable list needs its own table.
- **Doc-13-safe extensibility:** add a nullable `scope` later (`tenant` now; `partner`/`partner_group`
  when the hierarchy is built) so group/partner DEFAULT rules resolve *above* the AP rule with no rework.

### (B) ScheduledFollowup — the due-table (the schedule primitive + the CRUD surface)
New model `apps/followups/models.ScheduledFollowup`:
`{tenant(FK), contact(FK Prospect/Customer), mobile, rule_step(FK), fire_at, status(SCHEDULED|SENT|
CANCELLED|SKIPPED|FAILED), pref_lang, dedupe_key(unique per contact+step+chat-open), source_event, sent_at}`.
- **Enqueue:** on chat-open (Wati inbound webhook) or a GoRefer event, read the contact's AP's enabled
  `FollowupRule`s → insert one `ScheduledFollowup` per step at `fire_at = chat_open + offset_minutes`.
  Skip if opted-out / dedupe hit.
- **Fire:** new recurring schedule `followup_sweep` (add to `SCHEDULES`, every 5 min) →
  `apps.followups.tasks.fire_due_followups` selects `status=SCHEDULED AND fire_at<=now`, locks the row,
  runs the gate (D), sends (E). Mirrors `wati_reconcile_pending` exactly.

### (C) CRUD lifecycle (the owner's explicit requirement)
Two levels, both natural because everything is a table row:
- **Rule CRUD** (the cadence template): AP adds/edits/deletes/pauses `FollowupRule` steps via GoRefer
  API/admin (`api/` DRF, permission-scoped to the AP's tenant). **Default: edits apply to FUTURE
  chat-opens**; an explicit *"re-apply to in-flight"* action re-computes pending `ScheduledFollowup` rows.
- **Instance CRUD** (one contact's scheduled follow-up): view / reschedule `fire_at` / edit body / cancel
  a specific `ScheduledFollowup` **while `status=SCHEDULED`**; immutable once `SENT`. The sweep's row-lock
  prevents an edit racing a send.
- **Surface phasing:** admin + API now; the permission-scoped **in-product page** later (doc-13 O-6:
  AP sees own, group-lead sees group, admin sees all).

### (D) Send gate (per row, at fire time)
1. **Opt-out?** (per-AP, doc-13 G-4) → CANCEL.
2. **Engaged-exit?** contact replied / advanced funnel / converted since enqueue AND `stop_on_reply` → CANCEL.
3. **Window open?** `now - last_inbound_at < 24h` → OPEN → **SESSION** send; CLOSED → if step has a
   template → **TEMPLATE** (respect category/cap), else SKIP.
4. Send via adapter (inherits allowlist) → record `Notification` → verify terminal delivery via the
   existing reconcile (HTTP 200 ≠ delivered).

### (E) Two small adapter/webhook additions
- Add `send_session_text(to, message)` to `LiveWatiAdapter` (Wati v3 `POST /conversations/messages/text`),
  inheriting `_recipient_allowed`. Keep `send_template`.
- Extend `apps/integrations/wati/webhook.py` to stamp `last_inbound_at` on the contact on every inbound
  (the window-state feed). Fallback: live `getMessages` at fire time.

## 3. Success & edge scenarios (all handled by the above)
| Scenario | Behaviour |
|---|---|
| AP sets +15 min nudge; contact idle | fires at +15, window open → session message |
| AP sets +15 & +2h; contact replies at +30 min | +2h step CANCELLED (stop_on_reply / engaged-exit) |
| AP edits +15 → +20 | future chat-opens use +20; in-flight unchanged unless "re-apply" chosen |
| AP deletes a step | its pending `ScheduledFollowup` rows CANCELLED |
| AP pauses follow-ups (`enabled=false`) | no new enqueues; pending optionally cancelled |
| AP reschedules one contact's pending nudge | edit `fire_at` on that row (status=SCHEDULED) |
| Contact opts out | all their pending follow-ups CANCELLED (per-AP scope) |
| Window closed (>24h) at fire | session SKIPPED; template sent if configured, else skip |
| Contact converts (account opened) | follow-ups CANCELLED (engaged-exit) |
| Same person under 2 APs | independent per AP, each from that AP's own number (doc-13 isolation) |

## 4. New Django app + files
`apps/followups/`: `models.py` (FollowupRule, ScheduledFollowup) · `tasks.py` (enqueue_followups,
fire_due_followups) · `api.py` (DRF CRUD, tenant-scoped) · `admin.py`. Plus: one line in `SCHEDULES`
(setup_schedules.py); `send_session_text` in the Wati adapter; `last_inbound_at` in the webhook + a
contact field; a `followups_enabled` cascade key.

## 5. Phasing (doc-13-safe)
- **Phase 1 (now, PIFS-as-sole-AP):** A–E above, all tenant-scoped. PIFS configures its rules; the
  in-session +15/+20-min nudge works end-to-end. NO PartnerGroup, NO 5-tier resolution (§5).
- **Phase 2 (multi-AP mission):** add `FollowupRule.scope` (partner / partner_group) so group/partner
  DEFAULT cadences resolve above the AP rule — slots into ADR-036 with no rework. Per-AP number/opt-out
  (ADR-040/G-4) already fits.

## 6. Boundary with the Zoho journey (the one strategic fork — owner's call)
- **(A) Incremental (recommended):** GoRefer owns the **in-session** follow-up; the live Zoho Deluge
  Day-0/1/3/7/14 journey stays untouched. Lowest risk; proves the engine.
- **(B) Consolidate:** migrate the journey into this engine so GoRefer is the single reminder brain
  (Phase 2). Cleaner long-term; touches live production sends.
Phase 1 is identical either way.

## 7. DoD · risks · rollout
- **DoD:** unit (rule resolution; window-open→session / closed→template-or-skip; engaged/opt-out→cancel;
  idempotent; CRUD state transitions) · live test on 7972672473 / 7767009136 (idle→nudge; reply early→
  none; >24h→template/none; edit/cancel a pending row) · delivery verified at destination.
- **Risks:** webhook gap → fallback live-query · sweep latency at volume → 5-min granularity fine for
  ≥15-min targets, revisit if sub-5-min needed · `send_session_text` must inherit the allowlist ·
  rule-edit vs in-flight semantics must be explicit (default future-only).
- **Rollout:** behind `followups_enabled` flag → live-test on test numbers → owner copy sign-off →
  enable for PIFS → (Phase 2) extend to hierarchy when the multi-AP mission opens.

---
*The separate 3-minute Chatbot-Timer close is unrelated — a Wati dashboard fix (First Timer → 24h),
pending editable-builder access.*
