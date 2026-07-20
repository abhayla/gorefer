# Zoho → GoRefer webhook signer — Abhay's copy-paste steps

**Goal:** paste one Deluge function into Zoho CRM and attach it to the workflow that fires
when a lead's account-opening status changes. This adds a tamper-proof HMAC signature to
every status webhook GoRefer receives, so a leaked key alone can no longer fabricate a
conversion. **You paste logic only — never a secret in the code** (the secret lives in a
Zoho Variable). Everything on the GoRefer/server side is already done and staged.

> **You do NOT need to touch any secret value if you don't want to** — after you create the
> empty Variable in Step 1 and tell me its name exists, I set its value for you via the API.
> A manual fallback value is given in Step 1 in case you'd rather paste it yourself.

Total time: ~10 minutes. Steps 1–5 are all inside Zoho CRM's Setup.

---

## Step 1 — Create the secret Variable (holds the shared key, never in code)

1. In Zoho CRM, click the **⚙ Settings** (top-right) → under **Developer Space** click **Variables**.
   (Direct path: **Setup → Developer Space → Variables**.)
2. Click **+ New Variable** (or **New Variable**).
3. Fill in:
   - **Variable Name:** `gorefer_webhook_secret`
   - **API Name:** `gorefer_webhook_secret` (it usually auto-fills — leave as is)
   - **Variable Group:** `General`
   - **Type:** `Text`
   - **Value:** *(leave blank — I'll set it for you via the API once it exists)*
     **OR**, if you prefer to paste it yourself, ask the Engineer for the value
     (`ZOHO_WEBHOOK_HMAC_SECRET` — a secret; it is deliberately NOT written in this doc).
4. **Save.**

➡️ **After saving, just tell me "the variable exists"** and I'll set its value via the Zoho API
(so you don't have to handle the secret). If you already pasted the value above, it's done —
no need to tell me.

---

## Step 2 — Create the signer Function

1. Go to **Setup → Developer Space → Functions**.
2. Click **+ New Function**.
3. Fill in:
   - **Function Name:** `GoRefer Webhook Signer`
   - **Display Name:** `GoRefer Webhook Signer`
   - **Category:** `Automation`  (so it can be attached to a Workflow)
   - **Language / Type:** **Deluge**
4. In the argument mapping (the "Arguments" / "Edit Arguments" panel), add ONE argument:
   - **Name:** `leadId`  → **Type:** `String`  → map it to the workflow's record id
     (in a workflow-triggered function this is usually offered as `${Leads.Lead Id}` — pick that).
5. Paste **the entire contents of the canonical function file** into the function body,
   replacing anything there:

   > **`C:\Abhay\5Wealths\Zoho-Project\deluge\gorefer_webhook_signer.dg`**
   > (moved there 2026-07-19 — Deluge code is filed by its owning system, with its 17 siblings.
   > The signing contract in its header must stay byte-compatible with GoRefer's verifier
   > `apps/integrations/zoho/waxseal.py`; if the seal changes, the `.dg` and this doc change too.)

6. Click **Save**, then **Save** again on the function.

**Field mapping — already set to YOUR real Zoho Leads field names** (verified against your
102-field Leads layout, so you should not need to change any of these):
- `Referrer_Client_Id` → the **referrer's** Zerodha client id (the `r=` value). ⭐ the one
  that actually credits the referrer — this must be right, and it is.
- `Converted_Date_Time` → the true account-opening date/time.
- `Lead_Status` → your status field (picklist). The "opened" value is **`Account Opened with Us`**.
- `Full_Name` → the opener's name.
- `opener_zerodha_account_id` → left **blank on purpose**: your Leads layout has no dedicated
  field for the opened Zerodha account number yet. Add a text field for it later, then add one
  `payloadMap.put("opener_zerodha_account_id", ifnull(lead.get("Your_Field_Api_Name"), ""));`
  line — the webhook works fine without it (it's used only to disambiguate the opener; the
  referrer credit comes from `Referrer_Client_Id`).

If any field name were wrong, the webhook still *authenticates* — GoRefer just records blank
for that field (the HMAC signature is over the whole payload, not any single value). So this
is safe to attach now and fine-tune later.

---

## Step 3 — Attach the Function to the account-status Workflow Rule

1. Go to **Setup → Automation → Workflow Rules**.
2. Either open your existing rule that fires when a lead becomes "account opened", **or**
   click **+ Create Rule**:
   - **Module:** `Leads`
   - **Rule Name:** `GoRefer — notify on account opened`
   - **When:** `On a record action → Edit` (or "Field update"), so it fires when the status changes.
   - **Condition:** `Lead Status is Account Opened with Us` (that is your real "opened" picklist
     value — verified). If you also want to capture accounts opened with other partners/brokers,
     add those `Lead Status` values to the condition as well.
3. Under **Instant Actions**, click **Functions → + New Function** (or attach existing) →
   pick **`GoRefer Webhook Signer`**.
4. In the function's argument mapping, set **`leadId`** = the record's **Lead Id**
   (`${Leads.Lead Id}` in the merge-field picker).
5. **Save** the rule and make sure it's **Active** (toggle on).

---

## Step 4 — Tell me it's done

Message me: **"signer is pasted and the rule is active"** (and, from Step 1, "the variable exists"
if you left its value blank). That's your part finished.

---

## Step 5 — The coordinated flip (I do this — nothing for you)

Once you confirm, I will (all on the GoRefer side, no Zoho changes):
1. Set the Variable value via the API if you left it blank.
2. Do a signed **test POST** end-to-end and confirm GoRefer returns `applied:true` (a live proof).
3. Flip `ENABLE_ZOHO_WEBHOOK_HMAC` **ON** and restart — the moment the signed path becomes the
   only accepted path. (Until then it stays OFF so nothing breaks mid-rollout.)

That's it — after Step 4 you're done; the rest is mine.

---

### Why this is safe to paste before the flip
The signer just *adds* signature headers to the webhook. GoRefer keeps accepting the current
(interim) path until I flip the flag, so pasting this early cannot break the existing sync. The
secret never appears in the pasted code — it's read from the Variable at runtime.
