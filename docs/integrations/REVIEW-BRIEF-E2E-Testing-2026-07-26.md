# Review brief — live E2E testing work, 2026-07-26

> **For an independent reviewer (fresh session).** Everything below was built or changed in one
> session by Claude Opus 5 against **live production** (`gorefer.in`, Hostinger VPS
> `<PROD-VPS>`). Please review adversarially — §5 lists the claims I am least confident in and
> where I think the weakest decisions are. **Do not take my verdicts on trust; the verification
> commands are in §6.**

---

## 1. What to review — file inventory

| File | Lines | What it is |
|---|---|---|
| `.claude/skills/e2e-whatsapp-communication/SKILL.md` | 331 | The E2E procedure: 15 phases + prerequisite gate + gotchas |
| `.claude/skills/e2e-whatsapp-communication/check-prereqs.sh` | 94 | Prerequisite gate; 3 severities, exit 0/1/2 |
| `docs/integrations/E2E-TEST-QUEUE.md` | 99 | Disk-backed work queue (READY / BLOCKED / DONE) for the loop |
| `docs/integrations/WhatsApp-Template-Coverage-Matrix.md` | 129 | All 46 live templates × owner × scenario + sweep results |
| `Wati-GoRefer/Wati-GoRefer-Templates.md` | 149 | Contract doc; new §6.1 v5 section (CI-gated pairing) |
| `apps/integrations/wati/wati-templates.json` | 382 | Template manifest; statuses corrected, v5 added |
| `apps/referrals/redirect_service.py` | 270 | `_stamp_first_click` added |
| `apps/followups/tasks.py` | 363 | `_maybe_referrer_nudge` now uses the canonical link builder |
| `tests/test_redirect.py` | 160 | +3 tests (first_click_at) |
| `tests/test_followups.py` | 888 | +2 tests, 1 assertion updated (link shape) |
| `CLAUDE.md` | 256 | §6c added (template SSOT rule); §2c/§5/§6 drift corrected |

Commits: `4ab05b8` (first_click_at), `8219e6d` (v5 link fix), `6e5af76` (prereq gate).
Also republished: the SSOT artifact *"PIFS WhatsApp — the conversation, card by card"*
(`https://claude.ai/code/artifact/18a28208-60ae-456d-a534-f745a87acb5d`).

---

## 2. Defects found and fixed (all verified on live prod)

1. **Login OTP silently broken — P0.** Prod config `otp_whatsapp_template` = `gorefer_login_otp`,
   a name that has **never existed at Meta in any status**. Live probe → **HTTP 400**. Because the
   bad value was truthy it bypassed the adapter's correct hardcoded default, so every WhatsApp
   login OTP failed and cascaded silently to the `manual` channel while `ENABLE_OTP_LOGIN` read ON
   and `CURRENT-STATE.md` claimed OTP was delivery-verified. Fixed in the config cascade;
   re-probed `accepted=True`; real OTP delivered.
2. **`Referral.first_click_at` never written.** Declared on the model and rendered in the admin
   list, written by nothing → permanently `None`. Stamped in `_record_event` (the single funnel all
   click paths share) via a conditional `UPDATE`. Deployed; 16 existing rows backfilled from their
   earliest click event.
3. **Referrer nudge used the legacy link form** — `gorefer.in/r/{id}?s=wa` instead of the canonical
   channel-path `gorefer.in/r/wa/{id}` (B1 / Q-M-CHANNELPATH). Root cause: `nudge_link_for()` is
   the single canonical builder and the *prospect* nudge uses it, but `_maybe_referrer_nudge()`
   bypassed it and let the **template body** hardcode the URL shape. `?s=` only exists because a
   WhatsApp **URL button** requires its variable last — irrelevant in a body. Fixed by making
   `{{3}}` the whole link (v5 templates); verified live, delivered body reads `gorefer.in/r/wa/RJ4521`.
4. **Stale template manifest** — two entries said `PENDING` while Meta had them `APPROVED`.

---

## 3. Test coverage achieved

- Full suite **596 passed / 0 failed** in CI-parity env, complete 44-file tree.
- All **8** GoRefer-owned templates swept, **EN + HI**, terminal status read from Wati:
  6 delivered/read, 2 blocked by Meta (recipient-level).
- Live: redirect + share + guardrail 3 + bot suppression; capture loop → Wati template → Zoho lead
  write; real inbound → poll opened 24h window → 7 cadence steps enqueued → 1 fired → **READ**.

**Not covered** (in the queue's READY/BLOCKED): Zoho conversion webhook (**guardrail 2 unverified —
the biggest gap**), M13 login, admin dashboard routes, remaining API, landing page, DPDP, rollups,
cross-tenant, and 24 of 46 templates owned outside this repo.

---

## 4. Two of my own earlier claims that I had to retract

Included because they show the failure mode to watch for in the rest of the work.

1. **"19 pre-existing test failures in the deployed code."** False. All 31 observed failures were
   artifacts of running the suite on the prod host with prod's `.env`: 12 from `Q_ASYNC=true`, 15
   from live flags ON, 4 from real creds being present. CI-parity env → 596/0. I had asserted 19
   "look behavioural in the Zoho ingest path" without a baseline.
2. **"The UTILITY re-cut will fix the quality throttle."** False. My own disproof test (send v4 to
   the number where v3 failed) reproduced the **same** failure. The restriction is **per-recipient**
   (`919999900000`), not copy-related. Meta also kept v4 *and* v5 as MARKETING despite UTILITY
   being requested.

---

## 5. Please attack these — my weakest decisions and least-supported claims

**Architecture / process**
1. **"The published HTML artifact is SSOT for templates"** (`CLAUDE.md` §6c) is an owner directive I
   codified. Is a published web artifact a defensible source of truth for a versioned system, given
   it lives outside git, has no diff/review, and can only be edited by re-publishing? If it is
   wrong, what is the right shape that still satisfies the owner's intent?
2. **Deployment is by file-copy**, not a git-tracked deploy. Prod's `tests/` tree is already stale
   (41 files vs 44 in the repo) — a symptom of exactly this. I deployed two `.py` files this way.
   Assess the drift risk and whether my changes are actually reproducible from git on prod.
3. **I mutated prod config directly** (`ConfigGlobal` rows for `otp_whatsapp_template` and the two
   `followup_referrer_nudge_template_*`) with no migration or audit trail. Is that acceptable in
   this codebase's conventions, and is it recoverable?
4. **v5 may be pure churn.** Meta kept it MARKETING, and the throttle turned out to be
   recipient-level. The link-shape fix is real, but did creating v5 templates achieve anything the
   config change alone would not? Also judge the naming debt: `..._hi_2026_07_26_v4b` exists only
   because Wati's DELETE returns `ok:true` while Meta retains the language content (`2388024`).

**Security**
5. **I created a prod staff account** `e2e-test-admin@gorefer.in` (`is_staff`, not superuser) and
   wrote its **plaintext password into the project `.env`**. `.env` is gitignored (verified), but
   assess: was creating a shared prod credential appropriate, is `is_staff` the right privilege, and
   is plaintext-in-`.env` acceptable versus the ADR that admin bootstrap uses `ADMIN_PASSWORD_HASH`
   and "never a seeded plaintext credential"? This may directly contradict `CLAUDE.md` §4.
6. **I sent real WhatsApp messages to real numbers** and wrote a real Lead
   (`475281000041836002`) plus test identities into production. Owner-approved, but review whether
   the blast radius was minimised and whether cleanup is adequately tracked.

**Correctness**
7. **`_stamp_first_click` keys on `vocab.CLICK`.** In page mode the landing path emits *both* `CLICK`
   and `LANDING_VIEWED`. Is `CLICK` the right trigger for every path, and is the **backfill**
   (earliest `CLICK` event per referral) correct — e.g. for `zoho_import` rows, or where a bot event
   exists?
8. **The conditional `UPDATE` deliberately bypasses `AuditedModel`** (no `version` bump, no
   `updated_by`). I justified it as avoiding a hot-path race and field stomping. Is that consistent
   with how the rest of this codebase treats audited models?
9. **`link_mode="none"` now silently `return`s** from the referrer nudge with no event and no
   counter. Should that be observable rather than silent?
10. **Bot handling.** A bot UA still receives a **302 to Zerodha** (only the record is suppressed),
    yet M11 claims forwarded links render a PIFS OG preview card. If crawlers are redirected,
    WhatsApp would render *Zerodha's* card. I flagged this as unresolved rather than fixing it —
    was that right, and which behaviour is correct?

**The loop design**
11. `docs/integrations/E2E-TEST-QUEUE.md` + `/loop` is my answer to "don't stop until it's fixed".
    Judge: does disk-backed state genuinely survive context loss? Is skipping BLOCKED items instead
    of stalling correct? What failure mode does this design have that I have not anticipated
    (e.g. a loop that marks an item done on weak evidence, or thrashes on a flaky check)?
12. **The prereq gate cannot prove a browser login from disk**, so it relies on an owner-created
    marker file (`/root/.gorefer-e2e/whatsapp-web.ok`). A marker can go stale the moment a session
    expires. Is there a better check?

---

## 6. How to verify independently (do not trust my numbers)

```bash
# 1. Full suite — MUST be run with prod's .env neutralised or you get 31 phantom failures
rsync -a --exclude .venv --exclude .git /var/www/gorefer/ /tmp/gv/ && ln -s /var/www/gorefer/.venv /tmp/gv/.venv
cd /tmp/gv && env Q_ASYNC=false ENABLE_CUSTOMER_LOGIN=false ENABLE_OTP_LOGIN=false \
  ENABLE_ZOHO_WEBHOOK_HMAC=false ENABLE_WATI_SEND=false ENABLE_ZOHO_WRITE=false ENABLE_ZOHO_READ=false \
  WATI_ALLOW_ALL_RECIPIENTS=false WATI_API_ENDPOINT= WATI_API_TOKEN= ZOHO_CLIENT_ID= ZOHO_CLIENT_SECRET= \
  ZOHO_REFRESH_TOKEN= GOOGLE_OAUTH_CLIENT_ID= GOOGLE_OAUTH_CLIENT_SECRET= \
  TEST_DB_NAME=gorefer_test_rev .venv/bin/python -m pytest -q -n 4
# NOTE: sync the REPO, not prod, for a true count — prod's tests/ tree is missing 3 files.

# 2. first_click_at actually populates
ssh -i ~/.ssh/firekaro_v6_vps root@<PROD-VPS> 'cd /var/www/gorefer && sudo -u www-data .venv/bin/python manage.py shell -c "
from apps.referrals.models import Referral
print(Referral.objects.filter(first_click_at__isnull=False).count(), \"of\", Referral.objects.count())"'

# 3. Effective flags — never read .env, it says false while DB overrides are ON
ssh -i ~/.ssh/firekaro_v6_vps root@<PROD-VPS> 'cd /var/www/gorefer && sudo -u www-data .venv/bin/python manage.py shell -c "
from apps.config.integration_flags import resolve_flag
print([(f, resolve_flag(f)) for f in [\"ENABLE_WATI_SEND\",\"ENABLE_ZOHO_WRITE\",\"ENABLE_ZOHO_READ\"]])"'

# 4. Prereq gate
bash .claude/skills/e2e-whatsapp-communication/check-prereqs.sh   # expect exit 2 today

# 5. Contract-doc CI gate
python scripts/check_contract_docs.py
```

---

## 7. Open decisions the owner still owes (not defects)

`/open` destination path (live `signup.zerodha.com/api/lead/?c=ZMPHZC` vs `CLAUDE.md`'s
`signup.zerodha.com/?c=ZMPHZC`) · M11 OG card vs bot 302 · wire-or-delete the 9 approved-but-unwired
templates · cleanup of junk `TALK` / `ZMPHZC` identities created by a since-fixed malformed chatbot
link · Meta's recipient-level quality restriction on `919999900000` (Meta-side recovery, not a code fix).
