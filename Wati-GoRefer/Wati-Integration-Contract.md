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

## 9. Related

- Channel health, template approvals, nightly report: `C:\Abhay\5Wealths\Wati-Project\`
- Templates GoRefer uses: [`Wati-GoRefer-Templates.md`](./Wati-GoRefer-Templates.md)
- Zoho's own direct-to-Wati rules (NOT GoRefer): `C:\Abhay\5Wealths\Zoho-Project\zoho-pifs-crm-state.md`
- Spec: `docs/integrations/08-Zoho-WATI-Integration.md` (Part A), Gap 12/13
