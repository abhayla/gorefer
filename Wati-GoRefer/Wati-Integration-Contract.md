# Wati ⇄ GoRefer — Integration Contract

> **Scope:** GoRefer's side of the Wati (WhatsApp) integration — how GoRefer sends, how it proves
> delivery, and the gates around it. The **channel/platform** side (delivery health, template
> catalogue + approvals, the nightly report, Wati account facts) lives in
> `C:\Abhay\5Wealths\Wati-Project\`. Zoho's *own* direct-to-Wati sending lives in
> `C:\Abhay\5Wealths\Zoho-Project\`.
>
> Wati tenant `105355` · business number `+91 70806 42020`. Last updated 2026-07-19.

---

## 1. The cardinal rule

**HTTP 200 from Wati means "accepted", NOT "delivered."** Every send must be verified against the
**terminal message status** read back from Wati (`delivered` / `read` / `failed`). Anything else is
self-deception — this is the discipline the whole adapter is built around (doc-08 A3, Gap 12).

---

## 2. `LiveWatiAdapter.send_template` — the send shape

`apps/integrations/wati/adapter.py`.

- **Config from env only**, never inline: `WATI_API_ENDPOINT` (tenant base — the tenant id is IN
  THE PATH, e.g. `https://live-mt-server.wati.io/105355`) and `WATI_API_TOKEN` (a leading
  `Bearer ` is stripped; the code adds the scheme). The adapter **refuses to construct** without
  both, so a flag flip against missing config fails loudly instead of silently no-opping.
- **Endpoint:** `POST {base}/api/v1/sendTemplateMessage?whatsappNumber={digits}`.
- **A real `User-Agent` is REQUIRED** — Wati sits behind Cloudflare, which 403s the default
  `Python-urllib/x.y` signature. This is why manual `curl` worked while the adapter got 403.
  We send `GoRefer/1.0 (+https://gorefer.in)`.
- **Parameter naming — TWO modes, because our templates use two conventions.**
  - **Default (positional remap).** Most templates were created with **positional**
    `customParams` (`"1"`, `"2"`, `"3"` — the `{{1}}`/`{{2}}` placeholders). Callers pass
    *semantic* names so the code stays order-independent, and the adapter remaps by order at
    the boundary: `[{"name": str(i), "value": …} for i, p in enumerate(tvars, start=1)]`.
    Sending semantic names to such a template makes Wati reject the send as "blank text"
    (HTTP 400).
  - **Named (`params["template_params_named"] = True`).** Templates created with **named**
    `customParams` (`{{name}}`, `{{client_id}}`, …) need the names to SURVIVE, because Wati
    resolves them by name. **This is mandatory for a dynamic URL button:** the button's
    `buttonParamMapping` points at a `paramName`, and a button variable has its **own index
    space**, so positional remapping can never reach it — the button renders unfilled.
  - **The caller chooses**, because only the caller knows which template it resolved. The
    adapter does not guess.
  - *Discovered 2026-07-27 (D9).* Submitting a button template with positional body params
    made Wati silently rewrite the button's `{{client_id}}` to `{{1}}` and bind it to the
    **referrer's name** — every send would have rendered
    `gorefer.in/share/wa/Ramesh Kumar`. Caught only by reading the stored
    `buttonParamMapping` back; `ok:true` on create proves nothing about it.

- **Dynamic URL buttons (D9).** Create-time shape, verified against an approved template:
  `buttonsType` is REQUIRED alongside `buttons` (`call_to_action` for URL buttons) or the
  create call is rejected with *"Cannot contain any buttons in none buttonsType"* — nothing is
  created, so it costs no submission. Only the **last** URL segment may be a variable
  (`https://gorefer.in/share/wa/{{client_id}}`). **Wati allows only 10 template submissions per
  hour.**
- **Mixed button sets (refrecord family, 2026-07-27).** A dynamic URL button + a quick-reply
  button in ONE template is accepted under `buttonsType: "call_to_action"`, with each button as
  `{"type": "url"|"quick_reply", "parameter": {"text": …, "url": …, "urlType": "dynamic"}}`.
  With NAMED placeholders (`{{name}}` body, `{{client_id}}` button) the stored
  `buttonParamMapping` survived correctly (`paramName: "client_id"`) — the positional
  param-rewrite trap fires only on positional-body submissions. Still MANDATORY: read the stored
  template back after `ok:true` and verify both buttons + the mapping before trusting it.
- **The ack carries NO message id** (`{"result": true}` only), so `provider_message_id` is
  deliberately returned as `None` — never a fabricated id. That is *why* status reconciliation is
  keyed by mobile + template rather than by id.
- A failed send is a **recorded FAILED notification**, never an exception that strands the lead.

## 3. The fail-closed allowlist gate

Before any network call, `_recipient_allowed(number)`:

- Returns True only if **`WATI_ALLOW_ALL_RECIPIENTS == "true"`** (exact string), **or** the number
  (digits-only) is in **`WATI_TEST_RECIPIENTS`** (comma-separated).
- An empty allowlist with allow-all off **blocks everything** — the safe default.
- Env is read **on every call** (never cached) so the gate always reflects current config.
- A blocked send makes **no network call**; the Notification is recorded `status="skipped"` with
  `skip_reason="recipient not in WATI allowlist (fail-closed)"` — visible in the funnel, never
  silently dropped, and never mistaken for a Meta delivery failure.

This gate is what makes it safe to have `ENABLE_WATI_SEND` on while still not messaging real
people. **Opening it (`="true"`) is a deliberate, human decision** — it is the difference between
"the engine is on" and "real prospects are being messaged."

## 4. Terminal-status verification + the reconcile sweep

**Immediately after send:** `get_message_status(recipient_mobile, template)` reads
`GET {base}/api/v1/getMessages/{mobile}?pageSize=10` and looks for this template's row.

**Matching (two live bugs shaped this):**
1. Wati returns **`templateName = null`** and names the template only inside **`eventDescription`**
   (`'Broadcast message with using "<tmpl>" template …'`). Matching on `templateName` alone never
   matched a real row, so genuinely-DELIVERED messages sat at `accepted` forever.
2. A **bare substring** test then bleeds across versioned names — `…_2026_07_17` is a substring of
   a `…_2026_07_17_v2` row's description, and our real template family has exactly that shape, so a
   v1 send could read the v2 message's status.

Final rule: match `templateName == template` **OR** the **quoted** full name `f'"{template}"'`
inside `eventDescription`. Specific (the full quoted name is unique) and it works against the live
API. If no row positively identifies this template, return the honest non-terminal `accepted` —
never guess.

**The scheduled sweep** — `reconcile_pending_deliveries`, registered every **15 min**
(`setup_schedules`). Terminal status is read *instantly* after send, so anything not yet terminal
would otherwise be stranded at `accepted` forever (there is no Wati delivery webhook). The sweep
re-polls rows at `accepted` older than `RECONCILE_MIN_AGE_MINUTES` (3), finalizes them, and after
`RECONCILE_EXPIRE_MINUTES` (24h) marks a still-unresolved row **FAILED** with
`"no terminal status within reconcile window"` — so a silently-lost send becomes visible rather
than hiding as "accepted".

⚠️ Requires the **qcluster worker alive** (`Q_ASYNC=true` + `gorefer-qcluster.service`). A dead
worker silently stops this sweep; the admin topbar carries a worker-liveness light for exactly that
reason.

## 5. Honest demo semantics — `adapter_kind` + `simulated_delivered`

`LogOnlyWatiAdapter` (used when `ENABLE_WATI_SEND` resolves false) makes **no network call**, so it
must not claim a real delivery. It returns **`simulated_delivered`** — terminal (nothing further
will happen) but deliberately **excluded from `DELIVERED_STATUSES`**, so demo/degraded sends can
never inflate real delivery metrics. Every Notification also stamps **`adapter_kind`**
(`live` | `log_only`), so a demo "delivery" is always distinguishable after the fact.

It also **redacts template params in its log** (names only, never values) — with OTP on and WATI
off, sends route through this adapter and the payload would otherwise carry a plaintext OTP code.

## 6. Config-driven template names

Template names are **never hardcoded**. `apps/config/preferences.notify_template_name(role, lang=…)`
resolves them through the ADR-022 cascade (tenant override → central default), and they are editable
on the Settings screen **with no deploy**. Meta-name validation on save: `^[a-z0-9_]+$`.
See [`Wati-GoRefer-Templates.md`](./Wati-GoRefer-Templates.md) for the current mapping.

Notification *routing* (which of office / prospect / referrer fire) is likewise per-tenant config;
a role turned off is recorded `skipped` with a reason, never silently dropped.

## 7. Flags

| Flag / setting | Gates |
|---|---|
| `ENABLE_WATI_SEND` | live adapter vs log-only. Resolved via the **config cascade** (ConfigGlobal override → env), not the frozen `flags` snapshot |
| `WATI_ALLOW_ALL_RECIPIENTS` | the fail-closed recipient gate (§3) |
| `WATI_TEST_RECIPIENTS` | the allowlist when allow-all is off |
| `WATI_WEBHOOK_KEY` / `_IP_ALLOWLIST` | inbound assisted-capture **and** inbound-message webhook auth (fail-closed on a blank key) |
| `followups_enabled` | the follow-up engine (§8). **Cascade key**, tenant-tier, default OFF — gates enqueue AND the send gate |

## 8. `send_session_text` + the 24h-window follow-up engine (M-FUP-1)

The follow-up engine (`apps/followups/`, spec doc 14) adds one send method and one inbound
touch-point on this adapter boundary. Everything is gated by `followups_enabled` (cascade,
default OFF), so with the flag off nothing here sends or schedules.

**`LiveWatiAdapter.send_session_text(to, message)`** — a **free-form session message**, only
valid while the recipient's 24h window is open. Same contract spine as `send_template`:

- Inherits the SAME fail-closed allowlist (`_recipient_allowed`, §3) — a session send can no
  more reach a non-allowlisted number than a template can. Blocked → `raw_status = 'blocked'`,
  **no network call**.
- Returns **ACCEPTED, never delivery**. A session message carries no template name, so the
  §4 `getMessages`-by-template reconcile cannot key on it; terminal delivery for session sends
  is therefore **verified at the destination on the live test** (rollout gate), not inferred.
  Reconcile-by-conversation for session text is a Phase-2 enhancement, tracked — not built here.
- Endpoint: the v1 tenant-server session surface
  `POST {base}/api/v1/sendSessionMessage/{number}?messageText=…`, consistent with the proven
  `/api/v1/` calls this adapter already makes (§2, §4). ✅ **CONFIRMED (2026-07-24 live probe):** a
  real POST to this endpoint for a CLOSED window returned
  `{"result":false,"message":"Ticket has been expired.","ticketStatus":"CLOSED"}` — proving this is
  the correct endpoint (the Phase-1 checklist's v3 `/conversations/messages/text` path was wrong; it
  does not compose with the v1 tenant base) and that `result:false` is the out-of-window signal the
  adapter parses. In-window session delivery is verified against `getMessages` `statusString`. The
  log-only adapter simulates an accepted session send (no network) so the flow is testable offline.

**Inbound-message webhook → window feed.** `POST /api/wati/inbound` (auth = the §3/§7 shared key,
fail-closed) stamps `last_inbound_at` for the **customer's** number
(`apps.integrations.wati.webhook.record_inbound`). OUTBOUND events (`owner`/`fromMe` truthy) are
ignored — a business-sent message does not open a customer window. On a **fresh** window open (no
prior inbound, or ≥24h since the last) it starts the AP's cadence (one `ScheduledFollowup` per
enabled `FollowupRule` step); a subsequent inbound inside the window refreshes the timestamp (and
counts as a reply for engaged-exit) but does not re-enqueue.

**Auth accepts the key as a header OR a `?token=` query param.** Wati's native webhook sender
delivers the secret as `…?token=<WATI_WEBHOOK_KEY>` (verified on the live tenant — its pre-existing
webhooks post `https://…?token=<key>`) and cannot attach a custom header, so `authenticate()` accepts
the key from EITHER `X-Wati-Webhook-Key` or `?token=`, constant-time compared, still fail-closed on a
blank/absent key. (A query-string secret is access-log-visible — acceptable for a rotatable shared
webhook token; same posture as the existing firekaro webhook.)

**Advisor-callback slot tap (T-104, owner-approved Option B, 2026-08-12).** The same
`POST /api/wati/inbound` payload's `text` field is ALSO checked, in addition to (never instead of)
the window-stamp behaviour above, against the three fixed call-back slot labels
`AdvisorCallbackRequest.SLOT_CHOICES` (`9-12`, `12-3`, `3-6`) — an EXACT match only (trimmed,
case-insensitive; "call me 9-12 please" does not trigger). This exists because a scan of every flow
backup on this tenant found ZERO nodes with a populated `url` — Wati has no working HTTP flow node
here — so a chatbot flow's slot buttons instead send their label back as an ordinary inbound text
message, and GoRefer's own webhook is the only place left to catch it. On a match, `apps/integrations
/wati/api.py:inbound_message` calls the EXISTING `apps.followups.advisor_callback.request_and_schedule`
+ `send_alert` — the identical create-request + immediate-staff-alert path `POST /api/callback-request/`
already uses; no second alert/scheduling implementation. Gated on `ENABLE_ADVISOR_CALLBACK` (checked
at request time, not import time, so it toggles per-request unlike the `/api/callback-request/`
router's mount-time gate). `senderName`/`name` on the payload is passed through as the customer's
name if present; absent, the request is created with a blank name. Idempotency is the SAME
`(tenant, mobile, slot, request_date)` unique constraint the HTTP path already relies on — a repeat
tap the same day is a no-op past the first. No message is ever sent to the customer's own number from
this path — the only outbound is the staff alert.

**Wiring (Wati dashboard → Webhooks, "New Contact Message" event):** add a webhook to
`https://gorefer.in/api/wati/inbound?token=<WATI_WEBHOOK_KEY>`. The "New Contact Message" event is the
customer-inbound trigger; its payload carries the sender in `waId` (which `record_inbound`'s number
resolver reads). Safe to wire with the flag still off — enqueue is inert until `followups_enabled` is on.

**Send gate (per due row, at fire time).** Opt-out (per-AP, tenant+mobile) → cancel; replied /
converted since the window opened (`stop_on_reply`) → cancel; window open → session send; window
closed → template if the step has one (and it isn't session-only), else skip. Delivery is recorded
on the `ScheduledFollowup` row (SENT/FAILED/SKIPPED/CANCELLED) and a PII-free `notification` funnel
event is emitted (no mobile, per #16).

**Window feed — POLLING is the reliable trigger (the inbound webhook is chatbot-suppressed).**
Verified on the live tenant: Wati's "New Contact Message" webhook does NOT fire for an inbound the
account chatbot auto-replies to (the "Welcome" flow swallows it), and no "Message Received" (fire-on-
every-inbound) event is offered in this Wati version — so the webhook can't reliably open windows.
Because a follow-up can only be SENT to a prospect whose mobile GoRefer already knows, the reliable
trigger is a bounded poll: `LiveWatiAdapter.get_latest_inbound_at(mobile)` reads the newest
customer-inbound (`owner=false`) time from `getMessages/{number}` (the same real-time endpoint as
delivery reconcile), and `apps.followups.tasks.poll_inbound_windows` (schedule `followup_inbound_poll`,
every 5 min) checks each candidate mobile — a per-AP config watch-list (`followup_poll_watch_mobiles`)
plus recent `Prospect` mobiles — and calls `record_inbound` when the inbound is newer than the last
recorded, opening the window + starting the cadence on a fresh 24h open. Inert until
`followups_enabled`. The `/api/wati/inbound` webhook endpoint stays in place (harmless; it would fire
as a bonus for any event Wati does deliver).

**Replay protection — idempotency on Wati's OWN event id, because a nonce is impossible
(T-048, 2026-08-06).** Wati's webhook sender is fixed: it carries exactly one credential, the static
`?token=` query param, and cannot attach a signature, a timestamp header, or a nonce. So the Zoho
wax-seal design (HMAC + freshness + one-time nonce) is not available here, and a captured request
stays valid indefinitely. Replay protection therefore lives entirely on GoRefer's side:

- **Dedupe identity** (`apps.integrations.wati.replay.event_key`) — the first of Wati's own body keys
  that is present, in order: **`id`**, then **`whatsappMessageId`**. Both are keys this integration
  has actually observed on Wati message payloads (§10's verified key map / `getMessages` items); no
  invented header or field is read. A payload carrying **neither** falls back to
  `sha256=<digest of the exact request bytes>`, so a byte-identical replay is still refused while two
  genuinely distinct events are never merged.
- **Claim** (`claim_event`) — a UNIQUE-constrained INSERT into `wati_webhook_receipt`
  (`endpoint`, `event_key`). The database decides, so two concurrent replays cannot both win. The
  table is deliberately NOT tenant-scoped, for the same reason as `zoho_webhook_nonce`: the check
  runs before the request is trusted, so per-tenant uniqueness would let a replay succeed by
  claiming a different tenant. The same message id arriving at two different endpoints is two
  distinct events (`endpoint` is a separate column, not part of the key).
- **Ordering of the checks** — auth first, then payload validation, then the ignore-cases
  (`owner`/`fromMe` outbound, missing mobile), and only then the claim. An unauthenticated flood
  cannot fill the table, and a state-changing-nothing event never burns a key that a real message
  would need.
- **Responses.** `POST /api/wati/inbound` answers a duplicate with **HTTP 200**
  `{"status":"ignored","reason":"duplicate","stamped":false,"enqueued":0}` — Wati's native sender
  RETRIES on a non-2xx, and a retry of a message we already recorded must be a benign no-op, not an
  error loop. `POST /api/wati/webhook` (assisted capture, driven by a chatbot HTTP node that does not
  retry-loop) answers a duplicate with **HTTP 409** `duplicate webhook delivery (replay refused)`.
- **Retention.** Receipts are purged after **7 days** by `replay.purge_expired_receipts`, wired as
  the hourly `wati_purge_webhook_receipts` schedule (ADR-047 registry). A receipt older than that
  cannot prevent meaningful harm, because the 24h session window a replay would target has closed.
  Retention is structural security posture — deliberately NOT a tenant config key.

*Why this matters concretely:* `/api/wati/inbound` opens the 24h session window and, on a fresh open,
enqueues the referrer's entire nudge cadence. Before this guard, one captured request URL could be
re-POSTed a day later to re-open the window and re-fire the whole cadence at that person, on demand.

**Stale-status guard — status only ever moves forward (T-048).** There is still **no Wati
delivery-status webhook** (see §5); the only status-applying paths are the send and the reconcile
sweep, and both now funnel through the single `wati.tasks._finalize`, which refuses any status that
does not supersede what is already recorded. The precedence rule lives in the vendor-neutral
`apps/integrations/delivery_status.py` (`supersedes` / `status_rank`):

    accepted(1) < sent(2) < {delivered, failed, blocked, simulated_delivered}(3) < read(4)

`failed` shares rank 3 with `delivered` on purpose — they are mutually exclusive OUTCOMES of the same
step, so a late re-read can never flip a recorded delivery into a failure or the reverse; whichever
terminal outcome was observed first is kept. A refused status is logged and is **not** counted as a
`finalized` row by the reconcile sweep, so the sweep never reports work it did not do. This closes a
real corruption path: `getMessages` is an eventually-consistent list, and a sweep landing on an older
page would otherwise walk a message back from `delivered` to `sent` — a field both the daily WA
engagement report and the follow-up engine read.

**Window timestamps are monotonic (T-048).** `apps.followups.services.stamp_inbound` now refuses an
inbound whose timestamp is **older than or equal to** the one already recorded. Rewinding
`last_inbound_at` is not cosmetic: `window_is_open` is computed from it, so a replayed webhook
carrying its original timestamp (or an out-of-order poll page) would mark a genuinely OPEN 24h window
CLOSED and silently downgrade every in-window session send to the closed-window path.

## 9. Assisted-capture `client_id` validation — strict, per-partner (B4)

`apps/integrations/wati/webhook.py:process_assisted_capture()` — the Wati "Refer
directly" flow — validates the referrer's `client_id` against
**`validate_client_id_for(tenant, raw)`** (`apps/referrals/validators.py`), NOT the
loose spec rule (`validate_client_id`) that the rest of the doc-06 §4.1 bound (4–16
alphanumerics) still describes for lookup paths (admin search, login).

**Why this path is stricter.** A leaked Wati chatbot menu label (`TALK`) satisfied the
loose spec rule and was accepted here as a referrer `client_id` — creating a junk
identity from a menu label, not a person. The same loose rule would also have accepted
PIFS's own partner code (`ZMPHZC`) as a referrer. Because assisted-capture is an
identity-**creating** path (same as `/r/` and `/share/`), it now validates against the
active partner's stricter id pattern instead.

**Pattern resolution — config, not code, per partner (CLAUDE.md §6d).** The pattern is
resolved from the ADR-022 cascade, most specific first:

1. `client_id_pattern__<PARTNER_CODE>` — e.g. `client_id_pattern__ZMPHZC` (per-partner
   override).
2. `client_id_pattern` — tenant/central default.
3. The loose spec rule (4–16 alphanumerics) — used as-is when neither cascade key is
   configured.

`process_assisted_capture` resolves the active partner from the current tenant's
program (`get_active_program`) and passes its `code` into the cascade lookup; nothing
in the code is named after a partner, so onboarding a partner with a different id
shape is a config change, not a code change.

**A misconfigured pattern degrades, it never blocks all referrals.** The resolved
pattern is compiled with `re.compile` at validation time. If it is not valid regex,
`validate_client_id` catches `re.error`, logs it (`invalid client_id_pattern %r —
falling back to the spec rule`), and **falls back to the loose spec rule** for that
call — it does not raise and does not reject the capture. A bad config value therefore
degrades assisted-capture back to pre-B4 looseness for that partner rather than taking
the webhook down for every referrer.

A `client_id` that fails validation (whether against the strict pattern or, on
fallback, the spec rule) raises `AssistedCaptureError` and the capture is rejected —
same external behavior as before, just a narrower set of accepted ids on the happy
path.

## 10. Read-only engagement reporting — `apps/integrations/wati/engagement.py` (T-032)

A daily scheduled job (`wa_engagement_report_daily`, django-q, fires at
`wa_engagement_report_hour_ist` — default 21:00 IST) computes trailing-24h and
trailing-`wa_engagement_lookback_days` (default 7) WhatsApp engagement metrics and
writes a dated markdown report to `wa_engagement_report_dir` (default
`var/reports/wa-engagement/YYYY-MM-DD.md`), then posts an owner digest via the shared
Notifier gateway (`apps.common.notify_owner`). **This is a READ path — it sends
nothing to any customer and never writes to Wati.** The only outbound message it
produces is the owner digest.

**Gating differs from the send adapters.** `get_engagement_reader()` swaps
`LiveEngagementReader` / `LogOnlyEngagementReader` on whether `WATI_API_ENDPOINT` /
`WATI_API_TOKEN` are present in env — **not** on `ENABLE_WATI_SEND`, since reading
requires no send flag. The job itself is gated per-tenant by the cascade key
`wa_engagement_report_enabled` (default `False`); with it off the job is a no-op for
that tenant. With creds absent it still writes a report, explicitly marked "NO LIVE
DATA — WATI credentials absent" rather than crashing (mirrors the
LiveWatiAdapter/LogOnlyWatiAdapter degraded-mode philosophy already used for sends).

**Endpoints read (mirrors T-031's manual pull, `reports/wa-engagement/2026-07-30.md`
Appendix):**

- `GET /api/v1/getMessageTemplates` — template list (name, category, quick-reply
  button labels), used to classify a responder's reply as `quick_reply_button` vs
  `keyword_trigger` (a bare `client_id`-shaped token) vs `free_text`.
- `GET /api/ext/v3/broadcasts` (paged, newest-first, stopped once older than the
  window start) + `GET /api/ext/v3/broadcasts/{id}` — per-broadcast send/delivery/
  read/reply/failure counts and Meta failure codes, bucketed by template + category.
- `GET /api/v1/getMessages/{number}` — inbound history for numbers with a
  `total_replied > 0` broadcast, to classify their response mode.

**Two-base rule (T-033 fix — root cause of a live 404-on-every-page defect):** `/api/v1/*`
calls stay on the tenant-suffixed base configured in `WATI_API_ENDPOINT`
(e.g. `https://live-mt-server.wati.io/105355`), but `/api/ext/v3/*` calls go to the
**same host with the tenant path stripped** (e.g. `https://live-mt-server.wati.io`) —
proven by T-031's evidence scripts. `LiveEngagementReader` derives `v3_base_url` from
the configured v1 endpoint at construction time (no new env var). Before this fix, v3
calls kept the tenant suffix and got HTTP 404 on every broadcasts page.

**Any non-200 on a pull marks that window `degraded=True`** — templates, broadcasts
pages, broadcast detail, or `getMessages` — never a silently-fabricated zero. A
degraded pull renders the same "NO LIVE DATA" marker as the creds-absent path, in
both the report file (a banner above the counts) and the owner digest title; the
counts underneath a degraded window are zero **by construction of the empty pull**,
same as the pre-existing creds-absent path — the banner is what tells a reader they
are not real counts.

**Response classification reuses T-031's confirmed parser reality:** a tapped
quick-reply button arrives in `getMessages` as a **plain-text row** matching the
button's label — `buttonReply` and `interactive` are both `null` — not a structured
button-reply payload. `classify_response_mode()` matches the (case-folded) text
against the live template's quick-reply labels first, then a `client_id` shape regex
(keyword trigger), falling back to free text.

**Numbers are masked in the rendered report** (last-4 only, e.g. `…5000`) — same
masking discipline as every other customer-facing/PII-adjacent Wati artifact in this
repo.

**Verified payload key map (T-034 fix — the parser previously read imagined keys the
live API never returns; every mismatch below was checked against T-031's real capture
files, not guessed):**

| Endpoint | Real top-level key | Notes |
|---|---|---|
| `GET /api/v1/getMessageTemplates` | `messageTemplates` (list) | Was read as `messages` — always empty, so quick-reply labels never matched and every reply fell through to `keyword_trigger`/`free_text`. |
| `GET /api/ext/v3/broadcasts` (list) | `broadcasts` (list) | Was read as `items`/`data` — the T-033-era defect this contract names outright: `total_sends=0` with `degraded=false` even after the v3-host fix. |
| `GET /api/ext/v3/broadcasts/{id}` (detail) | `statistics` (object: `total_sent`/`total_delivered`/`total_read`/`total_replied`/`total_failed`/…) | Was read at the response's top level — the detail call returns the counts nested one level down; a naive top-level read gets nothing. |
| `GET /api/ext/v3/broadcasts/{id}/recipients` | `recipients` (list; `contact_phone`, `status` = `replied`/`failed`/…, `failed_code`) | **Not previously called at all.** The old code invented a `failed_meta_codes` field on the broadcast object and a `whatsapp_number`/`waId`/`recipient` field to identify a single "the" responder per broadcast — neither exists; a broadcast fans out to many recipients, and per-recipient outcome (who replied, who failed with what code) only exists on this endpoint. |
| `GET /api/v1/getMessages/{number}` | `messages.items` (list) | Already correct — verified unchanged against `getmessages_raw.json`. |

Category and template name are **not** on the broadcast object at all (list or
detail) — they are resolved by joining the broadcast's `template_id` against the
`messageTemplates` list (`elementName`, `category`).

**Zero vs unknown, applied per-endpoint:** a 200 response whose body is missing the
expected top-level key (`broadcasts`, `messageTemplates`) is an unknown shape and
marks the pull `degraded=True`; a 200 response with the key present but an empty list
is a legitimate zero and does not.

## 11. GoRefer-side port layer (ADR-045/046)

T-040 Wave 1 (2026-08-04) introduced a vendor-neutral boundary at the top of
`apps/integrations/`: domain code now consumes Wati via
`apps/integrations/ports.py` (`MessagingPort`, `get_messaging_port()`),
`apps/integrations/delivery_status.py` (re-exports `is_terminal` / `is_delivered` /
`classify_failure` from `wati.status`), and `apps/integrations/services.py`
(`queue_lead_notifications`, `record_inbound`). These are pure delegation — no
logic moved, no behaviour change; `LiveWatiAdapter` / `LogOnlyWatiAdapter` still
swap by the same `ENABLE_WATI_SEND` flag exactly as before.

The inbound webhook router also moved **inside** the boundary: `api/wati.py` is now
`apps/integrations/wati/api.py`, re-exported for mounting via
`apps/integrations/router.py` (`wati_router`). URL path (`/api/wati/...`), the
fail-closed 401-before-schema auth ordering, and response shapes are unchanged —
this was a move, not a rewrite. Everything else in this contract (send shape,
terminal-status rule, allowlist gate, reconcile matching) is untouched.

## 12. Fail-closed SERVER-COMPUTED variables — the rule that outranks "it sent" (T-073, 2026-08-10)

**The failure, concretely.** The referral-invite template carries `{{token}}` in its share-hub URL
button. That token is a `django.core.signing` value only GoRefer can compute. A Wati **dashboard
broadcast** does not know that: it fills an unrecognised variable from a contact attribute nobody
sets, the value comes out **blank**, and every recipient receives `https://gorefer.in/hub/` — a
dead link — with a green delivered tick. Wati reports success. Meta reports success. Only the
recipient sees the failure, and nobody tells us.

**The rule.** A template whose server-computed variables the sender cannot fill is **not sent at
all** — not with a blank, not with a placeholder. Refused, with a reason.

**Where it lives (GoRefer side).**

- `apps/integrations/computed_vars.py` — the REGISTRY + the single check.
  - `required_computed_vars(template)` → the params GoRefer itself must mint. Matched on exact
    `elementName` **and** on family substring (`refrecord`, `referandearn_invite`), so a version
    bump or Hindi twin cannot quietly fall out of the registry on rename.
  - `assert_computed_vars_filled(template, params)` → raises `MissingComputedVar` when a required
    param is absent, blank, or whitespace-only. Templates carrying no computed variable pass
    through untouched.
  - Stable machine reason: **`missing_computed_var:<param>`**.
- `apps/integrations/ports.py` — `GuardedMessagingPort` wraps **every** adapter returned by
  `get_messaging_port()`. The guard is therefore a property of the port, not of one caller's good
  manners; the check runs **before** the adapter, so a refused send makes **zero** network calls.
  The Protocol surface is delegated explicitly (`isinstance` uses `getattr_static`, which never
  fires `__getattr__`); `kind` and vendor extras still delegate dynamically.
- Senders that prefer a clean row over an exception (`records_link_send`) call the same check ahead
  of the write and record the recipient as `skipped` with that reason. One check, two call sites.
- **`apps/integrations/wati/tasks.py:send_notification`** (the M5 role-template path — office /
  prospect / referrer alerts) now calls `get_messaging_port()` too, not `wati.adapter.get_wati_adapter()`
  directly (T-074, 2026-08-10 — fixes a T-073 checker finding: the guard was fitted at the port
  factory, but this one caller still bypassed it by importing the raw adapter). Today's M5 templates
  carry no computed variable, so this is a pure pass-through; the fix means a future token-carrying
  template routed through this path is guarded too, instead of silently reopening the T-073 gap.

**Adding a template with a computed variable:** register it in `computed_vars` in the SAME change
that adds it, or the guard does not know to protect it. A template that needs a value only GoRefer
can mint has no safe dashboard-broadcast path — the sender is the only way to send it.

### 12a. Template-approval assertion before a real send

`MessagingPort.get_template_status(template=…)` → `TemplateStatus(name, status, category, simulated)`.

- **Live:** `GET {base}/api/v1/getMessageTemplates?pageSize=200&pageNumber=0`, matched on
  `elementName`. Reads the list from `messageTemplates` / `items` / `data` / `result` (Wati has
  shipped more than one shape). **Fails CLOSED** — HTTP error, unparseable body, or a name absent
  from the inventory all return `UNKNOWN`, never a hopeful `APPROVED`.
- **Log-only:** returns `APPROVED` with **`simulated=True`**, so demo mode runs end-to-end while a
  caller can still tell a simulated approval from a vendor-confirmed one (same honesty rule as
  `simulated_delivered`, §5).
- `records_link_send._assert_template_approved` refuses a whole run (`SendRefused`) when the
  resolved template is not APPROVED, when the check errors, or when the port cannot be asked at
  all. Precedent for why this exists: prod's `otp_whatsapp_template` was a name Meta had **never
  seen**, and every WhatsApp login OTP 400-ed silently while the flag read ON (CLAUDE.md §6c).

### 12b. Per-recipient token-carrying senders

`apps/integrations/records_link_send.py` now serves **two template families** through one code path
(`SendFamily`), so gates cannot drift between them:

| Family | Template cascade key (default) | Params | Category | Event `kind` |
|---|---|---|---|---|
| Records link (T-057) | `records_link_template_en` | `name`, `record_date`, **`token`** | UTILITY | `records_link` |
| Referral invite (T-073) | `invite_template_en` | `name`, `client_id`, **`token`** | MARKETING | `referral_invite` |

- Send shape is unchanged: `template_params_named: True` + a `{"name","value"}` list (§2). Named
  params are mandatory here — a dynamic URL button can only be filled by name.
- One **distinct** token per recipient, minted at send time through
  `api.records_tokens.resolve_link_details` → `apps.accounts.records_link.mint_records_token` — the
  same helper the mint API and the logged-in hub CTA use, so links from a broadcast and from the
  hub can never diverge for one identity. This module never HTTP-calls its own mint endpoint.
- Gates, all applied to both families: `ENABLE_WATI_SEND` (resolved, override-aware) **and each
  family's own `link_flag`** — vendor-confirmed approval; per-run cap; per-family min-gap dedupe
  (separate `kind`s, so the two never suppress each other); opt-out; the allowlist (§3); and
  accepted → terminal-status recording (§4).
- **`link_flag` is NOT the same knob for both families (T-074, 2026-08-10 — fixes a T-073 checker
  finding).** Records link gates on `ENABLE_RECORDS_LINK` (mounts `/records/`); the invite gates on
  **`ENABLE_SHARE_HUB`** (mounts `/hub/{token}`, the page the invite CTA actually links to) — using
  `ENABLE_RECORDS_LINK` for the invite would have let a SHARE_HUB-off + RECORDS_LINK-on tenant send
  an invite whose button opens an unmounted page. `SendFamily.link_flag` names the `flags.*`
  attribute per family; `_assert_flags_on` reads it off the family, never a shared literal.
- **Dry-run is the default** (`manage.py send_invite_links --client-ids …`); `--send` is explicit.
  The preview reports `token=minted`, **never the token value** — a preview a human reads is still
  a place a credential leaks. The token likewise never enters the immutable event log (T-051).
- New cascade keys (rail E-6): `invite_template_en`, `invite_send_max_per_run`,
  `invite_send_min_gap_days`.

**Status today:** the configured invite template is a **DRAFT** at Meta, so `--send` refuses it.
This is capability only — landing it fires no blast.

## 13. Related

- Channel health, template approvals, nightly report: `C:\Abhay\5Wealths\Wati-Project\`
- Templates GoRefer uses: [`Wati-GoRefer-Templates.md`](./Wati-GoRefer-Templates.md)
- Zoho's own direct-to-Wati rules (NOT GoRefer): `C:\Abhay\5Wealths\Zoho-Project\zoho-pifs-crm-state.md`
- Spec: `docs/integrations/08-Zoho-WATI-Integration.md` (Part A), Gap 12/13
