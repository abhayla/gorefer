`_id`.

* **Immutability:** The `events` table is append-only and never updated in place. All analytical data must be derived from this immutable stream rather than authoritative counters.


* **Lazy Instantiation:** Records for tracking analytics or journeys are created only upon the first inbound click, never pre-loaded based on a customer list.


* **Auditability & Attribution:** Critical entities track status changes and retain an audit trail, explicitly noting the `source` (e.g., `zoho`, `gorefer`, `wati`) of external status updates to prevent fabricating unverifiable events.



---

## 3. Core Bounded Contexts (Sprint 1 Implementation)

Based on the architecture, API surface, and decision records, the foundational bounded contexts for the GoRefer schema include:

### 3.1 Referral Identities & Journeys

This context manages the core tracking relationship between the referrer and the visitor.

* **`referral_identities`**: Keyed by the raw Zerodha `client_id` (e.g., `RJ4521`) and `id_source` (`native`). These are lazily created on the first click.


* **`referral_journeys`**: Ties a visitor (tracked via the `gr_vid` cookie) to a referral link. It records the `source` (referral or `partner_direct`) and tracks the `credited_referrer` exclusively based on Zoho's authoritative sync.


* **Timestamps:** Journeys store multiple distinct dates, including the true `account_opened_at` date imported from Zoho, which drives all conversion analytics.



### 3.2 Lead Capture & Pipeline Sync

This context securely stores prospect data before orchestrating downstream systems (Zoho and WATI).

* **`referral_leads`**: Stores the prospect's `name`, `mobile`, `email`, and `city` to support the capture-first strategy.


* **Consent:** Tracks a mandatory `consent` boolean for DPDP compliance and Meta opt-in hygiene.


* **State Management:** Maintains a `status` (e.g., `NEW`, `KYC_STARTED`, `ACCOUNT_OPENED`) and a `lead_disposition` field that directly mirrors the Zoho CRM pipeline state.



### 3.3 Event Stream & Analytics

This context is the append-only ledger powering all platform intelligence and funnel visualization.

* **`events` (or `referral_journey_events`)**: Logs every sequential step of the funnel, including `LINK_CLICKED`, `LANDING_VIEWED`, `LEAD_CREATED`, and `ACCOUNT_STATUS_IMPORTED`.


* **Bot Filtering:** Includes a `confidence` classification (e.g., `human_high`, `suspicious`, `bot`) and an `is_confirmed_human` boolean that flips to true only after a client-side JS beacon fires.


* **`share_events`**: Explicitly tracks the `channel` (e.g., `whatsapp`, `facebook`) when a user interacts with share affordances.


* **Aggregations**: Tables like `campaign_stats` or `daily_metrics` are populated by background rollup workers for fast, pre-computed dashboard reads.



### 3.4 Platform Configuration & Authorization

This context controls system access, program definitions, and dynamic frontend rendering.

* **`programs` & `landing_configs**`: Stores the configuration for the PIFS landing page, including `landing_mode`, dynamic `benefits`, the swappable `reward_note`, and mandatory compliance disclosures.


* **`admin_users` & `admin_sessions**`: Stores the bootstrap administrator's `email`, Argon2/bcrypt hashed password, and manages JWT refresh tokens. Customer login architecture is disabled for Sprint 1.



### 3.5 Privacy & DPDP Safeguards

This context enforces data minimization and retention policies across the schema.

* **IP Minimization:** Raw IPs are hashed or transformed into coarse city data upon ingestion to avoid storing raw personal identifiers.


* **Retention Limits:** Unconverted prospect PII is strictly mapped for anonymization and purging after a 12-month retention window.