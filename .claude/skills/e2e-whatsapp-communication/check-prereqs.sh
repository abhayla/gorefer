#!/usr/bin/env bash
# Prerequisite gate for the GoRefer live E2E run.
# Run this FIRST, every time, before any test phase. It reports exactly what is present,
# what is missing, and which phases each missing item blocks — so the owner is asked ONCE,
# up front, instead of the run dying mid-way.
#
#   bash .claude/skills/e2e-whatsapp-communication/check-prereqs.sh
#
# Exit 0 = every phase can run unattended.
# Exit 1 = a HARD prerequisite is missing; nothing can run.
# Exit 2 = core is fine but some phases are blocked; run the rest, report the blocked list.

set -uo pipefail
GLOBAL_ENV="${GLOBAL_ENV:-D:/Abhay/GLOBAL.env}"
PROJ_ENV="${PROJ_ENV:-.env}"
VPS_KEY="${VPS_KEY:-$HOME/.ssh/firekaro_v6_vps}"
VPS="${VPS:-root@72.61.240.224}"

hard_missing=(); soft_missing=(); present=()

has_key() { [ -f "$2" ] && grep -qE "^$1=.+" "$2" 2>/dev/null; }

check() { # name | test-result | severity | unlocks
  local name="$1" ok="$2" sev="$3" unlocks="$4"
  if [ "$ok" = "1" ]; then
    present+=("$name")
    printf '  \033[32m[ok]\033[0m      %-34s %s\n' "$name" "$unlocks"
  elif [ "$sev" = "hard" ]; then
    hard_missing+=("$name|$unlocks")
    printf '  \033[31m[MISSING]\033[0m %-34s %s\n' "$name" "$unlocks"
  else
    soft_missing+=("$name|$unlocks")
    printf '  \033[33m[blocked]\033[0m %-34s %s\n' "$name" "$unlocks"
  fi
}

echo "=============================================================="
echo " GoRefer live E2E — PREREQUISITE GATE"
echo "=============================================================="
echo
echo "HARD — nothing can run without these:"
ssh -i "$VPS_KEY" -o BatchMode=yes -o ConnectTimeout=12 "$VPS" true >/dev/null 2>&1 && r=1 || r=0
check "VPS ssh access" "$r" hard "prod DB reads, deploys, every phase"
has_key WATI_API_TOKEN "$GLOBAL_ENV"    && r=1 || r=0
check "WATI_API_TOKEN" "$r" hard "all WhatsApp sends + delivery verification"
has_key WATI_API_ENDPOINT "$GLOBAL_ENV" && r=1 || r=0
check "WATI_API_ENDPOINT" "$r" hard "all WhatsApp sends"
curl -s -o /dev/null -m 15 -w '' https://gorefer.in/ && r=1 || r=0
check "gorefer.in reachable" "$r" hard "Phases 1,2,3,10,11"

echo
echo "PER-PHASE — missing one blocks only its phases:"
has_key ZOHO_WEBHOOK_HMAC_SECRET "$GLOBAL_ENV" && r=1 || r=0
check "ZOHO_WEBHOOK_HMAC_SECRET" "$r" soft "Phase 5 — conversion ingest / guardrail 2"
has_key ZOHO_REFRESH_TOKEN "$GLOBAL_ENV"       && r=1 || r=0
check "ZOHO_REFRESH_TOKEN" "$r" soft "Phase 4 — Zoho lead write"
# Phase 9 uses an EPHEMERAL credential (created on demand, destroyed after) — there is
# deliberately no standing prod password in .env. Check the tool, not a stored secret.
[ -f "$(dirname "$0")/phase9-admin.sh" ] && r=1 || r=0
check "phase9-admin.sh (ephemeral cred)" "$r" soft "Phase 9 — admin dashboard routes"
has_key WATI_TEST_RECIPIENTS "$GLOBAL_ENV"     && r=1 || r=0
check "WATI_TEST_RECIPIENTS" "$r" soft "every send phase (allowlist, fail-closed)"

echo
echo "OWNER-PROVIDED SESSIONS — cannot be auto-provisioned:"
ssh -i "$VPS_KEY" -o BatchMode=yes -o ConnectTimeout=12 "$VPS" \
  'ls -d ~/.config/google-chrome*/Default/Local\ Storage 2>/dev/null | head -1' 2>/dev/null | grep -q . && r=1 || r=0
check "Chrome profile on VPS" "$r" soft "prerequisite for the two sessions below"
# A logged-in session cannot be proven from disk — require an explicit confirmation marker.
# A marker OLDER THAN 7 DAYS is treated as missing (sessions expire; a stale marker is a lie) —
# re-confirm by touching it again after checking the login still works. The marker is CONSENT,
# not proof: Phase 7 must still probe liveness (chat-list DOM vs QR canvas) before relying on it.
ssh -i "$VPS_KEY" -o BatchMode=yes -o ConnectTimeout=12 "$VPS" \
  'find /root/.gorefer-e2e/whatsapp-web.ok -mtime -7 2>/dev/null' 2>/dev/null | grep -q . && r=1 || r=0
check "WhatsApp Web session (marker <7d)" "$r" soft "Phase 7 autonomy; Phase 8 OTP; Phase 6 stop_on_reply/opt-out"
ssh -i "$VPS_KEY" -o BatchMode=yes -o ConnectTimeout=12 "$VPS" \
  'find /root/.gorefer-e2e/google-session.ok -mtime -7 2>/dev/null' 2>/dev/null | grep -q . && r=1 || r=0
check "Google session (marker <7d)" "$r" soft "Phase 8 — Google OAuth login (the PRIMARY login path)"

echo
echo "=============================================================="
if [ ${#hard_missing[@]} -gt 0 ]; then
  echo " VERDICT: CANNOT RUN. Need from the owner:"
  for m in "${hard_missing[@]}"; do echo "   - ${m%%|*}  (blocks: ${m##*|})"; done
  echo "=============================================================="
  exit 1
fi
if [ ${#soft_missing[@]} -gt 0 ]; then
  echo " VERDICT: PARTIAL AUTONOMY (${#present[@]} ok, ${#soft_missing[@]} blocked)."
  echo " I will run everything else and NOT stall. To go fully autonomous, provide:"
  for m in "${soft_missing[@]}"; do echo "   - ${m%%|*}  ->  unlocks: ${m##*|}"; done
  echo
  echo " To confirm a browser session once you have logged in on the VPS:"
  echo "   ssh -i $VPS_KEY $VPS 'mkdir -p /root/.gorefer-e2e && touch /root/.gorefer-e2e/whatsapp-web.ok'"
  echo "   ssh -i $VPS_KEY $VPS 'mkdir -p /root/.gorefer-e2e && touch /root/.gorefer-e2e/google-session.ok'"
  echo "=============================================================="
  exit 2
fi
echo " VERDICT: FULLY AUTONOMOUS — every phase can run unattended."
echo "=============================================================="
exit 0
