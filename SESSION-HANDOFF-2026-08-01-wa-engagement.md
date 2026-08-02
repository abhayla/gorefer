# SESSION HANDOFF — 2026-08-01 ~08:15 IST (WA engagement program, session was at 98% context)

**Read order for the new session:** this file → `CURRENT-STATE.md` (updated through T-037) →
`COORDINATION.md` tail → the conversation-map SSOT artifact
`https://claude.ai/code/artifact/18a28208-60ae-456d-a534-f745a87acb5d` (approval-gates chronicle
holds ROUND 5/6 + the KM escape-fix entry, currently state **BUILDING**).

## ⏸ IN-FLIGHT ACTION — resume THIS first

I was mid-way through **live-testing the KM chatbot escape-route fix as a real contact**, driving
the owner's PERSONAL WhatsApp Web via claude-in-chrome (browser "Local HP PC",
web.whatsapp.com, chat **"Passive Income Solutions"**). I had JUST typed "Know More" and pressed
Enter — the message sent, but I never saw the reply (owner interrupted for this handoff).

**Resume:** reconnect the browser (switch_browser → "Local HP PC"), open that chat, screenshot,
and verify the reply. Then complete the owner-approved test sequence AS the contact:
1. "Know More" → 3-button menu must appear (EN: Get my referral link / Open demat account / Talk to advisor)
2. Tap **Get my referral link** → ID ask (copy now ends "…Or reply *menu* to go back.")
3. **Tap "Open demat account" instead of typing** → MUST route to the open-account card instantly (this was the original defect: the question node swallowed taps)
4. Tap **Talk to advisor** → advisor message
5. Type **menu** → menu returns
6. Note: outside business hours (9:00–19:00 IST) the R1 off-hours auto-reply may appear alongside — known, not a defect.

**On pass:** flip the map's KM entry from BUILDING to LIVE (edit the artifact via Artifact tool
with `url:` the SSOT link above; fetch-merge if 409 — other sessions edit it too) and tell the
owner it's verified. **On fail:** flow surgery details below.

## KM flow fix — what was done (2026-07-31 evening → 08-01)

- Defect (owner screenshots): regex-validated Question nodes swallowed every sibling button tap.
- Fix LIVE in flow **KM Universal Menu** (flowId `646df1b3ec5598a8712d6165`, now v5, 32 nodes):
  both ID questions (kmlq_en/kmlq_hi) validation→None + menu hint; escape condition chains
  (Equal on each sibling label + "menu"/"Menu"); Back-to-menu buttons on link/open cards both
  lanes. Verified structurally: 32/32 nodes, zero dead references.
- **Wati write-API gotchas learned:** `Contains` conditions are SILENTLY DROPPED by updateFlow
  (only `Equal` persists — v4 write lost 6 nodes, ok:true anyway); always GET-verify node count
  + integrity after. Full recipe + 74-key write format: Wati-Project
  `.claude/skills/wati-dashboard-automation/SKILL.md` LEARNING LOG (2026-07-31 entry) +
  backups in `Wati-Project/backups/` (`km-flow-backup-2026-07-31-pre-escape-fix.json`).
- **Stale-session trap:** the owner's TEST-CONTACT phone (the number in
  `WATI_TEST_RECIPIENTS`, ends …73) is STUCK in the OLD question node from 07-31 18:49 — Wati
  pins in-flight conversations to old flow state, so even "Know More" gets the old regex nag
  there. Unstick: that phone sends any `^[A-Za-z0-9]{4,16}$` text (e.g. RJ4521) to complete the
  stale question, or the session expires naturally. Fresh sessions (like the personal number)
  get the new flow.

## Program state (all verified, evidence in GetWorkDone/)

- **Fallback engine (§6f): LIVE, EN lane real sends** — `fallback_enabled=true, dry_run=false`,
  map `{"en":"gr_platform_gorefer_refrecord_en_2026_07_31","hi":""}` (HI deferred by owner —
  ROUND 7 Hindi draft exists in chat history, dated-fact pattern, quick-reply only). E2E-proven
  07-31: synthetic FAILED row → sweep → gatekeeper → template DELIVERED to the test number.
  All 6 Zoho console functions pasted CURRENT as of 08-01 07:39 (sweep with params-array +
  record_date + by-mobile resolution; gatekeepers ×3 + office-visitor senders ×2 with the
  subString crash-guard). Sweep runs every 2h (Zoho schedule min); REST-triggerable via
  `ZOHO_FN_ZAPIKEY_WA_UTILITY_FALLBACK_SWEEP` in `D:\Abhay\GLOBAL.env` (synced to Windows VPS).
- **Nightly digest: FIXED (T-037)** — was dying at django-q's 60s timeout BOTH nights (never
  ran successfully on schedule). Q_CLUSTER now 600/720, deployed byte-exact (431931f),
  live-verified. **VERIFY TONIGHT:** report file
  `/var/www/gorefer/var/reports/wa-engagement/2026-08-01.md` (ssh alias `rfp-vps`) + Telegram
  digest ~21:17 IST. Checker PASS (evidence `GetWorkDone/evidence/2026-08-01-T-037`).
- **Template gates:** every draft goes `whatsapp-zoho-template-review` (project skill,
  Wati-Project) → `meta-utility-template-approval-probability` (global skill, threshold 75,
  calibration 18/18) → owner copy approval → map-first → submit → category READ-BACK. Feed
  every real verdict back into the calibration table
  (`Wati-Project/docs/meta-template-category-research-2026-07-31.md` §5.3).
- **Deluge estate:** skill `gorefer-zoho-deluge-functions` (gorefer `.claude/skills/`) = registry
  + wiring map + 20 dated standards. Console paste is the ONLY deploy path for Deluge (no API);
  batch fixes to respect the owner's time; sources live in `5Wealths/Zoho-Project/deluge/`
  (5wealths repo + Windows-VPS copy synced manually).

## My unfinished promises (do after the KM test)

1. **whatsapp-flow-map skill**: move hub (`claude-best-practices`) → Wati-Project
   `.claude/skills/` (owner approved; owner initially said gorefer, accepted my Wati-Project
   recommendation silently — confirm placement in one line if unsure) **+ add lint rule**:
   flag any Question node whose flow has sibling buttons but no escape branches (same class as
   its dead-button audit).
2. Flip the KM map entry to LIVE (after test).
3. Tomorrow-morning check: tonight's digest fired (see above).

## Parked owner decisions (no urgency, don't nag)

ROUND 7 Hindi fallback template · unify `WATI_TEST_RECIPIENTS` (differs local vs Windows-VPS
GLOBAL.env — deliberate?) · optional Wati token rotation (a checker once echoed it locally) ·
delete/keep `D:\Abhay\.pgtmp-t030` (338MB leftover temp Postgres).

## Process rules this program runs on (hard-won this week)

- Fable session = dispatcher: repo work → `/get-work-done` fleet (size budgets by task shape:
  data-sweep/build+deploy = 70–90 turns); live-ops/MCP + bounded last-miles in-session.
- NEVER report "merged/landed/sent" from a chain echo — read the state (`gh pr view --json
  state`; Wati terminal status; file at destination). Windows `git archive` CRLFs files — deploy
  via `git show | ssh cat`, hash-verify both sides.
- Conversation-map SSOT ordering is mandatory: map FIRST, then Meta/Wati, then map again with
  the verdict. Same for scenarios/flows, not just templates.
- The owner's standing instruction (08-01): **test everything yourself as the contact via
  WhatsApp Web before asking the owner to test anything.**
