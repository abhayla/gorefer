# GoRefer Sprint 2 (revised) — WhatsApp / Wati Referral Amplification

> **Owner:** Abhay / PIFS (Zerodha AP). **Compiled:** 2026-07-08. **Status:** APPROVED for build (design locked with Abhay via grill Q1–Q3 + a live study of the Wati tenant).
> **Scope change:** Sprint 2 is **narrowed to WhatsApp-only** (via Wati). The multi-platform share launcher, web customer-portal, and Google login from `S2-01` are **NOT discarded — deferred to Sprint 3.** This doc supersedes S2-01's platform scope for Sprint 2.
> **Grounding:** Wati facts verified live 2026-07-08 (tenant 105355, number +91 70806 42020) + `Wati-Project/` audit + manifests. Visual truth: `mockups/share-creatives-shortlist.html` (the forwardable creative). Memory: `wati-setup-reference`.

---

## 1. Purpose

Turn PIFS's existing Wati/WhatsApp reach into a **referral-amplification loop entirely inside WhatsApp**: PIFS nudges a client → the client taps a button → GoRefer hands them a **ready-to-forward referral message** (image + caption + their tracked link) → they forward it to friends/groups or post it to Status. Every resulting click is tracked to the referrer.

## 2. The flow (LOCKED — grill Q1 = Option B, native in WhatsApp)

```
PIFS ──(Wati MARKETING template, opt-in clients)──▶ Referrer's WhatsApp
        body sells REFERRER benefit (10% + 300 pts, config)   [Button: "Get my referral message" — quick reply]
Referrer taps button
        └─▶ Wati fires webhook ──▶ GoRefer endpoint
                 GoRefer resolves the contact's client_id, builds the kit from config,
                 and (within the 24h session the tap opened) sends via sendSessionMessage/File:
                   (a) a NUDGE msg: "Forward this to friends & groups, or post the image to your Status."
                   (b) the FORWARDABLE CREATIVE: image + caption selling the USER benefit
                       + gorefer.in/r/{client_id}?s=wa + the SEBI/NSE AP disclosure + risk warning.
Referrer forwards (b) to groups / posts image to Status  ──▶ prospect taps link
        └─▶ gorefer.in/r/{client_id}?s=wa : records click (channel=wa), strips ?s, 302 to Zerodha
```

## 3. Wati specifics (from the live study — build to these, don't assume)
- **Variable convention:** named positional — `{{1}}=name`, `{{2}}=client_id` (Abhay's convention; sample `DA1707`). Contacts carry a **`client_id`** attribute (+ `account_type`), synced from Zoho. **Never call it "ID".**
- **Existing template `zerodha_refer_earn_v3` (+ `_hi`)** has a *dynamic URL button straight to `signup.zerodha.com/api/lead/?c=ZMPHZC&r={{2}}`* — GoRefer **replaces** that because it (a) exposes the partner code in the URL and (b) bypasses click tracking. GoRefer routes via `gorefer.in/r/{client_id}?s=wa`.
- **Capabilities present:** `sendTemplateMessage(s)`, **`sendSessionMessage`/`sendSessionFile`** (free-form within the 24h window a user tap opens — no template cost/cap), interactive **quick-reply / CTA-URL** buttons, **webhooks**. Automations are currently unconfigured (2 rules, off) → the tap→reply logic is a GoRefer build, not a Wati toggle.
- **Category rule (grill Q2):** the nudge is **MARKETING** (promotional → opt-in, per-user cap, ~7×); the kit (post-tap) is a **free session message**. Also submit a stripped **UTILITY** variant to trial. First-touch to a non-opted-in number must be warm/utility.
- **Deliverability caveat (parked):** campaigns run ~60% failure (invalid numbers) — target valid, opted-in contacts. **Token rotation (parked):** the dashboard exposes a live bearer token — rotate later.

## 4. Templates (submit via the `wati-template-create-and-track` skill → track to APPROVED)
- **`gorefer_referral_nudge` (en) + `gorefer_referral_nudge_hi` (hi)** — category MARKETING. Body (EN): *"Hi {{1}}, earn from your Zerodha account 💰 Refer friends to open a free Zerodha account and earn {{REWARD}} per referral. Tap below — we'll send you a ready-to-share message you can forward to friends & WhatsApp groups."* `{{1}}=name`; reward text from config `REFERRER_REWARD_CLAIM` (baked at submit time, not a runtime var). Footer PIFS. **Button: quick-reply "Get my referral message"** (payload `GET_REFERRAL_KIT`). Body must end in static text (Meta rule).
- **`gorefer_referral_link` (UTILITY trial)** — stripped, transactional: *"Hi {{1}}, your PIFS referral link is active: gorefer.in/r/{{2}}. Tap below for a ready-to-share message."* `{{1}}=name`, `{{2}}=client_id`. Same quick-reply button. Submitted to see if Meta grants UTILITY (uncapped, cheaper).
- All bilingual EN + HI (Abhay's audience). Manifest lives at `apps/integrations/wati/wati-templates.json` (extend the M5 manifest).

## 5. The forwardable kit (session messages — GoRefer builds + sends)
- **Nudge message** (text): "Here's your ready-to-share message 👇 Forward it to friends & groups, or post the image to your Status. A personal line from you works best."
- **Forwardable creative** = **image** (one approved design from `share-creatives-shortlist.html`, config-selected) + **caption**: headline "Open a free Zerodha account", the 5 user-benefit lines, `gorefer.in/r/{client_id}?s=wa`, then the **verbatim disclosure + market-risk warning**. Sent via `sendSessionFile` (image) + caption.
- All copy is **config** (`WA_KIT_*` keys) — no inline literals; reward wording only in the nudge template, never in the public kit (grill Q3 / §5.5).

## 6. GoRefer build surface
- **Webhook endpoint** `POST /api/wati/webhook` — authenticated (shared secret / IP allowlist; wax-seal deferred DF-2). Parses the Wati button-tap event, extracts the sender waId + `client_id` (from the Wati contact attribute; fall back to Zoho match by mobile). Idempotent + deduped (a double-tap doesn't double-send). On valid tap → build kit from config → `sendSessionMessage`/`sendSessionFile`. Behind **`ENABLE_WATI_SEND`** (log-only in demo).
- **Redirect** `/r/{client_id}?s=wa` — already exists (Sprint 1); ensure `s` recorded as channel + stripped before the 302 (S2-01 §7). **OG preview page (S2-01 M11)** still in scope so the forwarded link renders a compliant preview card in WhatsApp.
- **Admin trigger** — a controlled "Send referral nudge" action (admin picks opted-in segment) using the `wati-send-and-verify-delivery` skill discipline (allowlist, terminal-status check, dedup, opt-in-aware). Not an auto-blast.

## 7. Config-over-code
`WATI_*` creds (env only); `REFERRER_REWARD_CLAIM`; `WA_KIT_HEADLINE` / benefit lines / nudge text / caption; the selected creative image; the opt-in attribute name; `?s` param name; the quick-reply payload string. Text/creative changes need no code edit.

## 8. Compliance
- Nudge template + kit are advertising material → **Zerodha written approval** + **Meta template approval** before live; disclosures verbatim + un-removable in the kit; **no paid ads / no bare-link spam** (Zerodha T&C cl.15/8.viii). Run the creative + templates through `zerodha-ap-social-media-compliance` before submit/publish.

## 9. Deployment dependency (for the live test)
The webhook + `/r/` redirect must be **publicly reachable at gorefer.in** for Wati to call the webhook and for prospects to click. So a deploy of at least the redirect + webhook is required before the end-to-end live test. **Deploy target is LOCKED: the Hostinger VPS `<PROD-VPS>` (Linux nginx + certbot), NOT the local box `<BACKUP-VPS>` — see `docs/deploy/DEPLOY-TARGET.md` (authoritative).**

## 10. Acceptance = a real live WhatsApp test (the gate)
On this machine, with Abhay logged into Wati + WhatsApp Web: send `gorefer_referral_nudge` to Abhay's number (79726 72473, the safe test recipient) → tap the button → confirm the **nudge + forwardable creative arrive** → **forward to a test group** and **post the image to Status** → confirm the **click registers on `/r/` with channel=wa**. Verify terminal delivery (not HTTP 200). Only then is WM done.

## 11. Missions (see COORDINATION.md)
- **M11** — OG preview page + crawler-not-a-click (kept from S2-01; needed for the WhatsApp link preview).
- **WM-A** — Wati nudge templates (EN+HI MARKETING + UTILITY trial, quick-reply button) → submit + track to APPROVED.
- **WM-B** — GoRefer Wati webhook → resolve `client_id` → send kit (nudge + forwardable creative) via session messages; `?s=wa` attribution; behind `ENABLE_WATI_SEND`.
- **WM-C** — Admin "Send referral nudge" trigger (opt-in-aware, terminal-status-verified).
- **Deferred to Sprint 3:** S2-01 multi-platform launcher (M12), web customer-portal + Google login (M13), poster (M14).

## 12. ADRs to record (`docs/architecture/02`)
- **ADR-029** — WhatsApp-native referral amplification via a Wati quick-reply → GoRefer webhook → `sendSessionMessage` kit (chosen over a web launcher for the WhatsApp sprint).
- **ADR-030** — Wati template variable convention (`name`, `client_id`) + reward wording as config; GoRefer routes the button link via `gorefer.in/r/{client_id}` (never direct-to-Zerodha) to hide the partner code + track clicks.
