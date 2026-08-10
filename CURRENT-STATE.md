# GoRefer — CURRENT STATE (read this FIRST, before COORDINATION archaeology)

> **What this is.** The verified now-state snapshot. `COORDINATION.md` (~3,700 lines) is the
> append-only log of record — this file is the **cache of its conclusion**, so a session never
> has to reconstruct "now" from a tail read (the 2026-07-21 incident: a mis-computed tail
> offset made the Engineer re-stage a go-live that was already live; see the CORRECTION entry).
>
> **Update rule (protocol):** whoever changes state — a flag flip, a deploy, a mission
> start/finish, a template approval — updates this file **in the same turn** as their
> COORDINATION entry. If this file and COORDINATION disagree, the newest COORDINATION entry
> wins; if either disagrees with the live system, **the live system wins** — verify, don't
> trust (commands at the bottom).
>
> **Last updated:** 2026-08-10 20:00 IST (**DEPLOYED: `d238789` = main tip** — **T-081 OTP email
> FROM-address self-serve LIVE**: the OTP email "from" is now an owner-editable cascade key
> `otp_email_from_address` (default `""` → falls back to `DEFAULT_FROM_EMAIL`, byte-identical to
> T-078); SMTP host/user/**password** stay env-only (checker's first ruling: secret-safety PASS —
> no secret leaks via Preferences; a bad from-address is rejected at save AND defended again at
> send so it can't break OTP email). 6-file file-copy deploy, sha256 byte-exact; `seed_program`
> run (key resolves `''` live); both services active; home+`/d/pifs` 200. Checker PASS 1183 tests,
> evidence `GetWorkDone/evidence/2026-08-10-T-081/`. **This header + the Deployed-SHA row had
> drifted three deploys behind — the T-075 login-gated-hub (`a569383`) and T-078 email-OTP
> (`fff1cf7`) PRs deployed without updating this header; corrected here.** Email OTP end-to-end
> stays owner-gated: `ENABLE_EMAIL_OTP` off in prod until the Gmail SMTP app-password is supplied
> (TODO-Manual `gorefer-email-otp-smtp-cred`) — until then the email leg is a clean no-op, WhatsApp
> OTP unchanged. **Invite template** `gr_brokers_zerodha_referandearn_invite_en_2026_08_10`
> submitted to Meta — PENDING, MARKETING/EN, token dropped; approval watcher armed.)
> — prior 2026-08-10 19:20 IST (**DEPLOYED: `fff1cf7`** — **T-078 email OTP as a second,
> simultaneous login channel** (fan-out: WhatsApp send unchanged + email leg, same code, on-file
> email only); `ENABLE_EMAIL_OTP` default off, owner-gated on Gmail SMTP creds. Opus security
> checker PASS 1170 tests.)
> — prior 2026-08-10 17:15 IST (**DEPLOYED: `a569383`** — **T-075 login-gated share hub at a
> token-free `/hub`** (Phase 1 of the token→login retirement): unauth → `/login?next=/hub`, authed
> → the same hub sourced from the session identity; the T-064 opener edit re-homed to session auth;
> `/hub/{token}` kept alive during transition. Opus checker PASS, cross-identity leak blocked,
> 1149 tests.)
> — prior 2026-08-10 12:35 IST (**DEPLOYED: `c89c8cd` = main tip** — **T-073 fail-closed
> computed-variable send guard LIVE**: GoRefer now refuses to send ANY WhatsApp template whose
> server-computed vars (e.g. {{token}}) are missing/blank, enforced at the messaging-port factory
> before any network call — the root-cause fix for the "template with a token but no sender ships
> blank/broken links silently" gap. Plus a fail-closed vendor-approval check + a per-recipient
> invite sender (send_invite_links, dry-run default). Live-proven: the DRAFT invite is REFUSED by
> --send. Opus checker PASS (24 probes, 1117 tests). Two non-blocking findings (invite gate should
> be ENABLE_SHARE_HUB; wati/tasks.py raw-adapter path) being closed by T-074 in flight. NO blast
> fired — invite send still gated on owner trigger + Zerodha sign-off + Meta approval.)
> — prior 2026-08-10 05:00 IST (**DEPLOYED: `758f64a` = main tip** — the overnight
> CUSTOMIZATION BLOCK is complete and live: **T-062** share-message self-serve (Preferences
> editors EN/HI) + language stickiness (stored-language resolution on /share and /hub),
> **T-063** hub share images (config slots, native-share-with-files, download buttons — dormant
> until image URLs configured), **T-064** referrer-personalized share opener (token-authed,
> compliance tail + credit link locked server-side, migration accounts.0003). All three
> checker-PASSed (T-064 by an opus checker with 67 adversarial probes + mutation testing),
> deployed byte-exact, live-probed. Fleet queue EMPTY (T-057…T-064 done). Details + findings in
> the COORDINATION 2026-08-10 dispatcher entry.)
> — prior 2026-08-09 21:15 IST (**DEPLOYED: `6db2e46` = main tip** — **T-061 Hindi
> hub/records LIVE (?lang=hi, 34 cascade _hi keys, EN fallback, compliance line verbatim EN)
> — and with it the TIER-A TRAIN IS COMPLETE: T-057…T-061 all deployed, checker-verified, and
> live-probed.** Owner actions open: (1) set `referrer_conversion_congrats_template_en` to an
> approved template name to arm the congrats template leg; (2) TODO-Manual card: broader Zoho
> self-client token (MFA once). Known partner-#2 gaps, all parked with triggers: OG preview-card
> copy, DF-5/9/10. Full train record in COORDINATION 2026-08-09 entries.)
> — prior 2026-08-09 18:00 IST (**DEPLOYED: `b623343` = main tip** — **T-060 LIVE**:
> self-click tag on the Referral Profile Clicks tab (display-only, CRM-read-gated, never a
> guess; DF-11 count-exclusion half stays deferred), deterministic order_by on duplicate
> client_id lookups (T-054 finding 1), `hub_cta` now a cascade key (finding 2), T-056 vacuous
> assertion repaired. Checker PASS incl. rollup-level display-only proof. T-061 (Hindi parity
> on hub/records, web-only) dispatched — the LAST task of the ratified Tier-A train.)
> — prior 2026-08-09 16:35 IST (**DEPLOYED: `15f9b94` = main tip** — **T-059
> program-scoped message copy LIVE**: every outbound message surface (share kit, hub message,
> selfview share text, followup nudge copy) now renders `{program_brand}` via the T-056
> fallback chain — byte-identical output for Zerodha today (checker-proven against the parent
> commit), a second program is copy-ready with zero code change. Remaining partner-#2 gap:
> OG preview-card title/description still hard-name Zerodha (page metadata, disclosed, parked).
> T-060 (self-click tag + hygiene) dispatched with the new headless-worker CI rule.)
> — prior 2026-08-09 15:45 IST (**DEPLOYED: `a641f07` = main tip** — **T-058
> conversion-congrats nudge LIVE (dormant template leg)**, PR #129, checker PASS with deep
> adversarial probes (evidence `GetWorkDone/evidence/2026-08-09-T-058/`). On the next REAL Zoho
> conversion the credited referrer gets a session congrats if their 24h window is open;
> otherwise the template leg is DORMANT until `referrer_conversion_congrats_template_en` is
> set to an approved template name (owner action, template lane). New standing deploy rule:
> **cascade-key deploys end with `manage.py seed_program`** — keys resolved unregistered until
> it ran. T-057's live send TERMINAL: Notification 25 = **delivered**. T-059 (program-scoped
> copy) dispatched.)
> — prior 2026-08-09 14:55 IST (**DEPLOYED to prod: `4968677` = main tip** — **T-057
> `send_records_links` operator command LIVE**, PR #127, sonnet worker + independent sonnet
> checker PASS (evidence `GetWorkDone/evidence/2026-08-09-T-057/`). The magic-link surfaces
> finally have a sender: `manage.py send_records_links --client-ids ... [--send]` (dry-run
> default) mints tokens internally, resolves mobiles via the CRM read port, and sends the
> APPROVED UTILITY template `gr_platform_gorefer_refrecord_en_2026_08_07` (params
> name/record_date/token, button → `/rr/{token}`) through the messaging port with cap/dedupe/
> opt-out/flag gates. New cascade keys: `records_link_template_en`,
> `records_link_send_max_per_run` (50), `records_link_send_min_gap_days` (7). Deploy: 9-file
> git-show pipe, hash-verified byte-exact; no migrations/static; both services restarted+active;
> public home+health 200. **Live fire:** dry-run for DA1707 correct (masked mobile, record_date
> 09 Jul 2026), then ONE real `--send` → Notification id=25 `accepted`; terminal delivery status
> poll armed (accepted ≠ delivered — will be recorded when the reconcile flips it).
> **Google OAuth (P-07) VERIFIED LIVE END-TO-END 2026-08-09 ~14:30 IST** — signed-out `/login/`
> → Continue with Google → account chooser → callback → real session on `/my/referrals`
> (DA1707, Zoho-enriched profile, T-054 'Share your link' entry rendering). The primary login
> door is no longer untested; the flag-table note below is superseded by this entry.
> **Checker findings logged:** (1) the T-057 COORDINATION entry claims "948 tests" — actual
> suite count at 4968677 is **934** (worker doc error, code fine); (2) DESIGN CALL for owner/DA:
> the records-link token is persisted plaintext in `Notification.template_params` (an erasable
> operational row, matching the pre-existing notify pattern — but a bearer token is more
> sensitive than name/email; decide whether to redact it there).
> **Owner-scope note (2026-08-09):** Tier-A train T-057→T-061 ratified; T-058 (conversion
> congrats) dispatches after T-057's terminal-delivery confirmation.)
> — prior 2026-08-09 02:45 IST (**DEPLOYED to prod: `e4fbeeb` = main tip** — PR #124
> hub compliance-reviewed share copy + real generated link-preview card. Verified live over SSH
> (`DEPLOYED_SHA` read from the box; `gorefer` + `gorefer-qcluster` both active). The 2026-08-08
> evening deploy had not been recorded here — drift caught and fixed by the 2026-08-09 session.
> **SSH note:** use the alias `ssh rfp-vps` (config in `~/.ssh/config`, key `rfp_vps_deploy`);
> bare `ssh root@72.61.240.224` is refused — publickey only, and the key is bound to the alias.)
> — prior 2026-08-08 13:05 IST (**DEPLOYED to prod: `14eb2f7`** — two
> same-day follow-ups to the magic-link go-live, both opus/sonnet-built + separately checked,
> both byte-exact deployed and live-sanity verified:
> **T-055** (PR #120, `214c900`) share-hub **partner header + share hierarchy** — owner reviewed
> the live page and found (a) the partner was named NOWHERE, (b) six equal-weight buttons pushed
> nothing. Now: brand line at the top, then the referrer's own link, ONE large "Share on WhatsApp"
> primary CTA, "Copy link" second, the other five demoted to a compact row, benefits, disclosures —
> DOM order locked by a test. Attribution wording = new cascade key `share_hub_partner_attribution`.
> No partner logo (ADR-014: never resemble/clone the partner; no trademark permission).
> **T-056** (PR #121, `14eb2f7`) — **live defect found by post-deploy sanity, not by tests**:
> T-055 bound the header to `ReferralIdentity.partner.name`, but PROD semantics are
> `Partner` = *PIFS itself* ('Passive Income Financial Solutions Pvt Ltd', the AP) while the broker
> brand lives on `ReferralProgram.display_name` ('Zerodha'). The live page therefore read
> "Passive Income Financial Solutions Pvt Ltd … via PIFS" — PIFS via PIFS. Every T-055 test and its
> checker passed because both **invented their own seed shape**. Fixed: brand resolves
> `program.display_name` -> `program.name` -> `partner.name` -> no brand element (never a blank
> chip), and the new tests seed the **production shape** so this class cannot pass again. The T-056
> checker independently rebuilt that prod shape and read the header back verbatim: renders
> **"Zerodha"**, no company name in the header; a second program ("Groww") renders only its own
> brand — multi-partner readiness is now demonstrated, not asserted.
> **Post-deploy sanity (14eb2f7, all green):** header shows Zerodha; token appears exactly once per
> page (the sibling cross-link) and ZERO times in any share href; all share buttons carry
> `gorefer.in/r/wa/{client_id}`; guardrail-3 clean; `/hub/` + `/rr/` 200 over public HTTPS; home 200;
> services active. The one remaining "Passive Income Financial Solutions" string in the body is the
> **mandatory SEBI/NSE disclosure block** (SEBI reg. INZ000031633, NSE AP AP2516003693) — required,
> not a leak.
> **Known, deliberately not fixed today:** (1) the WhatsApp share *message text* is tenant-scoped,
> not partner-scoped, and still says "Open a free Zerodha account" for any partner — harmless while
> Zerodha is the only program, MUST be fixed before a second broker onboards (found by the T-055
> checker); (2) `test_empty_brand_name_renders_no_blank_element_in_the_header` contains one vacuous
> assertion (checks a string absent from the template either way) — other assertions in the same
> test do the real work; clean up in the next PR; (3) hub COPY is still an engineering placeholder
> and the OG image reuses `static/img/og-card.png` — both owner-review gates before any real
> customer traffic; all copy is cascade config, so changing it needs no deploy.)
> — prior 2026-08-08 02:20 IST (**DEPLOYED: `e217489`** — the
> magic-link surface go-live: T-051 `/rr/{token}` masked read-only records page + signed
> revocable tokens, T-052 fail-closed token verification, T-053 `/hub/{token}` share hub
> (benefits + own link + WA/TG/FB/X/LinkedIn/copy/native-share, all spreading the CREDIT link
> `/r/wa/{client_id}`, never the token), T-054 `POST /api/records-tokens/mint` (header
> `X-Records-Mint-Key`, env-only, fail-closed) + the logged-in "Share your link" entry on
> `/my/referrals`. Each mission opus-built and verified by a separate opus checker
> (evidence `GetWorkDone/evidence/2026-08-0{7,8}-T-05{1,2,3,4}/`). Deploy: full-tree rsync of
> the 32-file delta from `3db7c59`, tarball built with `core.autocrlf=false`, destination files
> hash-verified byte-exact vs git blobs; migration `accounts.0002_recordslinkstate` applied;
> collectstatic 9 files; both services restarted+active. **FLAGS ON in prod:**
> `ENABLE_RECORDS_LINK=true`, `ENABLE_SHARE_HUB=true` (+ `RECORDS_TOKEN_MINT_KEY` generated on
> the box, `.env` backed up to `.env.bak-sharehub-*`). This deploy also carried the previously
> merged-but-undeployed **T-049 tenant-scoping refactor** (89 call-sites) — regression-probed
> below. **Post-deploy live sanity (all green):** `/` 200, `/open` 302, `/r/EKU497` 302,
> `/d/pifs` 200, `/api/health` 200, `/admin-panel/` + `/my/referrals` 302-to-login;
> bogus token on `/rr/` and `/hub/` → 404 (no oracle); mint API 401 without key and with a wrong
> key, 200 with the real key returning `{token, rr_url, hub_url, name, record_date}` for a known
> id and `unknown_client_id` for an unknown one; **real minted token → `/rr/` 200 and `/hub/` 200
> over public HTTPS**; token appears exactly ONCE per page — the cross-link to the sibling page —
> and ZERO times inside any share href (Facebook `u=` and LinkedIn `url=` both carry
> `gorefer.in/r/wa/{client_id}`); guardrail-3 clean on both pages (no `ZMPHZC`, no
> signup.zerodha.com); **masking proven live on DA1707** — renders `Ab••••a` / `91••••••53`
> while the raw name and raw mobile appear 0 times. **NOT yet customer-facing:** hub copy is an
> engineering placeholder pending owner compliance review (all copy is cascade config — no
> deploy needed to change it), the OG share image reuses `static/img/og-card.png`, and no
> template send is wired to the mint API yet.) — prior 2026-08-06 18:10 IST (**DEPLOYED: `7eb1c82`** — T-047
> CSRF + real session auth on staff Ninja routers (PR #107, opus worker + adversarial opus
> checker PASS incl. mutation test): `StaffSessionAuth(SessionAuth)` on followups/analytics
> routers — forged staff POSTs now 403; webhooks/public routes untouched (live probe:
> followups anon POST 403, zoho webhook bad-key 401 = key layer, not CSRF). 3 files piped
> blob-hash-verified, services active. Closes the last live security gap from the 2026-08-06
> review.) — prior 2026-08-06 16:30 IST (**DEPLOYED: `8f71be6`** — T-046
> dashboard N+1 fix (PR #104): explorer/leaderboard rewritten to queryset annotations +
> pagination (new cascade key `dashboard_explorer_page_size`, default 100), `_referrer_name`
> consolidated to one shared helper; deployed via git-show pipe (5 files, blob-hash-verified),
> services active, health/home probes green, admin-panel 302-to-login as expected. Also
> carries the `pytest-django<4.13` pin (4.13.0 broke django_db fixture setup on every PR).
> **P0-A CLOSED the same afternoon** — Contacts workflow rule + signer live and verified
> end-to-end incl. a latent Deluge TZ bug found by the live fire and fixed in-console (full
> story in the Zoho-ingest section below). **Wati webhook token ROTATED** on the VPS (old key
> in `.env.bak-tokenrotate-20260806`); the Wati-dashboard URL paste is an owner TODO-Manual
> card — until pasted, Wati webhook POSTs 401 and self-heal via the pending-delivery
> reconcile, no data loss.) — prior 2026-08-01 07:00 IST (**DEPLOYED: `431931f`** — T-037
> Q_CLUSTER timeout 60→600 (retry 720): the nightly 21:00 IST engagement digest had NEVER
> survived its schedule — django-q killed the multi-minute Wati pull at 60s on BOTH 07-30 and
> 07-31 (Failure rows are the evidence; only manual runs ever completed). Also carries PR #85
> (rollups IST-date dirty-marking, apps/events/signals.py). Both files deployed byte-exact via
> git-show pipe (the Windows git-archive CRLF trap fired again — hash-verified after redo),
> services restarted+active, live-verified timeout=600. First scheduled digest expected tonight
> 21:xx IST. Fallback engine (T-032..036 chain): LIVE EN lane, E2E-proven 07-31 (test template
> DELIVERED to the allowlisted number); Zoho console still runs the map-params sweep version —
> owner paste batch pending (sweep params-array + gatekeeper/sender subString guards).) — prior 2026-07-30 14:00 IST (**DEPLOYED to prod: `d342831` = main tip** — the
> T-032/T-033/T-034 daily WA-engagement-report chain LIVE and verified with REAL numbers:
> PR #75 (feature: `wa_engagement_report` command + `apps/integrations/wati/engagement.py` +
> `wa_engagement_report_daily` schedule, hourly poll gated on `wa_engagement_report_hour_ist`,
> default 21 IST) + PR #76 (fix: v3 bare-host base, degraded-on-non-200, command moved to the
> installed-app location `apps/integrations/management/commands/`) + PR #77 (fix: parser reads
> the REAL Wati payload keys — `messageTemplates`, `broadcasts`, nested `statistics`,
> `recipients`; ground truth = T-031 captured payloads). Config cascade for PIFS:
> `wa_engagement_report_enabled=True`, hour 21 IST, lookback 7d, reports at
> `/var/www/gorefer/var/reports/wa-engagement/` (www-data-owned). Owner digest goes via the
> shared **Notifier gateway** (localhost:3300, `projects.gorefer` → Telegram ops chat;
> NOTIFIER_URL/KEY in prod .env). Supervised prod run 2026-07-30 13:57 IST: degraded=false,
> trailing-7d sends **1,930** (MARKETING 1,873 / UTILITY 51 / AUTH 6), failure codes
> 131049=382 · 131026=234 · 130472=27, responders 20 (17 quick-reply taps), windows 4,
> share_intent 19 / clicks 34 — consistent with the T-031 verified baseline (2,047 sends on
> the ~1-day-earlier window; report `reports/wa-engagement/2026-07-30.md`, PR #74). Digest
> POST 202 accepted, dedupeKey `wa-engagement-2026-07-30`. **CORRECTION:** the T-034
> COORDINATION entry's closing claim ("Deployed + a supervised prod run verified…") was
> written by the worker BEFORE the deploy happened (it ran out of budget); the deploy + run
> above were executed and verified by the dispatcher at 13:54–13:57 IST — the claim is true
> only as of then. Fleet records: GetWorkDone T-031…T-034, evidence
> `GetWorkDone/evidence/2026-07-30-T-031/` + `…-T-032-034/`.) — prior 2026-07-28 19:15 IST (**DEPLOYED to prod: `31fc244` = main tip** — share-kit preview fix LIVE (verified: /share/wa/ redirect now emits https://gorefer.in/r/wa/{id} BEFORE the disclosures link) + Phase-0 rails (a23a58e, zero-behavior-change; seed_program run — locked rows exist) + docs. Services restarted, both active. NOTE: pre-deploy DEPLOYED_SHA read `2accaa1` (Jul-27 deploy), NOT this table's stale `1be4c34` — table now corrected) — earlier same day (share-kit preview fix PR #67 squash-merged to main `118ddfd` — https:// scheme on the kit referral link + preview-order test, so WhatsApp previews the referral landing not the Disclosures page; **NOT deployed — prod stays `1be4c34`**, main is ahead of prod) — prior 2026-07-25 (recipient-identity resolver LIVE, `c050d19` — PR #42; prospect
> nudges now carry the credit-preserving referral link `gorefer.in/r/wa/{referrer_client_id}` (or
> `/open` fallback), referrer recipients suppressed from the prospect copy, language from the
> existing `referrer_language` rule; re-seeded 7 rules with the `{link}` CTA; resolve-on-send, no
> migration; verified live. Referrer-nudge §6.1 slice pending Meta approval of
> `gorefer_referrer_prospect_pending_{en,hi}_..._v2`.) — earlier same day M-FUP-1 auto-trigger LIVE via polling `f0fa385` — scheduled
> `followup_inbound_poll` opens windows + enqueues cadences autonomously, verified on 917767009136)
> — earlier 2026-07-24 (main CI RESTORED GREEN, `347947a` — PR #33, test-only fix for a
> quiet-hours wall-clock flake in `tests/test_followups.py`; no production code changed, nothing
> redeployed) — same day M-FUP-1 follow-up engine deployed + LIVE on prod, `bbc32c8`,
> `followups_enabled=True`, live session nudge DELIVERED+READ; earlier same day M-WATI-1 `/share`
> LIVE (`f7f8656`). Flag values below carry the 2026-07-21 verification date.

## Production

| Fact | Value |
|---|---|
| Deployed SHA | **`d238789`** (2026-08-10 20:00 IST — T-081 OTP email FROM-address self-serve; see header). Prior **`fff1cf7`** (2026-08-10 19:20 IST — T-078 email OTP second channel). Prior **`a569383`** (2026-08-10 17:15 IST — T-075 login-gated `/hub`). Prior **`c89c8cd`** (2026-08-10 12:35 IST — T-073 fail-closed send guard). **[These four deploys post-date the `4968677` entry below, which had been the stale lead of this row.]** Prior **`4968677`** (2026-08-09 14:55 IST — T-057 send_records_links live; see header). Prior **`e4fbeeb`** (2026-08-08 evening, verified over SSH 2026-08-09 02:45 IST — PR #124 hub copy + generated preview card). Prior **`14eb2f7`** (2026-08-08 13:05 IST — T-056 hub header shows the broker/program brand; see header). Prior **`214c900`** (12:0x IST — T-055 header + share hierarchy). Prior **`e217489`** (2026-08-08 02:12 IST — magic-link go-live: T-051/052/053/054, flags ENABLE_RECORDS_LINK + ENABLE_SHARE_HUB ON, mint key set; see header for the full sanity list). Prior **`3db7c59`** (T-050 docs; the row below read `f4f079f`, which was stale — prod DEPLOYED_SHA read `3db7c59` at 2026-08-08 01:5x). Prior **`f4f079f`** (2026-08-04 ~14:40 IST — doc-17 boundary-hardening train W1+W2+W3, see header. Full-tree rsync deploy, hash-verified). Prior **`f9f0144`**/**`ca6a3d6`** (2026-07-30 ~09:15 IST — T-030 admin-login redirect-loop fix, PR #72: `DashboardLoginView` now redirects only authenticated STAFF; a non-staff referrer session gets a 200 login page with a sign-out notice (was: infinite loop with `_staff_required` → ERR_TOO_MANY_REDIRECTS). File-copy deploy of the 6-file delta 31fc244..ca6a3d6 (no migrations/deps/static; app.css unchanged), byte-exact hash-verified vs git blobs (first copy had CRLF from Windows `git archive` — redone via `git show` pipe), both services restarted+active. Verified live at destination: anonymous login 200; the owner's real referrer session renders the notice page at /admin-panel/login/ (no loop) and /my/referrals still works. Suite 706/0 + checker re-derivation, evidence GWD/evidence/2026-07-30-T-030). Prior **`31fc244`** (2026-07-28 ~19:12 IST — main tip: share-kit https fix `118ddfd` + Phase-0 rails `a23a58e` + docs; migrate=no-op, seed_program run, collectstatic, both services active; share-endpoint effect verified live). Prior **`2accaa1`** (2026-07-27; the table briefly said 1be4c34 — stale). Prior detail: **`1be4c34`** (deployed 2026-07-26 ~22:35 IST — D8 close-out: `b2bac2c` OTP delivery-race tests + `1be4c34` guardrail-3 fix (partner code `ZMPHZC` was rendering on the client-facing `/my/referrals` self view — found live during D8; stripped at DATA level in `selfview.py`, admin view unchanged). Suite **634/0** in the CI-parity env. NOTE: the prior `DEPLOYED_SHA` file read `324a1b8` while prod CONTENT already matched `main` (`dfda4bc`) on every file except `apps/otp/adapters.py` — the marker was stale, not the deploy; verified by hashing, not by trusting the file. Prior: `324a1b8` (PR #52 merged + deployed 2026-07-26 ~14:35 IST — E2E-session fixes: `4ab05b8` `first_click_at` stamping (16 rows backfilled), `8219e6d` §6.1 nudge link → canonical `/r/wa/{id}` via `nudge_link_for()` with **v5 templates** (`gorefer_referrer_prospect_pending_{en,hi}_2026_07_26_v5`, APPROVED; Meta kept MARKETING), `55f1886` review reconciliation (observable `link_mode=none` skip + drift fixes). Config rows changed same day (ConfigGlobal, tenant 1): `otp_whatsapp_template` → `gr_platform_gorefer_login_otp_en_2026_07_21` (**P0 fix** — old value `gorefer_login_otp` never existed at Meta), `followup_referrer_nudge_template_{en,hi}` → v5. `tests/` tree synced to repo (48 files). Verify-live: files hash-match `main`; suite 596/0 in CI-parity env. Prior: `7870052` (§6.1 nudge LIVE+ACTIVATED — PRs #46+#47; `followup_referrer_nudge_on=True` (tenant pifs), step `nudge_12h`. Nudges an idle prospect's referrer — only when the referrer's phone is a known `Customer`; capped one/step; name→generic descriptor. Prior `c050d19` (recipient-identity resolver + referral link in prospect nudges, PR #42, LIVE — `/r/wa/{referrer}` or `/open`), `6e3072d`/`bbc32c8` (M-FUP-1), `f7f8656` (M-WATI-1 `/share`) |
| Host | Hostinger VPS `72.61.240.224`, Cloudflare-proxied, gunicorn + qcluster (`Q_ASYNC=true`) |
| DB | `gorefer_prod` (Postgres) — migration `accounts.0001` applied |

## Integration flags — LIVE VALUES (cascade-resolved, verified 2026-07-21)

| Flag | State | Since / note |
|---|---|---|
| `ENABLE_WATI_SEND` | **ON** | Settings override ~17-Jul. `WATI_ALLOW_ALL_RECIPIENTS="true"` — allowlist OPEN, real sends to real recipients daily |
| `ENABLE_ZOHO_WRITE` | **ON** | Settings override ~17-Jul (DF-9 effectively closed then) |
| `ENABLE_ZOHO_READ` | **ON** | Settings override ~17-Jul |
| `ENABLE_ZOHO_WEBHOOK_HMAC` | **ON** | 18-Jul; Deluge signer pasted + workflow rule active in Zoho; seal proven end-to-end |
| `ENABLE_CUSTOMER_LOGIN` | **ON** | 21-Jul (M13 go-live, owner "go"): prod `.env` true. `/login/` live (Google OAuth primary + OTP fallback), `/my/referrals` live, admin Verifications queue live |
| `ENABLE_OTP_LOGIN` | **ON** | 21-Jul: AUTH template `gr_platform_gorefer_login_otp_en_2026_07_21` APPROVED + delivery-verified. **26-Jul P0 found+fixed:** prod config `otp_whatsapp_template` had been set to `gorefer_login_otp` — a name that NEVER existed at Meta — so every WhatsApp OTP got HTTP 400 and silently degraded to the `manual` channel while this flag read ON. Config corrected to the real template; re-probed `accepted=True`, real OTP delivered. Lesson codified in CLAUDE.md §6c. **26-Jul SECOND, INDEPENDENT break found+fixed (D8):** `WatiWhatsAppOtpAdapter.send()` demanded a TERMINAL delivery status microseconds after sending, so the WhatsApp channel ALWAYS reported failure and ALWAYS cascaded to `manual` — `OtpChallenge` id=1, the first ever recorded on prod, had already fallen back. Non-terminal now returns `QUEUED` (accepted, unproven, stops the cascade). **VERIFIED LIVE END TO END 2026-07-26 22:18-22:25 IST** with the owner reading the code: challenge id=2 `channel=whatsapp_wati` / `delivery_status=delivered`, message READ at the Wati destination, verify → 302 `/my/referrals` + session, replay → 400 (single-use), `/my/logout` clears it, referrer session refused both admin surfaces. **Google OAuth — the PRIMARY login — remains UNTESTED** (owner deferred it in D8) |

The prod `.env` lines say `false` for the three integration flags — those are **overridden
defaults**; the truth is the ConfigGlobal override read through `resolve_flag()`. Never read
`.env` alone for flag state.

## Zoho ingest — P0-A CLOSED 2026-08-06: the real push pipe is LIVE and verified

**A Contacts-module workflow rule now pushes conversions to GoRefer within seconds.** Rule
**"GoRefer account opened Contacts"** (id `475281000042172012`, ACTIVE, execute on Contacts
Create-or-Edit with repeat-on-edit, condition `Account_Opened_On is not empty`) fires the
Deluge function **`gorefer_webhook_signer_contacts`** (argument `contactId` ←
`Contacts.Contact Id`), which HMAC-seals and POSTs to `/api/zoho/status-webhook`. Installed
via browser session 2026-08-06 (the runbook `Zoho-GoRefer/P0A-Contacts-Trigger-Steps.md`,
executed by the Engineer, not owner-manual; note Zoho CRM **v8 now has a workflow-rules API**
— our OAuth token lacks the `settings.workflow_rules` scope, minting a broader self-client
token is the durable automation fix and needs owner MFA once).

**Live-fire test found and fixed a latent TZ bug:** the first real firing (16:04 IST edit of
contact KTP804) was **rejected — "stale or future timestamp (skew 19800s)"**. The Deluge
signer formatted IST wall-clock and parsed it as GMT (+5h30m). The 18-Jul "seal proven
end-to-end" was **curl-only** — no Deluge sender had ever actually fired (the Leads rule
never triggers), so the bug sat invisible in BOTH signer functions. Fixed in-console
(`toString("dd-MMM-yyyy HH:mm:ss","GMT")`) and synced to the canonical `.dg` files in
`5Wealths\Zoho-Project\deluge\` (both signers).

**Post-fix verification (2026-08-06 16:04 IST):** rule fired → **HTTP 200**, conversion
**applied** — `KTP804`, true opening date **2022-10-02** honoured (ADR-017), referrer
`VPP326` credited exactly as Zoho holds it; the duplicate rule-firing was refused as a
**nonce replay (401)**; DB shows **exactly 1** conversion row. Notably this 2022 opening is
one the reconciler could never have recovered (watermark never reaches it) — the push pipe
is already ingesting data the patch couldn't.

**Reconciler stays on as the safety net:** `zoho_reconcile_conversions` (P0-B, `4919036`),
~15-min sweep. Old Leads rule/function remain inactive-harmless. Zoho Variable
`gorefer_webhook_secret` exists and matches prod.

## Daily report (O-6a / R-DRR)

Three-sided (Zoho supposed-to-send ⋈ Wati delivered ⋈ GoRefer funnel), scheduled 21:30 IST
(`Wati-DailyDeliveryReport` task; engine `5Wealths\Wati-Project\daily_report.py`).
`GOREFER_ZOHO_INGEST_LIVE=true` — accounts-opened line shows real numbers. WhatsApp summary
template: v3 `gr_platform_gorefer_funnel_report_en_2026_07_21` **APPROVED at Meta**
(verified against the live inventory 2026-07-26; the earlier "PENDING" here was stale).

## In flight

- **M13 is DONE and LIVE** (2026-07-21): PR #20 merged + deployed; Google OAuth creds in prod
  `.env` (owner-created); OTP AUTH template approved + delivery-verified; both login flags ON.
  Contract: `docs/sprint2/S2-05-M13-Referrer-Login-Goal-Contract.md`. Q-M-OTP-2 CLOSED.
  (Correction to an earlier line here: PR #12/Q-M-OTP was in fact MERGED 2026-07-16 — the
  "held" note was stale; M13 built on it.)
- Known messaging problem: delivery rate ~42% (131049 per-user cap dominated) — the daily
  report is the instrument on it.
- **M-FUP-1 (24h-window follow-up engine, Phase 1) — LIVE on prod** (2026-07-24, owner-authorized
  Sprint-2 mission + prod deploy; CLAUDE.md §6 deferral lifted). PR #30 merged (`bbc32c8`), deployed
  to `/var/www/gorefer` (DEPLOYED_SHA `bbc32c8`, backup `predeploy-fup-20260724-223741.tgz`), migration
  `followups.0001` applied, `followup_sweep` registered (every 5 min → `fire_due_followups`), cadence
  seeded (**every 3h through 24h**: nudge_3h…nudge_21h), **`followups_enabled=True` for PIFS**, both
  services restarted. **Live end-to-end proof:** owner messaged the WATI business number → window
  opened → `record_inbound` enqueued the 7-step cadence → the sweep sent a session nudge →
  **DELIVERED + READ** (terminal-verified) on 917972672473. Quiet hours 23:00–06:00 IST enforced
  (night steps auto-defer to 06:00 IST). Session endpoint CONFIRMED (`/api/v1/sendSessionMessage`).
  Tenant-scoped only (doc-13 §5, NO PartnerGroup).
  **AUTO-TRIGGER now LIVE via POLLING** (2026-07-25, `f0fa385`): the Wati inbound webhook is
  chatbot-suppressed ("New Contact Message" doesn't fire when the Welcome flow auto-replies; no
  "Message Received" event exists), so windows are opened by `followup_inbound_poll` (every 5 min →
  `poll_inbound_windows`): it reads `getMessages` for a per-AP watch-list (`followup_poll_watch_mobiles`,
  set to the test numbers) + recent Prospect mobiles, and on a new inbound calls `record_inbound` →
  window opens + cadence enqueues. **Verified autonomous:** the scheduled poll opened 917767009136's
  window (from its "Hi") and enqueued the 7-step cadence with ZERO manual action; idempotent on re-run.
  The `?token=`-authed `/api/wati/inbound` webhook stays wired (harmless bonus). Full loop live:
  prospect messages business → poll (≤5 min) → window → 3h cadence → sweep sends (session, quiet-hours).
  **Burst+copy fix LIVE (`6e3072d`, 2026-07-25):** anti-burst min-gap (default 90 min via `compute_defer`, satisfies quiet-hours AND spacing) + DISTINCT per-step copy (seed_followup_cadence STEP_BODIES) — fixes the owner-caught 06:03 duplicate burst + identical messages; applies to pending sends too (copy read at fire time).
- **M-WATI-1 (one-tap `/share/{channel}/{client_id}` endpoint) is LIVE** (2026-07-24, owner "make it
  live now"): PR #28 merged (`f7f8656`); the 6 code files deployed to prod (file-copy, backup
  `.predeploy-backup-20260724-150205`), `ENABLE_SHARE_INTENT=true` in prod `.env`, both services
  restarted. Live-verified at destination: `GET /share/wa/DA1707` → **302 → wa.me** (pre-filled
  referral message), homepage 200, unsupported channel `/share/xx/` → 404 (spec-correct). No
  migrations/deps/static in this deploy. Rollback = set flag false + restart (route unregisters).

## Verify-live commands (truth beats this file)

```bash
ssh root@72.61.240.224 "cat /var/www/gorefer/DEPLOYED_SHA"
ssh root@72.61.240.224 "cd /var/www/gorefer && sudo -u www-data .venv/bin/python manage.py shell -c \"
from apps.config.integration_flags import resolve_flag
print([(f, resolve_flag(f)) for f in ['ENABLE_WATI_SEND','ENABLE_ZOHO_WRITE','ENABLE_ZOHO_READ']])\""
# COORDINATION tail — by CONTENT, never by a computed offset (blank-line counts lie):
tail -n 80 COORDINATION.md   # confirm the last entry's date before trusting any state claim
```
