# Zoho ⇄ GoRefer — Integration Contract

> **Scope:** GoRefer's side of the Zoho integration. What GoRefer writes to Zoho, what it reads
> back, and the webhook contract Zoho must satisfy. The Zoho-side artifacts that *execute inside
> Zoho* (Deluge, workflow rules, the Send Queue) live in `C:\Abhay\5Wealths\Zoho-Project\`.
>
> **Owner:** Abhay / PIFS. Zoho org `passiveincomesolutions` (`60019670093`). Last updated 2026-08-14.

---

## 1. The cardinal rule

**Zoho is the SINGLE authoritative source for conversion + referrer credit** (ADR-013, ADR-016).
GoRefer verifies only what it observes — clicks, landing views, redirects, its own lead captures.
Account-opening and reward status originate **only** in Zoho and are never inferred, overridden,
or fabricated by GoRefer. If Zoho shows no referrer, GoRefer credits **no one**.

Guardrail #2 in code: `apps/integrations/zoho/ingest.py` is the **sole writer** of
`conversion_status` / `credited_referrer` / `account_opened_at`. A CI test rglobs all of `apps/**`
(excluding that file) for any assignment or `.update(field=…)` of those columns and fails the build
if one appears elsewhere.

---

## 2. What GoRefer WRITES to Zoho (the lead upsert)

**Trigger:** landing-form submit (`POST /api/leads/`) or the Wati assisted-capture webhook.
**Order is capture-first:** the lead is persisted in GoRefer's own Postgres **before** any Zoho
call, so a Zoho outage can never lose a lead. Zoho failure does not fail the request; the
`zoho_backfill_unsynced` sweep (every 10 min) retries stranded leads.

**Model-2 upsert-by-mobile.** The lead is upserted keyed on the **normalized mobile**, not blindly
created — the same person submitting twice must not become two Zoho leads. Normalization is one
canonical form everywhere: strip spaces / `+` / `(` `)` / `-`, then prefix `91`
(`apps/common/phone.py`). This matches the Wati/Zoho join-key convention in doc-08 §B4.

Fields written: prospect name, mobile, email (optional), lead source, and the **referrer's Zerodha
client id** (the `r=` value from the referral link). GoRefer never writes lead *status* back to
Zoho — status flows one way only, Zoho → GoRefer.

Gated by **`ENABLE_ZOHO_WRITE`**. With it off, the adapter logs the intended call and writes
nothing (demo-safe).

**Referrer Contact upsert (M13 Path B).** When an admin APPROVES an evidence-verified referrer
(`apps/accounts/service.approve_verification`), the adapter upserts a **Contacts** record —
`POST /crm/v8/Contacts/upsert` with `duplicate_check_fields:["ClientId"]` (the client id is the
referrer's identity; mobile is deliberately NOT the dedup key here). Fields written:
`Last_Name` (the verified registered name), `ClientId`, `Mobile`/`Phone` (bare 10-digit via
`to_zoho_mobile`, same stored format as Leads), `Email` (if known), `IsReferrer=true`,
`Lead_Source="GoRefer"`. **Identity/channel fields only — never account/conversion status**
(guardrail #2 unchanged). Purpose: the referrer's NEXT login resolves an on-file channel (Path A).
Same `ENABLE_ZOHO_WRITE` gate; log-only when off.

## 3. What GoRefer READS from Zoho

Account/contact status enrichment, gated by **`ENABLE_ZOHO_READ`**. Read-only: it never mutates
Zoho. Used to enrich the referral profile and — **Q-M-OTP-2, wired in M13** — to resolve a
referrer's on-file channel from their client id.

**Contact search field-set (M13 extension):** `fetch_contact_by_client_id` now also requests
**`Mobile`, `Phone`, `Email`** alongside the profile-enrichment fields. These feed exactly two
consumers: the login-OTP recipient resolver (`apps/otp/recipient.py` — OTP goes ONLY to the
on-file `Mobile`, falling back to `Phone`; never a typed number, ADR-035) and the ADR-027 OAuth
auto-bind match (Google email vs `Email`, entered mobile vs `Mobile`). They are **not rendered**
on the profile page — they stay on the erasable-PII side of the boundary.

**Token handling:** the OAuth access token is cached **process-wide until ~60s before
`expires_in`** (`apps/integrations/zoho/client.py`). Before that fix every API call re-minted a
token — two round trips per call, and Zoho throttles refresh-token grants per window, which
surfaced as spurious sync failures.

**401 self-heal (M7 pt 7, wired 2026-08-17):** `ZohoHttpClient._request` now retries a `401`
exactly **once**, force-refreshing the cached token first — `force_refresh=True` existed since M9
but no call site ever used it, so a revoked/stale token used to brick every Zoho call (write and
read) for up to the cache's own TTL (~1h) instead of self-healing on the very next call. A second
consecutive `401` (fresh token still rejected) raises, same as any other non-401 HTTP error.

**Token-fetch lock (M7 pt 33):** `access_token()`'s check-then-refresh-then-cache sequence is now
guarded by a per-refresh-token `threading.Lock` — two concurrent cache-miss callers (e.g. two
gunicorn threads both hitting a cold cache) mint exactly ONE grant; the second blocks, then reuses
the cache the first just filled, instead of both racing Zoho's throttled refresh endpoint.

**Transport errors (M7 pt 16):** `_request` now also catches `URLError`/`OSError` (DNS failure,
connection refused, timeout) and raises the same `RuntimeError` shape as an `HTTPError`, mirroring
`apps/integrations/wati/adapter.py`'s transport-error handling. `sync_referrer_audience`'s single
`fetch_referrer_audience()` call is wrapped in a per-run try/except-and-log (matching its sibling
read tasks in `zoho/tasks.py`), so a Zoho blip degrades that scheduled run to a no-op instead of
crashing the job.

### 3.1 Audience sync + send-queue counts (T-126, W3 — decisions ⑫/⑭ of the messaging-engine plan)

Two more `CrmReadPort` methods, both gated by the SAME `ENABLE_ZOHO_READ` flag and issuing GETs
only (guardrail #2: neither writes to Zoho or touches conversion/account status).

**`fetch_referrer_audience()`** — decision ⑫'s READ-ONLY audience source for the T-124/T-125
messaging-campaign engine. Sourced from the Zoho **`Referrers`** custom module (module API name
`Referrers`, internal id `CustomModule3`), via the plain **record-LIST endpoint**
`GET /crm/v8/Referrers` (fields `Client_Id,Mobile,Name,Created_Time`) — **not** `/search` (a full
audience needs no criteria) and **not COQL** (same reasoning as §"Conversion reconciler" below: the
live refresh token has no COQL scope, `/crm/v8/coql` returns `OAUTH_SCOPE_MISMATCH`). Paginated,
200/page, hard stop at 100 pages (20,000 referrers); hitting the cap sets `truncated=True` on the
result and the consuming sync task refuses to treat a partial fetch as a complete audience snapshot
(see below).

**Field map** (`Referrers` → `ZohoReferrerRow`):

| GoRefer field | Zoho `Referrers` field |
|---|---|
| `client_id` | `Client_Id` |
| `mobile` | `Mobile` (nullable live — seen blank on real rows, e.g. `FWW808`/`XJ9068`) |
| `name` | `Name` (the module's primary field) |
| `record_created_at` | `Created_Time` — the drip anchor (decision ⑪) |
| `language` | **always `""`** — the live module (verified via `getFields`) carries no Language
  field. Decision ⑮'s "Zoho language field, EN fallback" therefore always falls back to English
  today; the fallback itself lives in `apps.campaigns.models.MessagingCampaign.template_for`, not
  in this adapter. |

**Consumer:** `apps.integrations.zoho.tasks.sync_referrer_audience` (scheduled hourly as
`zoho_sync_referrer_audience`, same "poll often, gate on config" idiom as
`wa_engagement_report_daily`). The actual cadence is the cascade key
`zoho_audience_sync_frequency_hours` (default 24h) — tracked via `max(SyncedReferrer.synced_at)`
for the tenant, no extra state table. Inert (logged, **no port call at all**) whenever
`ENABLE_ZOHO_READ` is off — deliberately stricter than the usual live/LogOnly swap, because writing
`LogOnlyZohoReadAdapter`'s demo fixtures into the real `SyncedReferrer` table would silently corrupt
who the engine messages. Upserts by `(tenant, client_id)`; mobile normalized via
`apps/common/phone.normalize_phone`. Any currently-`active` `SyncedReferrer` row **not** present in
a **complete** fetch is marked `active=False` (never deleted) — a **truncated** fetch skips the
deactivation sweep entirely so a partial page can never look like "referrer gone". A parity check
(synced-active count vs fetched count) logs a `PARITY MISMATCH` warning loudly on any divergence —
the audience must never silently shrink relative to what Zoho just returned.

**`fetch_send_queue_counts(date_ist)`** — per-`Queue_Status` counts for one IST business date,
grouped **referral-vs-other** (decision ⑭): the future W4 digest's messaging block. Sourced from the
Zoho **`WA_Send_Queue`** custom module (`CustomModule5`) via `/crm/v8/WA_Send_Queue/search`,
criteria `(Business_Date:equals:{date})`, fields `Queue_Status,Template_Name` — again NOT COQL.
Paginated, 200/page, hard stop at 20 pages (4,000 rows/day). Live statuses observed at intake:
`SENT`, `FAILED`, `PENDING`, `SUPPRESSED_CAPPED`, `SUPPRESSED_INVALID`; any status not recognized
rolls into an `OTHER` bucket **within its group** rather than being dropped.

**Grouping rule is config, not a literal** (CLAUDE.md §6d/§6e): the cascade key
`zoho_send_queue_referral_template_prefixes` (default `["gr_", "gorefer_"]`) decides which
`Template_Name` prefixes count as "referral" (the GoRefer/Zerodha stream); everything else — e.g.
the legacy other-broker broadcasts (`angel_one_*`, `stay_connected_*`) — counts as "other". Nothing
is ever dropped: every stream burns the same WhatsApp number's quality rating, so the digest must
account for all of it even while keeping the referral funnel readable.

**Not consumed yet.** `fetch_send_queue_counts` has no caller in this PR — the W4 digest task is a
separate, future slice. This PR ships the read method + contract only.

---

## 4. Status → stage mapping (the mirror)

`apps/integrations/zoho/statusmap.py` maps a raw Zoho status string (lowercased, trimmed) to a
GoRefer stage. The **real PIFS Leads picklist values** are mapped explicitly — verified against the
live 102-field Leads layout:

| Zoho `Lead_Status` | GoRefer stage |
|---|---|
| `Account Opened with Us` | **`account_opened`** ← the PIFS conversion |
| `Not Contacted` / `New` | `new` |
| `Contacted` / `Attempted to Contact` / `Call Not Picked` / `Contact in Future` | `contacted` |
| `Pre-Qualified` / `Interested` | `interested` |
| `In-Progress` / `KYC Started` | `kyc_started` |
| `Not Interested` / `Junk Lead` / `Lost Lead` / `Not Qualified` / `Rejected` | `rejected` |

**`Account Opened with Other Broker` / `… Other Partner` are deliberately NOT mapped** to a PIFS
conversion — those accounts were not opened with us.

⚠️ **Known sharp edge:** `ingest.py` does `map_zoho_status(...) or "account_opened"` — an
*unmapped* status falls back to `account_opened`. That is why the explicit mapping above matters:
without it, a stray `Contacted` webhook would register a false conversion. Because the workflow
rule only fires on the opened status, the practical risk is low, but the fallback is a latent trap
worth revisiting.

**Dates:** the **TRUE account-opening date** from Zoho is stored as a first-class field
(`account_opened_at`), distinct from the sync/import date (ADR-017). All conversion analytics run
off the true date so bulk/off-platform imports land in their real period with no fake day-1 spike.

**Idempotency:** deduped on the Zoho `event_id` (composite fallback = account + referrer + date +
forward/reversed). A repeat delivery is a no-op returning `{"status":"duplicate"}`. Reversals
(`reversed: true`) tombstone the conversion (`is_reversed=True`) rather than deleting it.

**Verified signer behavior (M7 pt 14, checked 2026-08-17 against
`Wati-Project/Zoho-Project/deluge/gorefer_webhook_signer_contacts.dg:39-43`, the live Contacts
signer):** `event_id` is **ALWAYS** present in every fire — it's built unconditionally as
`"contact:" + contact.id + ":" + Account_Opened_On`, never omitted. It is **deliberately STABLE**
(not distinct) across a re-fire of the same contact with the same `Account_Opened_On` — that's what
lets a duplicate webhook delivery for the same opening dedupe as a no-op. Neither this signer nor
`apps/integrations/zoho/reconcile.py` (which mints its own stable `reconcile:<id>:<openedOn>`
`event_id`) currently ever sends `reversed: true` — no live path emits a reversal payload today.

Because the signer always sends `event_id`, `ingest._dedupe_key()`'s composite (`cmp:...`) branch
is unreached by live traffic today — it only activates for a hand-built or future payload that
omits `event_id`. It was still missing the `reversed` flag from its key: a forward conversion and
a later reversal for the same account/referrer/date (both missing `event_id`) would have collided
onto the same idempotency row, and the reversal would have been silently dropped as a
`DuplicateDelivery` of the forward event it exists to undo. Fixed 2026-08-17 by folding
`forward`/`reversed` into the composite key (`ingest.py:_dedupe_key`) — latent-bug hardening, not a
response to a currently-reachable production path.

**Separately surfaced, NOT fixed (out of this task's scope):** the signer's `event_id` formula is
stable per (contact, `Account_Opened_On`) but does **not** vary with `Referrer_Client_Id`. A
referrer correction/de-mapping on the same contact, same opening date, that re-fires the workflow
rule would carry the SAME `event_id` as the original — and would be dropped as a
`DuplicateDelivery`, silently discarding the correction, via the `evt:` branch (not the composite
fallback this task fixed). No live path is known to re-fire the Contacts workflow on a
referrer-only edit today, so this is a latent risk, not a demonstrated live gap — flagged here for
the Design Authority to decide whether the signer's `event_id` should incorporate
`Referrer_Client_Id`, or whether `ingest.py`'s `evt:` branch should treat a referrer-changed replay
as a legitimate re-ingest rather than a duplicate.

### 4.1 Referrer conversion-congrats side-effect (T-058, P-01/Gap 5, 2026-08-09)

When `ingest.py` applies a conversion that reaches `account_opened` (never on reversal, no-op, or
a replay the idempotency guard refuses), it schedules a **one-time referrer notification** via
`transaction.on_commit` through `apps.integrations.services.enqueue_referrer_congrats` →
`apps.integrations.congrats` (vendor-neutral, uses the boundary ports only — not under
`.wati`/`.zoho`, so this side-effect does not itself touch either vendor package).

- **Best-effort, never blocking:** the facade catches and logs any enqueue failure — a broken
  congrats send can never fail or roll back the conversion webhook/reconciler call that triggered
  it.
- **Recipient:** the credited referrer only. Mobile is resolved via `get_crm_read_port()
  .fetch_contact_by_client_id(client_id=...)` (the SAME read port §6c already documents) — never
  from the conversion payload (which carries no mobile) and never guessed.
- **Channel:** an open 24h follow-up window → a session message (gated by the SAME quiet-hours /
  min-gap / opt-out rules `apps.followups.services` enforces for nudges); otherwise a WhatsApp
  template named by the cascade key `referrer_conversion_congrats_template_en`, whose default is
  **empty** — so the template leg stays dormant (recorded as a skipped `Notification`, "no
  template configured") until an operator configures an approved name. Session copy is the
  `referrer_conversion_congrats_body_en` cascade key.
- **Idempotent per conversion, not per event:** one `Notification` row per `Conversion.pk`
  (`idempotency_key = "referrer_congrats:{conversion_id}"`), reserved before any outbound call —
  a re-ingest, reconciler re-sweep, or webhook replay hitting the same conversion can enqueue the
  task again, but the row's unique constraint makes every send after the first a no-op.
- This is **not** a nudge and is **not** subject to `followup_stop_when_converted` — it fires
  precisely because the account converted.

---

## 5. The webhook — `POST /api/zoho/status-webhook`

The **sole conversion-mutation entry point**, and therefore the highest-value target in the system:
a forged request here fabricates a conversion and credits an arbitrary referrer.

### 5.1 Request handling order (security-relevant)

1. Read the **raw request bytes once** — this exact byte string is what the seal signs.
2. **Authenticate FIRST**, before any parsing/validation. Fails closed. A flat `401` with no reason
   (telling the caller *which* check failed would hand them a probing oracle).
3. Only an authenticated caller reaches JSON parsing and schema coercion.

The view takes **no schema parameter**, so Django Ninja cannot eagerly parse the body before auth.
Re-serializing a parsed dict would reorder keys / renormalize spacing and verify a *different* byte
string than Zoho signed.

### 5.2 The HMAC wax-seal (DF-2) — `ENABLE_ZOHO_WEBHOOK_HMAC`

```
signature = HMAC-SHA256(secret, f"{timestamp}.{nonce}.{raw_body}")   # lowercase hex
```

Headers Zoho must send: **`X-Zoho-Signature`**, **`X-Zoho-Timestamp`**, **`X-Zoho-Nonce`**.

Four controls, all required together:
1. **HMAC over the RAW BODY** — proves the sender holds the secret AND that not one byte changed.
2. **Timestamp + freshness window** (`ZOHO_WEBHOOK_MAX_SKEW_SECONDS`, default 300s) — a captured
   request goes stale. `abs()` skew so a far-**future** forged stamp is rejected too.
3. **One-time nonce**, DB-arbitrated via a unique constraint (not check-then-insert, which two
   concurrent replays could both pass). Burned **last** — the only write — so an unsigned flood
   cannot fill the nonce table. Purged hourly past the freshness window.
4. **IP allowlist** applies in both modes.

**Timestamp normalization (ms vs seconds) — important.** Deluge has **no `toEpoch()`**; the valid
path is `zoho.currenttime.toString(fmt).unixEpoch("GMT")`, which returns **milliseconds**. The
verifier therefore normalizes by magnitude: a value `>= 1e10` is treated as milliseconds and
divided by 1000, otherwise seconds (`_normalize_epoch_seconds`). The **signature is still computed
over the exact timestamp STRING that was sent**, so this tolerance never weakens the seal — it only
interprets the freshness value. A stale millisecond timestamp still fails the skew check.

**With the seal ON the static key is NOT a fallback.** Leaving it as an alternative would mean a
leaked key still forges conversions and the seal would be decoration.

### 5.3 Caller-IP resolution

The IP allowlist is a security control, so the caller IP must come from a hop the attacker cannot
forge. `X-Forwarded-For` is client-appendable (nginx *appends* the real peer), so `xff[0]` is
attacker-controlled. `apps/common/netaddr.trusted_client_ip` reads the **(hops)-th XFF entry from
the END** — `DJANGO_TRUSTED_PROXY_HOPS=2` in prod (Cloudflare → nginx → gunicorn). This is
*enforced*, not assumed, because the origin is locked to Cloudflare CIDRs at nginx (direct-to-origin
returns 403), so every request provably transited Cloudflare.

`ZOHO_WEBHOOK_IP_ALLOWLIST` is **deliberately empty**: Zoho does not publish stable/enumerable
outbound webhook IPs and they rotate, so pinning a guessed list would silently reject legitimate
conversion webhooks. The HMAC seal + the Cloudflare origin lock are the real controls;
`WEBHOOK_REQUIRE_IP_ALLOWLIST` stays off.

### 5.4 The Zoho-side signer

The Deluge function Abhay pastes into Zoho is documented step-by-step in
[`Zoho-Signer-Steps.md`](./Zoho-Signer-Steps.md) (same folder). Secret lives in a Zoho CRM
**Variable** (`gorefer_webhook_secret`), never in the pasted code. Contract test:
`tests/test_zoho_signer_contract.py` simulates the exact Deluge signing against the real endpoint
and asserts accept-on-match plus reject on byte-mismatch / wrong-secret / replay / stale-ms.

---

## 6. Which flags gate what

| Flag | Gates | Where resolved |
|---|---|---|
| `ENABLE_ZOHO_WRITE` | creating/upserting the Lead in Zoho | `resolve_flag()` — ConfigGlobal override else `.env` |
| `ENABLE_ZOHO_READ` | status/contact read-back enrichment | `resolve_flag()` |
| `ENABLE_ZOHO_WEBHOOK_HMAC` | seal REQUIRED on the webhook (static key no longer accepted) | `flags.py` env snapshot |
| `WEBHOOK_REQUIRE_IP_ALLOWLIST` | refuse an empty IP allowlist in prod | Django setting |

⚠️ **Flag-resolution gotcha:** `ENABLE_ZOHO_WEBHOOK_HMAC` is read from the **frozen import-time
`flags` snapshot**, while the three integration flags resolve through the **config cascade**
(ConfigGlobal override → env). `settings.py` must call `load_dotenv()` **before** importing
`gorefer.flags` or a `.env`-only flag stays frozen at its default and a `.env` flip silently
no-ops. A static load-order guard test now enforces this.

## 6b. READ-leg referrer NAME sync (scheduled, 2026-07-22)

`apps.integrations.zoho.tasks.sync_referrer_names` (django-q schedule
`zoho_sync_referrer_names`, daily) walks every live `ReferralIdentity`, calls the READ
adapter's `fetch_contact_by_client_id`, and fills/corrects the local `Customer` name
(the Explorer/leaderboard name source) for MATCHED contacts with a `Full_Name`:

- Zoho remains the name truth-source; an unmatched ClientId stays "name not on file".
- **T-130 (2026-08-15):** an existing non-empty Customer name IS now overwritten when
  it disagrees with Zoho — the prior "never overwritten" rule let a stale local name
  (e.g. a `seed_demo` leftover) permanently outrank Zoho once set, which is exactly how
  a real client_id (DA1707) kept showing a demo name in production despite this job
  running daily. GoRefer still never writes to Zoho; Zoho's `Full_Name` always wins on
  a MATCH.
- A companion read-only sweep, `apps.integrations.zoho.tasks.sweep_customer_name_drift`
  (`python manage.py sweep_name_drift`), reports every `Customer` row whose name
  disagrees with the already-synced `Referrers`-module name (`SyncedReferrer`, §3.1
  above) without calling Zoho again, flagging known `seed_demo` client_ids separately
  as `demo_seed_shadow` candidates.
- READ-only against Zoho (Contacts fetch); guardrail #2 unaffected — this path never
  touches account/conversion status.
- Gated by the same `ENABLE_ZOHO_READ` resolution as all read-back enrichment
  (log-only adapter when off ⇒ the sync is a no-op offline).

Why: the profile page always fetched names live from Zoho, but the Explorer reads the
`Customer` table, which nothing populated except referrer login — so referrers who never
logged in rendered nameless even when Zoho knew them (live finding 2026-07-22).

---

## 6c. GoRefer-side port layer (ADR-045/046)

T-040 Wave 1 (2026-08-04) introduced a vendor-neutral boundary at the top of
`apps/integrations/`: domain code now consumes Zoho via `apps/integrations/ports.py`
(`CrmPort`/`CrmReadPort`, `get_crm_port()`/`get_crm_read_port()`) and
`apps/integrations/services.py` (`enqueue_lead_upsert`, `ingest_conversion`,
`MAX_SYNC_ATTEMPTS`). These are pure delegation — no logic moved, no behaviour
change; `LiveZohoAdapter` / `LogOnlyZohoAdapter` (and the read-side equivalents)
still swap by the same `ENABLE_ZOHO_WRITE` / `ENABLE_ZOHO_READ` flags exactly as
before, and `zoho.ingest.ingest_conversion` remains the sole sanctioned writer of
conversion/account status (guardrail #2 unaffected).

The inbound webhook router also moved **inside** the boundary: `api/zoho.py` is now
`apps/integrations/zoho/api.py`, re-exported for mounting via
`apps/integrations/router.py` (`zoho_router`). URL path (`/api/zoho/...`), the HMAC
waxseal auth, and response shapes are unchanged — this was a move, not a rewrite.

T-041 W2a (2026-08-04) rewired the four `apps/referrals/**` consumers (`lead_service.py`,
`admin.py`, the `golive_smoke` / `seed_demo` management commands) to call
`apps.integrations.services` instead of importing `apps.integrations.zoho.tasks` /
`.ingest` directly — pure delegation, no behaviour change. The facade also gained
`observe_zoho_upsert_action(sink)`, a diagnostic-only context manager (moved verbatim
from `golive_smoke.py`) that wraps the selected Zoho adapter's `upsert_lead` for the
duration of a smoke run to report insert-vs-update; it changes nothing about what the
adapter does and is not used on any production write path.

## 7. Related

- Zoho-side execution (Deluge, rules, Send Queue): `C:\Abhay\5Wealths\Zoho-Project\`
- Current live state of this integration: [`Zoho-GoRefer-State.md`](./Zoho-GoRefer-State.md)
- Original spec: `docs/integrations/08-Zoho-WATI-Integration.md`, ADR-013/016/017

## Reversal must un-mirror the referral (fixed 2026-07-26)

The forward ingest mirrors conversion state onto the `Referral` (`conversion_status`,
`credited_referrer`, `reward_status`, `account_opened_at`, `status="confirmed"`). Reversal
(`{"reversed": true}`) previously tombstoned the `Conversion` (`is_reversed=True`) and emitted
`conversion_removed` — but **never un-mirrored the referral**.

**Demonstrated live** on referral 17: after a sealed reversal the referral still read
`conversion_status="account_opened"` with `credited_referrer` set and **zero** live conversions
behind it. Three consequences:

1. the referrer stayed **credited** for an account Zoho had de-mapped;
2. the dashboard / Referral Profile still showed a conversion that no longer existed;
3. `apps.followups.services.has_converted()` kept returning True, so the prospect was
   **permanently suppressed** from follow-up nudges.

**Now:** `_apply_reversal` clears `conversion_status`, `credited_referrer`, `reward_status` and
`account_opened_at`, stamps `conversion_source`/`conversion_synced_at`, and returns
`status` to `"opened"` — **but only when no non-reversed `Conversion` remains on that referral.**

**The conditional matters.** A referral can carry several conversions (prod referral 1 has a live
`ZA9001` alongside a reversed row). Reversing one must not un-credit a referral that another live
conversion still legitimately supports. Reversal is therefore *last-one-out*, not per-row.

Unchanged: the `Conversion` row is still tombstoned rather than deleted (audit retained), the
`conversion_removed` event still fires, and the affected period is still marked dirty off the
**true** `account_opened_at` (ADR-017), so a reversal lands in the month the account was opened.

Guardrail 2 is respected: this write happens inside `apps/integrations/zoho/ingest.py`, the sole
Zoho-sourced path permitted to change account/conversion status.

## Conversion reconciler — the webhook is no longer the only delivery path (P0, 2026-07-26)

**What went wrong.** For a month the webhook delivered **nothing**, and nobody could tell.
Two independent causes:

1. **Wrong module.** The ingest is built around Zoho **Leads** (`zoho_lead_id`; and
   `followups.services.has_converted` reads `Lead.status`) — but a Zoho lead that converts
   **becomes a Contact**. The account-opened event never occurs in the module anything watched, so
   the workflow rule never fired and `POST /api/zoho/status-webhook` was never called. Evidence:
   0 Zoho-originated POSTs across 14 days of continuous nginx logs; all 17 were internal tooling.
2. **Nothing reconciled.** Without a sweep, *"no conversions arrived"* and *"no conversions
   happened"* are indistinguishable. Six real openings — three referred — sat uncredited while the
   dashboard and the 21:30 report both reported `accounts_opened: 0`.

**What now exists.** `apps/integrations/zoho/reconcile.py` +
`manage.py reconcile_conversions`, registered as the scheduled task `zoho_reconcile_conversions`
(every 15 min). It polls Zoho Contacts and ingests anything GoRefer is missing.

**It does not replace the webhook — it makes webhook delivery non-critical.** A missed, failed or
mis-triggered webhook self-heals on the next sweep. That property is worth more than fixing the
trigger alone, because the trigger can silently break again.

**Field map (Zoho `Contacts` → ingest payload):**

| Ingest field | Zoho Contacts field |
|---|---|
| `opener_zerodha_account_id` | `ClientId` |
| `referrer_client_id` | `Referrer_Client_Id` — blank stays blank, credit NOBODY |
| `account_opened_at` | `Account_Opened_On` (the TRUE date, ADR-017) |
| `status` | `Account_Status` (null in practice; ingest defaults to account-opened) |
| `opener_name` | `Full_Name` |

**Endpoint choice is deliberate: `/crm/v8/Contacts/search`, NOT COQL.** The live refresh token has
no COQL scope — `/crm/v8/coql` returns `OAUTH_SCOPE_MISMATCH`. Using COQL would require the owner to
re-authorise Zoho before conversions could flow again. Search is the same endpoint `read.py` already
uses in production, so it needs no new permission. Results are paginated (200/page, hard stop at 20
pages); processing only the first page would look like success while dropping conversions.

**The account-pattern filter is load-bearing, not cosmetic.** The same Contacts module holds
non-Zerodha accounts — `AACK095261` (AngelOne) sits beside the Zerodha rows. Without
`zoho_reconcile_account_pattern` (default `^[A-Z]{2,3}[0-9]{3,4}$`) the sweep would invent PIFS
conversions for another broker's customers and credit PIFS referrers for accounts PIFS never opened.

**Guardrail 2 intact:** the reconciler only READS Zoho and hands each row to
`ingest.ingest_conversion`, the sole sanctioned writer of conversion/account status. It never sets
status itself and never infers a conversion Zoho does not assert.

**Config keys** (per `CLAUDE.md` §6d — behaviour is configuration): `zoho_reconcile_enabled`,
`zoho_reconcile_since`, `zoho_reconcile_account_pattern`.

**Idempotent** on `event_id` (`reconcile:<contactId>:<openedOn>`) via `ZohoSyncIdempotency`, so the
15-minute sweep is safe forever. Verified live: a second run re-processed the same 6 rows and the
conversion count did not change.


## event_id derivation (Zoho-side signer) — verified live 2026-08-17 (T-170)

The Deluge signer builds `event_id` as `contact:<contact.id>:<Account_Opened_On>:ref:<Referrer_Client_Id>`
(leads path analogous). A referrer CORRECTION therefore mints a NEW event_id and flows through
GoRefer's dedupe as a fresh event; unchanged re-deliveries keep a stable id and dedupe as
duplicates. Timestamp in the wax-seal is TRUE UTC epoch (Deluge `zoho.currenttime.toLong()`) —
the prior IST-text-parsed-as-GMT skew (19800s) that silently 401'd every webhook is fixed.
Three-shot live test-fire evidence: wati-project PR #45 (accepted / duplicate / referrer-change
accepted). Historical note: before this fix the webhook path was effectively dead behind the
15-minute reconcile backstop.
