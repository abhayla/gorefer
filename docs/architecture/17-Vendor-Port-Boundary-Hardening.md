# 17 — Vendor Port & Boundary Hardening (Phase 2 of doc 16)

> **Status:** Owner-authorized 2026-08-04 (architect session GoRefer-Fable-031; owner directed
> full autonomous implementation with verification). Executes the Phase-2 burn-down that
> doc 16 §5 (rail E-3) left as a work-list. Decisions here continue doc-16's ADR numbering:
> **ADR-045…ADR-048**. `scripts/architecture_import_baseline.txt` is the work-list; when it
> is empty the E-3 gate hardens into a permanent boundary automatically.
>
> **Goal (owner's words):** Wati and Zoho must be completely disconnected from the domain,
> replaceable anytime, and eventually reusable by other projects. This doc gets GoRefer to
> "replaceable by editing one folder"; cross-project reuse (a shared gateway service, the
> Notifier model) is **Wave 4, parked** until these waves land.

---

## ADR-045 — Role-shaped ports live at the boundary's front door

Vendor-neutral **ports** (Python Protocols + dataclasses + factories) are defined in
**`apps/integrations/ports.py`** — the top level of `apps/integrations/` is already
vendor-neutral (`models.py` proves it) and the E-3 gate pattern (`apps.integrations.wati|zoho`)
already permits it. No new Django app, no INSTALLED_APPS churn.

The interfaces are extracted from the **existing adapter surfaces** (they are already
role-shaped — this is formalization, not redesign):

- **`MessagingPort`** — `send_template(to, template, params) -> SendResult`,
  `send_session_text(to, message) -> SendResult`,
  `get_message_status(provider_message_id, recipient_mobile, template) -> DeliveryResult`,
  `get_latest_inbound_at(mobile)`. Factory `get_messaging_port()` → today returns the
  Wati adapter (live or log-only by flag, unchanged).
- **`CrmPort`** — `upsert_lead(payload, gorefer_reference) -> LeadWriteResult`,
  `fetch_referrer_history(referrer_client_id)`, `upsert_referrer_contact(...)`.
  Factory `get_crm_port()` → Zoho adapter.
- **`CrmReadPort`** — `fetch_contact_by_client_id(client_id)`,
  `fetch_referred_people(referrer_client_id)`. Factory `get_crm_read_port()` → Zoho read
  adapter.
- **Neutral delivery vocabulary** — `apps/integrations/delivery_status.py` re-exporting
  `is_terminal` / `is_delivered` / `classify_failure`. Callers stop importing
  `apps.integrations.wati.status`; the Wati implementation stays where it is.
- **Boundary facade** — `apps/integrations/services.py` for the boundary's task-level
  operations domain code needs by name: `queue_lead_notifications(...)`,
  `enqueue_lead_upsert(lead_id)` (wraps `zoho.tasks.enqueue_upsert`), `record_inbound(...)`,
  `ingest_conversion(...)` (same single sanctioned writer — guardrail 2 unchanged),
  `MAX_SYNC_ATTEMPTS`. Thin delegation only — no logic in the facade.

Factories import vendor modules **lazily (inside the function body)** to avoid app-loading
cycles. Domain code imports ONLY `apps.integrations.ports` / `.services` /
`.delivery_status` / `.models` — never `.wati.*` / `.zoho.*`.

**Why:** an adapter behind a Wati-shaped import is still lock-in; the port's neutral
vocabulary is what makes a replacement vendor (or the Wave-4 gateway) cheap. `apps/otp`
already proved this pattern in this codebase.

## ADR-046 — Webhook HTTP routers are part of the boundary, not leaks

`api/wati.py` and `api/zoho.py` are the vendors' inbound HTTP surface — they parse
vendor-shaped payloads by definition and can never be "rewired through a port." They move
INTO the boundary: router modules under `apps/integrations/wati/` and
`apps/integrations/zoho/`, aggregated by a vendor-neutral `apps/integrations/router.py`
that `api/router.py` mounts (precedent: `apps/followups/api.py` already lives in its app).
URL paths, auth ordering (401-before-schema, fail-closed), and response shapes are
**byte-identical** — this is a file move, not a rewrite.

## ADR-047 — Dotted task paths are a public contract (schedule/async safety)

`django_q` **Schedule rows in the prod DB** store dotted function paths
(e.g. `apps.integrations.wati.engagement.run_scheduled_report`), and `async_task()` calls
pass them as strings. Therefore:

1. **Move-freeze:** any module named in `setup_schedules.SCHEDULES` or in an `async_task`
   string may not move/rename unless the SAME PR updates the registry AND the deploy
   procedure updates prod's Schedule rows.
2. `setup_schedules` gains an **update mode**: when a registered name's `func` or
   `minutes` differs from the SCHEDULES map, it updates the existing row (today it
   no-ops, which would leave prod pointing at a deleted module → hourly ImportError,
   silently).
3. The boundary contributes its own schedule entries via a vendor-neutral
   `apps/integrations/schedules.py` fragment that `setup_schedules` aggregates — clearing
   `setup_schedules.py` from the baseline without hiding the registry.

## ADR-048 — What stays inside the boundary (deliberate non-goals)

- `apps/integrations/models.py` (Notification, Conversion, sync bookkeeping) is
  GoRefer-owned and vendor-neutral — importing it from domain code is fine and NOT part
  of the burn-down.
- `wati/engagement.py` (WA engagement report) and the transport half of `wati/notify.py`
  read vendor APIs by nature; they stay inside the boundary and are reached via the
  facade. Relocating their report-composition halves is a recorded backlog item
  (DF-PORTS-1), **not** a blocker: swappability = "domain never imports vendor," which
  Waves 1–2 achieve. Scope discipline beats cosmetic eviction.
- Rewiring is behavior-frozen: **no** template name, copy, timing, flag, URL, or payload
  change anywhere in Waves 1–3. `golive_smoke --json` output must be equivalent pre/post.

---

## Burn-down map (baseline file → action)

| Baseline file | Wave | Action |
|---|---|---|
| `api/wati.py` | W1 | Move router into boundary (ADR-046) |
| `api/zoho.py` | W1 | Move router into boundary (ADR-046) |
| `apps/referrals/lead_service.py` | W2a | `services.queue_lead_notifications` + `services.enqueue_lead_upsert` |
| `apps/referrals/admin.py` | W2a | `services.MAX_SYNC_ATTEMPTS` + `services.enqueue_lead_upsert` |
| `apps/referrals/management/commands/golive_smoke.py` | W2a | facade (`services`) equivalents |
| `apps/referrals/management/commands/seed_demo.py` | W2a | `services.ingest_conversion` (same single writer) |
| `apps/followups/tasks.py` | W2b | `get_messaging_port()` + `delivery_status` + `services.record_inbound` |
| `apps/otp/adapters.py` | W2b | `get_messaging_port()` + `delivery_status` |
| `apps/otp/ports.py` | W2b | comment/vocabulary neutralization only |
| `apps/otp/recipient.py` | W2b | `get_crm_read_port()` |
| `apps/accounts/onfile.py` | W2c | `get_crm_read_port()` |
| `apps/accounts/service.py` | W2c | `get_crm_port()` |
| `apps/dashboard/profile.py` | W2c | `get_crm_read_port()` + neutral dataclasses re-exported via ports |
| `apps/events/management/commands/setup_schedules.py` | W2c | schedule-registry aggregation + update mode (ADR-047) |

Each PR removes its cleared files from `scripts/architecture_import_baseline.txt` in the
same commit; the E-3 gate output (count N → N−k) is the acceptance evidence.

## Wave contracts (dispatched via /get-work-done)

- **W1** (1 contract, mid-tier): ports + delivery_status + services facade + router moves
  (ADR-045/046). Only `api/router.py` changes outside the boundary. Baseline −2.
- **W2a / W2b / W2c** (3 parallel contracts, cheapest-correct, own worktrees, **unique
  `TEST_DB_NAME` each** — shared-DB collisions read as fake regressions): mechanical
  rewires per the map. Baseline −12 total. No file overlap between the three groups.
- **W3** (1 contract): `setup_schedules` update-mode tests hardening + DF-PORTS-1 scoping
  note + CLAUDE.md §2c code-map refresh + contract-doc "port layer" sections.
- **W4** (parked): shared gateway service (Notifier model). Decided separately with the
  finished ports in hand.

**Worker rails (every contract):** (a) full suite green (`pytest -n 4`, own TEST_DB_NAME),
ruff, `manage.py check`, migration-drift check, `check_architecture.py` count strictly
decreased, Tailwind untouched; (b) PRs touching `apps/integrations/**` must update the
matching `Wati-GoRefer/` / `Zoho-GoRefer/` contract doc in the same PR (§6b gate) — a
"GoRefer-side port layer" section, not a vendor-behavior change; (c) the three guardrail
tests + `tests/test_architecture_rails.py` untouched and green; (d) no behavior change —
if a worker believes one is required, STOP and report, never improvise.

## Deploy & acceptance (architect session, not workers)

1. After W2 lands: **full-tree deploy** (moves delete files — file-copy cherry-picking is
   forbidden for these waves), clear stale `.pyc`, restart gunicorn + qcluster, run
   `setup_schedules` (update mode), verify qcluster log clean of ImportError.
2. Live probes: `/r/{id}` 302 with `c=ZMPHZC`, `golive_smoke` on prod honoring live flags,
   webhook auth still 401-closed, scheduled jobs firing.
3. Final: baseline EMPTY → E-3 gate in hard mode; suite green in CI-parity env;
   `CURRENT-STATE.md` + `COORDINATION.md` updated same turn as the deploy.
