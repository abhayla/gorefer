#!/usr/bin/env bash
# GoRefer deploy-drift alert (T-162, owner-approved point 9b).
#
# WHY: three separate times, the SHA recorded as deployed and the SHA actually serving
# gorefer.in disagreed and nobody noticed for days (COORDINATION.md: the 2026-07-21
# stale-state incident, the `3db7c59` / `f4f079f` mismatch, the `324a1b8` marker drift).
# Every one was found by a human happening to look. This script is the instrument that
# looks: it compares the box's DEPLOYED_SHA to origin/main's HEAD and, on a mismatch,
# POSTs one alert to the shared Notifier gateway (GLOBAL.md §2).
#
# It runs ON THE VPS from cron. It is read-only: it never deploys, never restarts,
# never edits DEPLOYED_SHA — it only reports.
#
# Install (dispatcher-owned at landing — see docs/deploy/DEPLOY-TARGET.md):
#   sudo install -m 755 /var/www/gorefer/current/scripts/check_deploy_drift.sh \
#        /usr/local/bin/gorefer-deploy-drift.sh
#   printf '30 6 * * * root /usr/local/bin/gorefer-deploy-drift.sh >> /var/log/gorefer-deploy-drift.log 2>&1\n' \
#        | sudo tee /etc/cron.d/gorefer-deploy-drift
#
# Env (read from $ENV_FILE, default /var/www/gorefer/shared/.env, then the environment):
#   NOTIFIER_URL / NOTIFIER_KEY   the Notifier gateway (no alert can be sent without them)
#   DEPLOY_GIT_REMOTE             git remote to read main from (default: the public HTTPS URL;
#                                 for a private repo set a credentialed URL or GITHUB_TOKEN)
#   GITHUB_TOKEN                  optional; if set, the GitHub API is used instead of git
#   GOREFER_ROOT                  deploy root (default /var/www/gorefer)

set -uo pipefail

ROOT="${GOREFER_ROOT:-/var/www/gorefer}"
ENV_FILE="${ENV_FILE:-$ROOT/shared/.env}"
GIT_REMOTE="${DEPLOY_GIT_REMOTE:-https://github.com/abhayla/gorefer.git}"
BRANCH="${DEPLOY_GIT_BRANCH:-main}"
PROJECT="gorefer"

# Pull NOTIFIER_* (and any override above) out of the app's env file without executing it.
if [ -r "$ENV_FILE" ]; then
  while IFS='=' read -r key value; do
    case "$key" in
      NOTIFIER_URL|NOTIFIER_KEY|DEPLOY_GIT_REMOTE|GITHUB_TOKEN)
        value="${value%\"}"; value="${value#\"}"
        export "$key=$value"
        ;;
    esac
  done < <(grep -E '^(NOTIFIER_URL|NOTIFIER_KEY|DEPLOY_GIT_REMOTE|GITHUB_TOKEN)=' "$ENV_FILE" || true)
fi
GIT_REMOTE="${DEPLOY_GIT_REMOTE:-$GIT_REMOTE}"

notify() {  # $1 severity (P0|P1|P2|info), $2 title, $3 body, $4 dedupeKey
  if [ -z "${NOTIFIER_URL:-}" ] || [ -z "${NOTIFIER_KEY:-}" ]; then
    echo "WARN: NOTIFIER_URL/NOTIFIER_KEY not set — cannot alert. Message was: $2 / $3" >&2
    return 1
  fi
  local http_code
  http_code="$(curl -s -o /dev/null -w '%{http_code}' \
    -X POST "${NOTIFIER_URL%/}/notify" \
    -H 'Content-Type: application/json' \
    -H "X-Api-Key: $NOTIFIER_KEY" \
    --data "$(printf '{"project":"%s","severity":"%s","title":"%s","body":"%s","type":"ops","dedupeKey":"%s"}' \
                "$PROJECT" "$1" "$2" "$3" "$4")")"
  if [ "${http_code:-000}" -ge 200 ] 2>/dev/null && [ "${http_code:-000}" -lt 300 ] 2>/dev/null; then
    echo "notifier: HTTP $http_code"
  else
    echo "WARN: notifier POST failed — HTTP $http_code" >&2
    return 1
  fi
}

DEPLOYED="$(cat "$ROOT/DEPLOYED_SHA" 2>/dev/null | tr -d '[:space:]')"
if [ -z "$DEPLOYED" ]; then
  echo "DEPLOYED_SHA missing/empty at $ROOT/DEPLOYED_SHA"
  notify "P2" "GoRefer: DEPLOYED_SHA missing" \
    "No readable $ROOT/DEPLOYED_SHA on the box — the deploy marker is gone, so drift cannot be measured." \
    "gorefer-drift-nomarker-$(date -u +%Y-%m-%d)"
  exit 1
fi

# Origin HEAD: git first (works for a public repo or a credentialed remote), GitHub API
# as the fallback when a token is configured.
ORIGIN=""
ORIGIN="$(git ls-remote "$GIT_REMOTE" "refs/heads/$BRANCH" 2>/dev/null | awk '{print $1}')"
if [ -z "$ORIGIN" ] && [ -n "${GITHUB_TOKEN:-}" ]; then
  API_REPO="$(printf '%s' "$GIT_REMOTE" | sed -E 's#.*github\.com[/:]##; s#\.git$##')"
  ORIGIN="$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
      "https://api.github.com/repos/$API_REPO/commits/$BRANCH" \
    | sed -n 's/.*"sha": *"\([0-9a-f]\{7,\}\)".*/\1/p' | head -1)"
fi

if [ -z "$ORIGIN" ]; then
  # Degraded, not silent: an unreadable origin is itself worth one alert a day. A
  # drift check that quietly stops checking is exactly the failure it exists to prevent.
  echo "Could not read $BRANCH from $GIT_REMOTE (no credentials?)"
  notify "P2" "GoRefer: drift check degraded" \
    "Could not read origin/$BRANCH from $GIT_REMOTE — set DEPLOY_GIT_REMOTE (credentialed) or GITHUB_TOKEN. Deployed SHA reads $DEPLOYED." \
    "gorefer-drift-degraded-$(date -u +%Y-%m-%d)"
  exit 1
fi

SHORT_ORIGIN="$(printf '%s' "$ORIGIN" | cut -c1-${#DEPLOYED})"
if [ "$SHORT_ORIGIN" = "$DEPLOYED" ]; then
  echo "OK: deployed $DEPLOYED == origin/$BRANCH $SHORT_ORIGIN"
  exit 0
fi

echo "DRIFT: deployed $DEPLOYED != origin/$BRANCH $SHORT_ORIGIN"
notify "P2" "GoRefer: prod is behind origin/$BRANCH" \
  "Box DEPLOYED_SHA=$DEPLOYED but origin/$BRANCH HEAD=$SHORT_ORIGIN. Either a merge was never deployed, or a deploy never updated the marker. Check with: ssh root@$DEPLOY_SSH_HOSTNAME 'cat $ROOT/DEPLOYED_SHA; readlink $ROOT/current'" \
  "gorefer-drift-$DEPLOYED-$SHORT_ORIGIN"
exit 0
