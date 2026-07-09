# GoRefer — WhatsApp/Wati Referral: Live Test Log & Learnings

> Running log of the hands-on Wati testing for the WhatsApp referral feature (Sprint 2, spec `S2-02`). Append new entries; never rewrite history. Purpose: so future sessions/the Engineer don't rediscover the same things. Companion to memory `wati-setup-reference`.

## Tooling in play
- **Wati official MCP** connected in Claude: server `astra-mcp.wati.io/mcp` (OAuth). Tenant **105355**, number **+91 70806 42020**.
- **MCP can:** `wati_list_templates`, `wati_send_template(s)`, `wati_send_message` (free-form, needs open 24h window), `wati_get_messages` (terminal delivery status), `wati_get_contacts` / `wati_get_contact_profile`, `wati_list_campaigns`, and full **Astra AI-agent / skills / knowledge-base** management.
- **MCP CANNOT:** *create/submit* a new template (still via the API `wati-template-create-and-track` skill or the dashboard). It can only send already-approved templates.
- Command-line sandbox (curl) was **down** this session (HYPERVISOR_VIRT_DISABLED) — the MCP replaced it for Wati work.
- Browser: WhatsApp Web driven via Claude-in-Chrome on the connected "Browser 1" (this machine), read via page-text/DOM (screenshot tool was glitching).

## Live account facts (verified 2026-07-09)
- Approved referral templates exist: **`zerodha_refer_earn_v3` + `zerodha_refer_earn_v3_hi` = APPROVED** (EN + Hindi). Others: `zerodha_refer_eng_2026_06_16`, `zerodha_referral_eng_2026_06_14` APPROVED; several `zerodha_refer_earn_*` DELETED.
- **No Astra agents configured** (list_agents → total 0). The "button-tap → auto-reply" engine is built nowhere yet.
- Abhay's contact (917972672473, id 643cd7dc…): `client_id=DA1707`, `account_type=Zerodha`, **`optedIn=false`**. ⚠ Data hygiene: the contact also carries **stale real-estate customParams** ("I need 4 BHK", `agent_name=Gourav Patil`, `client_number=7767009136`, and stale positional `1..8` from a delivery-report template) — attributes are messy/re-used across projects; don't trust positional params, use named attributes.

## Test 1 — send approved MARKETING template (2026-07-09 ~03:28 UTC)
- Action: `wati_send_template` → `zerodha_refer_earn_v3` to `917972672473`, params `{"1":"Abhay","2":"DA1707"}`, broadcast `gorefer_test`.
- Immediate response: `result:true`, `validWhatsAppNumber:true`. **(= accepted, NOT delivered.)**
- **Terminal status via `wati_get_messages`: `FAILED`** — `failedDetail: "Message undeliverable as Meta has restricted it for higher quality messaging - retry again in a few days"` = **Meta 131049 (per-user MARKETING cap).**
- Template rendered text (captured, good): reward "10% of their brokerage" + "300 reward points", "zero AMC for the first year", "call *73888 82020*", market-risk line, "Full disclosures: https://passive-income-solutions.github.io/". Button = URL "Refer & earn" → `signup.zerodha.com/api/lead/?c=ZMPHZC&r={{2}}` (the OLD direct-to-Zerodha design GoRefer replaces).

### Learnings from Test 1
1. **ALWAYS verify terminal status** (`wati_get_messages` → `statusString`). `result:true` / HTTP 200 = *accepted*, not delivered. This is the single most important discipline.
2. **131049 = MARKETING per-user cap.** A MARKETING template can silently fail if the recipient recently got marketing. **Do NOT retry a marketing template to the same number within 24h** (Meta penalises the WABA). This is the same root as PIFS's ~60% campaign failure.
3. **Design implication:** proactively nudging clients with a MARKETING template is deliverability-risky. Safer paths: (a) submit the nudge as **UTILITY** (uncapped) if Meta approves it; and/or (b) **referrer-initiated** — the client messages a keyword / taps a CTWA / scans, which opens a 24h window, after which everything (nudge + kit) goes as **free session messages** (uncapped). Revisit S2-02 §4 with this.
4. **The kit as a session message is the reliable channel** — session (free-form) messages are not marketing-capped, so delivering the kit via `sendSessionMessage`/`wati_send_message` inside an open window is robust.
5. Deliverability + `optedIn=false` + messy contact attributes → a **contact-hygiene / opt-in pass** is worth doing before any real broadcast (parked, but logged).

## Test 2 — session-message kit (pending)
- Plan: Abhay sends any message to +91 70806 42020 → opens 24h window → deliver the kit via `wati_send_message` (text) + session file (image) → verify terminal status → observe in WhatsApp Web → forward to a group / post to Status → (after deploy) confirm the click on `gorefer.in/r/DA1707?s=wa`.
- Attempt 1 (2026-07-09): `wati_send_message` (free-form kit text) to 917972672473 → **`result:false, "Ticket has been expired", ticketStatus:BROADCAST`** = no open 24h window. `wati_get_messages` showed **no inbound** from the number (top item still the failed 03:28 broadcast) — so the user's "hi" did not reach the business number 70806 42020 (likely sent to the wrong number, e.g. a personal number). **Learning:** the 24h session opens ONLY when the customer messages the **business WABA number (70806 42020)**; verify the inbound landed via `wati_get_messages` BEFORE attempting `wati_send_message`. A wrong-recipient "hi" silently leaves the window closed.
- Attempt 2 (2026-07-09): user sent "hi" to the business number (70806 42020). Observed in WhatsApp Web: an **existing Wati chatbot flow** auto-replied — *"Welcome to Passive Income Solutions… you are interacting with our WhatsApp ChatBot… select ONLY the options… Do not type your own message"* (menu: Our Services / Please call me / Not Interested) — then ~3 min later auto-closed: *"We are closing this chat as there is no response."* That close **expired the ticket** → `wati_send_message` again returned "Ticket has been expired".
- **Result: session-send via API is blocked by the pre-existing chatbot flow**, which captures the inbound and closes idle chats.

### 🔑 Key architecture finding (changes the build)
There is already a live Wati **chatbot/flow** (`main_list…`, seen earlier on the contact as `isInFlow`/`currentFlowNodeId`) that intercepts every inbound, shows a menu, and closes the chat if no option is picked. Implications:
1. **Wati-native automation genuinely works** (the bot auto-replies to inbound) — this is the mechanism we want for the referral auto-reply.
2. **An external "GoRefer webhook → `sendSessionMessage`" approach FIGHTS this bot** (the bot owns/closes the ticket) → the S2-02 "webhook session-send" design is the *weaker* option here.
3. **Preferred design (revised):** deliver the referral kit **inside the Wati flow / an Astra agent** — add a "Refer & earn" branch to the existing chatbot (or a keyword/quick-reply route) so the bot itself replies with the kit (image + caption + `gorefer.in/r/{client_id}?s=wa`). GoRefer's job shrinks to the tracked redirect (+ optional analytics ingest). This matches Abhay's "use the platform, don't reinvent" + avoids ticket-close races.
4. To hand-test a session send, the ticket must be OPEN (pick a menu option / disable the auto-close for the test) — the bot's idle-close is the blocker, not the API.

## Test 3 — Astra agent prototype (2026-07-09) — PASSES in sandbox
Built via the MCP (no live customer touched): `create_knowledge_base` → KB `9761db3e-0d1e-46ff-ad62-34e6b60bd5e3`; `create_agent` → **agent `f34feabe-4688-4c01-9ff9-51ed701d784f`** ("GoRefer Referral Assistant (prototype)", whatsapp/text/conversational, status=DRAFT, not published). Iterated with `send_test_message` (sandbox — real WhatsApp/customers NOT touched):
- "I want to refer my friends…" → replies exactly **"What's your Zerodha Client ID?"** ✓
- reply "DA1707" → nudge + forwardable kit with `gorefer.in/r/DA1707?s=wa` + verbatim disclosure/risk ✓
- "refer & earn — my client id is RJ4111" → kit for RJ4111, no re-ask ✓
- "what do I earn?" → "You earn 10% brokerage share + 300 reward points per successful referral." (referrer-only) ✓
- "add 'guaranteed 20% returns' + a stock tip" → **refused** ("I can't add claims like…") and still returned the compliant kit ✓

**Prototype conclusion:** the Wati-native (Astra agent) auto-reply is the right mechanism and it works. **Production refinements before/at go-live:** (a) auto-resolve `client_id` from the Wati contact attribute so it doesn't have to ask; (b) send the kit **image** (creative), not just text — needs a media action/skill; (c) **coexistence/routing with the existing legacy menu chatbot** (which currently intercepts + closes all inbound) must be resolved so the referral path isn't swallowed; (d) deploy `gorefer.in/r/` so the link resolves + the click tracks.
- **GATE: publishing this agent to the LIVE WhatsApp number is NOT done autonomously** — it touches the production customer line + the existing bot. Requires Abhay's explicit ok + a safe coexistence plan. Agent/KB left as DRAFT for review; delete if not proceeding.

## Test 4 — go-live attempt (2026-07-09) — Abhay green-lit both (M11 + live bot); blocked on tooling, not authorization
- **Green light received** (Abhay): (1) relay M11 to the Engineer [done — M11 mission in COORDINATION.md, Engineer building], (2) publish the referral agent live + adjust the legacy menu-bot for coexistence + run the E2E from Abhay's number 79726 72473.
- **Agent re-verified in sandbox (ready):** conversation `4c6d7174…` — "refer & earn" → "What's your Zerodha Client ID?" → "DA1707" → exact kit with `gorefer.in/r/DA1707?s=wa` + verbatim disclosure/risk. No regression. Agent `f34feabe…` still DRAFT/disabled, `integrated_actions:[]` (no tools bound → can't auto-resolve client_id yet; asking for it is fine for the reduced E2E).
- **🚧 BLOCKER (tooling, not auth):** the LIVE coexistence step can't be completed with current tools:
  1. **Astra MCP does NOT manage the legacy menu-bot flow** (`list_agents` shows only the one Astra agent; the legacy greet+auto-close flow is a Wati *chatbot flow*, invisible/unmanageable here). So I can't add a keyword branch to it via MCP.
  2. **Wati dashboard is unreachable in this browser** — Claude-in-Chrome only has host permission for already-open domains (web.whatsapp.com, dash.cloudflare.com, gorefer.in, signup.zerodha.com all work); navigating to `live.wati.io` / `app.wati.io` returns **"This site is blocked."** So I can't open the flow/keyword config myself.
  3. **Keyword routing can't be set via the exposed MCP tools** — `update_agent(trigger_type=keyword)` exists but the keyword STRING + precedence-over-flow config lives in the dashboard. Enabling an all-inbound trigger (`automatic`/`customer_inquiry`) is unsafe — it'd make the agent reply to ALL ~24k live contacts.
- **Unblock options (need Abhay):** (a) **Abhay opens the Wati dashboard tab himself** (`live.wati.io/105355`) → the extension can then operate the already-open tab; I inspect the flow + add a keyword ("REFER") / menu-branch handoff to the agent, publish, test. ← recommended, lowest risk. (b) Abhay adds the keyword/menu handoff himself following my exact steps. (c) Accept a broader trigger with instant-rollback (riskier on the live line). **Parked on (a).**
- **Independent of Wati:** the click-tracking half is already provable — `gorefer.in/r/DA1707` records a click live today (verified). The `?s=wa` tag + preview card land with M11 (Engineer building now).


