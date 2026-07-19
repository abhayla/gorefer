# Zoho ⇄ GoRefer — Current Live State

> **Snapshot: 2026-07-19 ~17:00 IST.** Volatile state that does NOT belong in the contract doc.
> Prod = Hostinger VPS `72.61.240.224`, `gorefer.in`. Re-verify before trusting; flags are
> user-owned and change without code deploys.

---

## 1. Flags right now

| Flag | Value | How set |
|---|---|---|
| `ENABLE_ZOHO_READ` | **ON** | ConfigGlobal override (tenant 1), set 2026-07-19 11:12 UTC |
| `ENABLE_ZOHO_WRITE` | **ON** | ConfigGlobal override (tenant 1), same |
| `ENABLE_WATI_SEND` | **ON** | ConfigGlobal override (tenant 1), same |
| `ENABLE_ZOHO_WEBHOOK_HMAC` | **ON** | `.env` (`=true`), seal ENFORCED |
| `ENABLE_OTP_LOGIN` | OFF | `flags.py` default — do not enable (see §5) |
| `DEBUG` | false | `.env` |
| `TRUSTED_PROXY_HOPS` | 2 | `.env` (Cloudflare → nginx) |
| `WEBHOOK_REQUIRE_IP_ALLOWLIST` | off | deliberate — see contract §5.3 |

`.env` on the box also carries `ENABLE_ZOHO_*=false`, but the **ConfigGlobal override wins**, so
the effective values are ON. Only one tenant exists (`id=1, pifs`); `gorefer.in` → tenant 1.

**Deployed SHA:** `a6d2400`.

---

## 2. What has been PROVEN live (with evidence)

| Capability | Evidence | When |
|---|---|---|
| Real Zoho lead WRITE | Lead created with real numeric `zoho_lead_id` **`475281000041592002`** via the live site (`gorefer.in`), then deleted from Zoho — zero residue | 2026-07-18 11:46 UTC |
| Earlier real write | `zoho_lead_id` `475281000041538002` | 2026-07-17 |
| Real WhatsApp DELIVERED | prospect-welcome to `917972672473`, **terminal** status via `getMessages` (not HTTP 200) | 2026-07-18 11:46 UTC |
| Fail-closed allowlist | office alert to `917388882020` correctly **BLOCKED** (`recipient not in WATI allowlist`) | same run |
| HMAC seal ENFORCED end-to-end | valid signed request → **200 `applied:true`**; tampered body → 401; wrong secret → 401; replay → 401 | 2026-07-18 23:2x |
| Seal test conversion cleaned up | `conversion_id 3` reversed via the designed `reversed:true` path → `is_reversed=True`, excluded from counts | same |
| Zoho signer live in Zoho | Abhay pasted the Deluge signer; workflow rule active; `gorefer_webhook_secret` Variable exists with the matching secret | 2026-07-19 |

**Zoho-side signer wiring (verified against the live Leads layout):**
`Referrer_Client_Id` (referrer credit — the field that matters), `Converted_Date_Time` (true open
date), `Full_Name`, `Lead_Status`. Trigger value: **`Account Opened with Us`**.
`opener_zerodha_account_id` is sent **blank on purpose** — `ClientId` lives on the Zoho *Contact*,
not the Lead the signer reads; GoRefer keys the opener by `zoho_lead_id` and credits the referrer
by `Referrer_Client_Id`, so nothing depends on it.

---

## 3. What is STAGED but not exercised

- **The signer has not yet fired on a real lead.** The seal is proven with synthetic signed
  requests; the first genuine `Account Opened with Us` transition will be the true end-to-end
  proof. Worth confirming from the prod side when it happens.
- **`ZOHO_WEBHOOK_IP_ALLOWLIST`** intentionally empty (contract §5.3).
- **Q-M-OTP-2** — Zoho `client_id → Mobile` recipient lookup is still a stub returning `""`
  (`apps/otp/recipient.py`).

---

## 4. ⚠️ Activity reality-check (do not mistake the platform for GoRefer)

As of this snapshot GoRefer's own database shows **no sends and no Zoho writes in ~24 hours** —
newest Notification and newest Lead are both `2026-07-18 11:46 UTC` (the go-live proof run).
Totals all-time: 12 notifications, 6 leads, 3 conversions.

If live WhatsApp traffic is observed in the Wati console, it is almost certainly **Zoho's own
`zoho_auto_*` workflow rules sending directly to Wati** — independent of GoRefer's flags, and the
top open problem documented in `Zoho-Project/zoho-pifs-crm-state.md`. GoRefer's topbar indicators
(`Zoho: On/Off · WATI: On/Off`) are **flag-driven, not activity-driven** by design (Abhay,
2026-07-18): green means "the switch is on", not "a message just went".

---

## 5. Do NOT flip

- **`ENABLE_OTP_LOGIN`** — the OTP path was repaired (ordered `template_params`,
  mobile+template status reconcile, log redaction) but has never run live, and `otp/recipient.py`
  still can't resolve a recipient from Zoho. Keep off until that's wired.
- **`WATI_ALLOW_ALL_RECIPIENTS`** — see `../Wati-GoRefer/Wati-Integration-Contract.md` §3. Current
  value and its rationale are volatile; check `.env` on the box rather than trusting this line.

---

## 6. Rollback / forensics

- Pre-change `.env` backups: `/var/backups/gorefer-env-pre-*.bak` on the VPS (one per change,
  timestamped) — the fastest way to answer "what was this set to before?".
- Pre-deploy tarballs: `/var/backups/gorefer-pre-*.tar.gz`.
- Every flag/config change is logged as a STATUS entry in `../COORDINATION.md`.
