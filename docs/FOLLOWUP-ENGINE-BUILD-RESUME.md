# RESUME — Build the 24h-Window Follow-up Engine (Phase 1)

_Handover from the hub session 2026-07-24. Start a fresh Claude Code session rooted in THIS repo
(`D:\Abhay\VibeCoding\gorefer`) so GoRefer's CLAUDE.md / ADRs / contract-doc CI gates auto-load._

## ⚠️ GOVERNANCE — READ BEFORE BUILDING (discovered 2026-07-24)
This feature = the **"WATI stale-lead auto-nudge"** that GoRefer `CLAUDE.md §6` explicitly **DEFERS to
Sprint 2+**. Building it therefore means **opening a Sprint-2 mission and lifting that §6 deferral** —
an architectural/scheduling decision. **The owner (Design Authority) has authorized this.** So the new
session must: (1) treat the owner's go as the Sprint-2 authorization (confirm in one line at start);
(2) **log the mission as a STATUS entry in `COORDINATION.md`** per §3 before coding; (3) build
**spec-first** against doc 14; (4) obey doc-13 §5 — **Phase 1 is TENANT-SCOPED only, NO PartnerGroup**.
Do not silently drift from the Constitution — this note is the paper trail that the deferral was
lifted deliberately.

## Read first (in order)
1. `docs/architecture/14-24h-Window-Followup-Engine.md` — the full design (THIS is the spec to build).
2. `docs/architecture/13-Partner-Hierarchy-and-Vendor-Independence.md` — the hierarchy constraints:
   **AP = tenant**; §5 says the PartnerGroup/5-tier hierarchy is **MODEL-ONLY, do NOT build it now**.
3. This repo's `CLAUDE.md` + `COORDINATION.md` + contract-doc discipline (integrations boundary).

## Goal — Phase 1 ONLY (tenant-scoped; PIFS is the sole AP)
A new `apps/followups/` app that fires a per-AP-configurable follow-up to an idle prospect while the
WhatsApp 24h window is open, with full CRUD. NO PartnerGroup, NO 5-tier resolution (doc-13 §5).

## Build checklist (all grounded in existing code — see doc 14 §1 for file refs)
- [ ] `apps/followups/models.py`: **FollowupRule** (tenant-scoped editable cadence: offset_minutes,
      channel session/template, body_en/hi, enabled, stop_on_reply) + **ScheduledFollowup** (due-table:
      fire_at, status, dedupe_key).
- [ ] `apps/followups/tasks.py`: `enqueue_followups` (on chat-open) + `fire_due_followups` (sweep) —
      mirror `apps.integrations.wati.tasks.reconcile_pending_deliveries`.
- [ ] Register `followup_sweep` (every 5 min) in `apps/events/management/commands/setup_schedules.py`.
- [ ] Add `send_session_text(to, message)` to `LiveWatiAdapter` (Wati v3 `/conversations/messages/text`),
      inheriting `_recipient_allowed`. Keep `send_template`.
- [ ] Stamp `last_inbound_at` on the contact from `apps/integrations/wati/webhook.py` (window-state feed).
- [ ] Send gate: opt-out → cancel; engaged/replied → cancel; window open → session, closed → template/skip.
- [ ] `apps/followups/api.py` (DRF, tenant-scoped) for rule + instance CRUD; `admin.py`.
- [ ] `followups_enabled` cascade flag (default OFF).
- [ ] Tests (TDD): rule resolution, window-open→session/closed→template/skip, engaged/opt-out cancel,
      idempotency, CRUD state transitions.

## Guardrails
- Contract-doc CI: any `apps/integrations` change moves its contract doc with it.
- Verify delivery at destination (terminal status), never HTTP 200.
- Rollout: behind `followups_enabled=false` → live-test on test numbers **9999900001 / 9999900002**
  → owner copy sign-off → enable.
- Suggested engine: `/development-loop` or loop-engineering (maker≠checker), sonnet workers.

## Open (does NOT block Phase 1)
- §6 fork: keep the Zoho Day-0/1/3/7/14 journey separate (recommended) vs. consolidate into this engine.
  Phase 1 is identical either way — only affects a future Phase 2.

## Already done (context, not to redo)
- The 3-minute Wati Chatbot-Timer close is FIXED (1440 + 15-min exit notice) — unrelated to this build.
- Design reconciled against doc 13; the earlier `docs/whatsapp-reminder-scheduler-plan.md` is a superseded pointer.
