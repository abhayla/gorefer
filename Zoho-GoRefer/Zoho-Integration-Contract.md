# Zoho ⇄ GoRefer — Integration Contract

> **Scope:** GoRefer's side of the Zoho integration. What GoRefer writes to Zoho, what it reads
> back, and the webhook contract Zoho must satisfy. The Zoho-side artifacts that *execute inside
> Zoho* (Deluge, workflow rules, the Send Queue) live in `C:\Abhay\5Wealths\Zoho-Project\`.
>
> **Owner:** Abhay / PIFS. Zoho org `passiveincomesolutions` (`60019670093`). Last updated 2026-07-19.

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
surfaced as spurious sync failures. `force_refresh=True` re-mints on a 401.

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

**Idempotency:** deduped on the Zoho `event_id` (composite fallback = account + referrer + date).
A repeat delivery is a no-op returning `{"status":"duplicate"}`. Reversals (`reversed: true`)
tombstone the conversion (`is_reversed=True`) rather than deleting it.

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
adapter's `fetch_contact_by_client_id`, and fills the local `Customer` name (the
Explorer/leaderboard name source) for MATCHED contacts with a `Full_Name`:

- Zoho remains the name truth-source; an unmatched ClientId stays "name not on file".
- Existing non-empty Customer names are NEVER overwritten (referrer-login names win).
- READ-only against Zoho (Contacts fetch); guardrail #2 unaffected — this path never
  touches account/conversion status.
- Gated by the same `ENABLE_ZOHO_READ` resolution as all read-back enrichment
  (log-only adapter when off ⇒ the sync is a no-op offline).

Why: the profile page always fetched names live from Zoho, but the Explorer reads the
`Customer` table, which nothing populated except referrer login — so referrers who never
logged in rendered nameless even when Zoho knew them (live finding 2026-07-22).

---

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
