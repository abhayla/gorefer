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
     **OR**, if you prefer to paste it yourself, use exactly:
     ```
     opHRFwCNpTa1TYiPMzYOqJDo416qmW1WbZW1_yt2e1O-feEqpdkA-_-r0LtysFey
     ```
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
5. Paste **the entire code block below** into the function body, replacing anything there.
6. Click **Save**, then **Save** again on the function.

```javascript
// GoRefer Webhook Signer — signs the account-status payload with HMAC-SHA256 so
// GoRefer can prove the request came from Zoho and was not tampered with in flight.
// The shared secret is read from the CRM Variable `gorefer_webhook_secret` — it is
// NEVER written in this code. Attach this to the workflow that fires on account-open.
//
// Contract (must match GoRefer's verifier exactly):
//   dataToSign = timestamp + "." + nonce + "." + <exact JSON body string>
//   signature  = hmacsha256(secret, dataToSign, "hex")   // lowercase hex
//   headers:  X-Zoho-Signature, X-Zoho-Timestamp, X-Zoho-Nonce
//   The SAME body string that was signed is POSTed as the raw body.

// 1) Load the lead whose status changed.
lead = zoho.crm.getRecordById("Leads", leadId.toLong());

// 2) Read the shared secret from the CRM Variable (not hardcoded).
secret = zoho.crm.getOrgVariable("gorefer_webhook_secret");

// 3) Build the payload. Only send fields GoRefer ingests; keep it a FLAT object of
//    strings. Adjust the right-hand field API names if yours differ (see the notes
//    under the code). Empty values are fine — send "" rather than null.
payloadMap = Map();
payloadMap.put("event_id", lead.get("id").toString());
payloadMap.put("zoho_lead_id", lead.get("id").toString());
payloadMap.put("opener_zerodha_account_id", ifnull(lead.get("Zerodha_Account_Id"), ""));
payloadMap.put("opener_name", ifnull(lead.get("Full_Name"), ""));
payloadMap.put("referrer_client_id", ifnull(lead.get("Referred_By_Client_Id"), ""));
payloadMap.put("status", ifnull(lead.get("Lead_Status"), "account opened"));
payloadMap.put("account_opened_at", ifnull(lead.get("Account_Opened_On"), ""));
payloadMap.put("reward_status", ifnull(lead.get("Reward_Status"), ""));

// 4) Serialize ONCE to a string. This exact string is what we sign AND what we send —
//    they must be byte-identical, so we never re-serialize the map again below.
bodyString = payloadMap.toString();

// 5) Timestamp (epoch SECONDS as a string) + a one-time nonce.
ts = time.now().toEpoch() / 1000;
timestamp = ts.toString();
nonce = zoho.encryption.md5(timestamp + bodyString + secret) + "-" + ts.toString();

// 6) Sign: HMAC-SHA256 over "timestamp.nonce.bodyString", lowercase HEX.
dataToSign = timestamp + "." + nonce + "." + bodyString;
signature = zoho.encryption.hmacsha256(secret, dataToSign, "hex");

// 7) POST the SAME bodyString as the raw body, with the three headers.
headerMap = Map();
headerMap.put("Content-Type", "application/json");
headerMap.put("X-Zoho-Signature", signature);
headerMap.put("X-Zoho-Timestamp", timestamp);
headerMap.put("X-Zoho-Nonce", nonce);

response = invokeurl
[
	url : "https://gorefer.in/api/zoho/status-webhook"
	type : POST
	parameters : bodyString
	headers : headerMap
];

info response;  // shows in the function log; a healthy call returns applied:true
return response;
```

**Field-name notes (adjust the right-hand side only if your Leads layout differs):**
- `Zerodha_Account_Id` → your field holding the opened Zerodha account/client number.
- `Referred_By_Client_Id` → the field holding the **referrer's** Zerodha client id (the `r=` value).
- `Account_Opened_On` → the true account-opening date field (a plain date is fine).
- `Lead_Status` → your status field; when it equals your "account opened" stage this fires.
- `Reward_Status` → optional; leave the line as-is if you have no such field (it sends "").

If a field name is wrong, the webhook still *authenticates* — GoRefer just records blank
for that field. So you can attach it first and fine-tune field names later.

---

## Step 3 — Attach the Function to the account-status Workflow Rule

1. Go to **Setup → Automation → Workflow Rules**.
2. Either open your existing rule that fires when a lead becomes "account opened", **or**
   click **+ Create Rule**:
   - **Module:** `Leads`
   - **Rule Name:** `GoRefer — notify on account opened`
   - **When:** `On a record action → Edit` (or "Field update"), so it fires when the status changes.
   - **Condition:** `Lead Status is <your account-opened stage>` (e.g. `Account Opened`).
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
