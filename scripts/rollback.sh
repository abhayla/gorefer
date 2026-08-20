#!/usr/bin/env bash
# GoRefer rollback — flip `current` back to the previous release, in one command.
#
# This is the other half of the release-directory deploy (scripts/deploy.sh, T-162).
# Because every deploy leaves the previous release intact on disk, rolling back is a
# pointer flip plus a service restart — seconds, no git, no re-deploy, no network
# transfer of a tree. THAT is the whole reason release dirs exist.
#
# Usage:
#   scripts/rollback.sh                 # roll back to the release immediately before 'current'
#   scripts/rollback.sh <release-name>  # roll back to a specific release directory name
#   scripts/rollback.sh --list          # list the releases on the box and which one is live
#   scripts/rollback.sh --dry-run       # run the same logic against a local temp layout
#
# Env overrides match scripts/deploy.sh: DEPLOY_SSH_HOST / DEPLOY_SSH_KEY /
# DEPLOY_SSH_USER / DEPLOY_REMOTE_DIR / DEPLOY_HEALTH_URL.

set -euo pipefail

DRY_RUN=0
LIST_ONLY=0
TARGET_RELEASE=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --list) LIST_ONLY=1 ;;
    *) TARGET_RELEASE="$arg" ;;
  esac
done

SSH_USER="${DEPLOY_SSH_USER:-root}"
# The production host is NOT in this public repo (T-240). Resolve it from, in order:
#   1. $DEPLOY_SSH_HOSTNAME
#   2. the untracked file scripts/.deploy-target.env  (DEPLOY_SSH_HOSTNAME=...)
#   3. gorefer-ops/docs/deploy/DEPLOY-TARGET.md is the authoritative record of the value.
_TARGET_ENV="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.deploy-target.env"
if [ -z "${DEPLOY_SSH_HOSTNAME:-}" ] && [ -f "$_TARGET_ENV" ]; then
  # shellcheck disable=SC1090
  . "$_TARGET_ENV"
fi
if [ -z "${DEPLOY_SSH_HOSTNAME:-}" ] && [ -z "${DEPLOY_SSH_HOST:-}" ]; then
  echo "ERROR: deploy target host unknown. Set DEPLOY_SSH_HOSTNAME (or DEPLOY_SSH_HOST)," >&2
  echo "       or create scripts/.deploy-target.env with DEPLOY_SSH_HOSTNAME=<ip>." >&2
  echo "       The authoritative value lives in gorefer-ops/docs/deploy/DEPLOY-TARGET.md." >&2
  exit 2
fi
SSH_HOSTNAME="${DEPLOY_SSH_HOSTNAME:-}"
SSH_KEY="${DEPLOY_SSH_KEY:-$HOME/.ssh/firekaro_v6_vps}"
SSH_HOST="${DEPLOY_SSH_HOST:-$SSH_USER@$SSH_HOSTNAME}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)
if [[ -f "$SSH_KEY" ]]; then
  SSH_OPTS+=(-i "$SSH_KEY" -o IdentitiesOnly=yes)
fi
HEALTH_URL="${DEPLOY_HEALTH_URL:-https://gorefer.in/api/health}"

if (( DRY_RUN )); then
  ROOT="${DEPLOY_REMOTE_DIR:-${TMPDIR:-/tmp}/gorefer-deploy-dryrun}"
else
  ROOT="${DEPLOY_REMOTE_DIR:-/var/www/gorefer}"
fi
RELEASES_DIR="$ROOT/releases"
CURRENT_LINK="$ROOT/current"

remote_sh() {
  if (( DRY_RUN )); then bash -s; else ssh "${SSH_OPTS[@]}" "$SSH_HOST" "bash -s"; fi
}

preamble() {
  cat <<EOF
set -euo pipefail
ROOT='$ROOT'
RELEASES_DIR='$RELEASES_DIR'
CURRENT_LINK='$CURRENT_LINK'
EOF
}

read_current() {
  { preamble; cat <<'EOS'
if [ -L "$CURRENT_LINK" ]; then readlink "$CURRENT_LINK"
elif [ -f "$CURRENT_LINK" ]; then cat "$CURRENT_LINK"; fi
EOS
  } | remote_sh
}

CURRENT_PATH="$(read_current)"
CURRENT_NAME="$(basename "${CURRENT_PATH:-none}")"

RELEASE_LIST="$({ preamble; cat <<'EOS'
ls -1 "$RELEASES_DIR" 2>/dev/null | LC_ALL=C sort
EOS
} | remote_sh)"

if (( LIST_ONLY )); then
  echo "Releases under $RELEASES_DIR (oldest first); '*' = live:"
  while IFS= read -r r; do
    [ -z "$r" ] && continue
    if [[ "$r" == "$CURRENT_NAME" ]]; then echo " * $r"; else echo "   $r"; fi
  done <<< "$RELEASE_LIST"
  exit 0
fi

if [[ -z "$RELEASE_LIST" ]]; then
  echo "ERROR: no releases found under $RELEASES_DIR — nothing to roll back to." >&2
  exit 1
fi

if [[ -z "$TARGET_RELEASE" ]]; then
  # The release immediately before the live one, by chronological name order.
  TARGET_RELEASE="$(awk -v cur="$CURRENT_NAME" 'prev != "" && $0 == cur { print prev } { prev = $0 }' <<< "$RELEASE_LIST")"
  if [[ -z "$TARGET_RELEASE" ]]; then
    echo "ERROR: '$CURRENT_NAME' has no predecessor on the box. Available:" >&2
    sed 's/^/  /' <<< "$RELEASE_LIST" >&2
    exit 1
  fi
fi

if ! grep -qx "$TARGET_RELEASE" <<< "$RELEASE_LIST"; then
  echo "ERROR: release '$TARGET_RELEASE' does not exist. Available:" >&2
  sed 's/^/  /' <<< "$RELEASE_LIST" >&2
  exit 1
fi

echo "==> Rolling back: $CURRENT_NAME  ->  $TARGET_RELEASE"

{ preamble; cat <<EOF
TARGET="\$RELEASES_DIR/$TARGET_RELEASE"
[ -d "\$TARGET" ] || { echo "ERROR: \$TARGET is missing on the box." >&2; exit 1; }
if ln -sfn "\$TARGET" "\$CURRENT_LINK.tmp" 2>/dev/null && [ -L "\$CURRENT_LINK.tmp" ]; then
  mv -Tf "\$CURRENT_LINK.tmp" "\$CURRENT_LINK"
else
  # No-symlink filesystem (dry-run only): marker-file emulation. A failed \`ln -s\` can
  # leave a directory copy behind, so clear both paths before writing the marker.
  rm -rf "\$CURRENT_LINK.tmp"
  printf '%s\n' "\$TARGET" > "\$CURRENT_LINK.tmp"
  rm -rf "\$CURRENT_LINK"
  mv -f "\$CURRENT_LINK.tmp" "\$CURRENT_LINK"
fi
# DEPLOYED_SHA must follow the pointer, or the drift alert (scripts/check_deploy_drift.sh)
# starts reporting a SHA that is no longer serving traffic.
printf '%s\n' "$TARGET_RELEASE" | sed 's/^[0-9]*-[0-9]*-//' > "\$ROOT/DEPLOYED_SHA"
EOF
} | remote_sh

if (( DRY_RUN )); then
  echo "==> [dry-run] skipping: systemctl restart + health probe"
  echo "==> current -> $(read_current)"
  exit 0
fi

echo "==> Restarting services"
remote_sh <<<"systemctl restart gorefer gorefer-qcluster"
sleep 2
ACTIVE="$(remote_sh <<<"systemctl is-active gorefer gorefer-qcluster nginx" | tr '\n' ' ')"
echo "==> Service status: $ACTIVE"

echo "==> Probing $HEALTH_URL"
HTTP_CODE="$(curl -s -o /tmp/gorefer_rollback_health.json -w '%{http_code}' "$HEALTH_URL" || true)"
echo "==> Health probe: HTTP $HTTP_CODE"
cat /tmp/gorefer_rollback_health.json 2>/dev/null || true
echo

if [[ "$ACTIVE" != "active active active " || "$HTTP_CODE" != "200" ]]; then
  echo "ERROR: the rollback target is ALSO unhealthy (services='$ACTIVE' health=$HTTP_CODE)." >&2
  echo "       This is not a bad release — look at the DB, .env or the box itself." >&2
  exit 1
fi

echo "==> Rollback complete: $TARGET_RELEASE is live (DEPLOYED_SHA updated)."
