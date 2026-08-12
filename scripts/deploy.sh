#!/usr/bin/env bash
# GoRefer production deploy — Hostinger VPS <PROD-VPS> (docs/deploy/DEPLOY-TARGET.md is
# authoritative; this script is a mechanical wrapper around the manual pattern that has
# deployed every GoRefer release to date, recorded across dozens of COORDINATION.md entries
# as "git-show pipe … blob-hash-verified").
#
# What it does, in order:
#   1. Resolve the target commit (default: local HEAD) and refuse a dirty tree unless --force.
#   2. Stream the exact committed tree for that commit into /var/www/gorefer over SSH via
#      `git archive | ssh ... tar -x`, WITHOUT touching .env / .venv / staticfiles / DEPLOYED_SHA
#      (those are the box's runtime state, never part of the git tree being deployed).
#   3. Hash-verify every deployed file against its git blob (byte-exact, catches any transport
#      corruption or CRLF mangling before it reaches prod).
#   4. Run `migrate` + `collectstatic --noinput` + `manage.py check` inside the venv as www-data.
#   5. Restart gorefer + gorefer-qcluster, wait for both (+ nginx) to report active.
#   6. Write DEPLOYED_SHA on the box and probe https://gorefer.in/api/health.
#
# Usage:
#   scripts/deploy.sh                  # deploy local HEAD
#   scripts/deploy.sh <commit-ish>     # deploy a specific commit/branch/tag
#   scripts/deploy.sh --force          # allow a dirty working tree (deploys HEAD, not the tree)
#
# Target + access per docs/deploy/DEPLOY-TARGET.md: root@<PROD-VPS> over SSH with key
# ~/.ssh/firekaro_v6_vps. Override via DEPLOY_SSH_HOST / DEPLOY_SSH_KEY / DEPLOY_SSH_USER env
# vars if your local SSH setup differs (e.g. a config alias) — the script never assumes an
# alias exists.

set -euo pipefail

SSH_USER="${DEPLOY_SSH_USER:-root}"
SSH_HOSTNAME="${DEPLOY_SSH_HOSTNAME:-<PROD-VPS>}"
SSH_KEY="${DEPLOY_SSH_KEY:-$HOME/.ssh/firekaro_v6_vps}"
SSH_HOST="${DEPLOY_SSH_HOST:-$SSH_USER@$SSH_HOSTNAME}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)
if [[ -f "$SSH_KEY" ]]; then
  SSH_OPTS+=(-i "$SSH_KEY" -o IdentitiesOnly=yes)
fi
REMOTE_DIR="${DEPLOY_REMOTE_DIR:-/var/www/gorefer}"
REMOTE_USER="www-data"
HEALTH_URL="${DEPLOY_HEALTH_URL:-https://gorefer.in/api/health}"

ssh_run() { ssh "${SSH_OPTS[@]}" "$SSH_HOST" "$@"; }

FORCE=0
COMMITISH="HEAD"
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    *) COMMITISH="$arg" ;;
  esac
done

if [[ "$COMMITISH" == "HEAD" && "$FORCE" -ne 1 ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: working tree is dirty. Commit/stash first, or pass --force to deploy HEAD as-is." >&2
    exit 1
  fi
fi

SHA="$(git rev-parse "$COMMITISH")"
SHORT_SHA="$(git rev-parse --short "$COMMITISH")"
echo "==> Deploying $SHORT_SHA ($SHA) to $SSH_HOST:$REMOTE_DIR"

ssh_run "echo ok" >/dev/null \
  || { echo "ERROR: cannot reach $SSH_HOST over SSH (key: $SSH_KEY)." >&2; exit 1; }

echo "==> Streaming committed tree ($SHA) into $REMOTE_DIR (preserving .env/.venv/staticfiles/DEPLOYED_SHA)"
# -c core.autocrlf=false is required on a Windows dev box: the global autocrlf=true setting
# makes `git archive` silently rewrite LF -> CRLF in every text file it streams, which then
# fails hash verification against the LF git blobs (the "Windows git-archive CRLF trap" —
# hit and worked around repeatedly per COORDINATION.md history). Force LF-exact output here.
git -c core.autocrlf=false archive "$SHA" | ssh "${SSH_OPTS[@]}" "$SSH_HOST" "
  set -euo pipefail
  cd '$REMOTE_DIR'
  tar -x
  chown -R $REMOTE_USER:$REMOTE_USER .
"

echo "==> Hash-verifying deployed files against git blobs"
git ls-tree -r --name-only "$SHA" | while IFS= read -r path; do
  local_hash="$(git show "$SHA:$path" | md5sum | cut -d' ' -f1)"
  remote_hash="$(ssh_run "md5sum '$REMOTE_DIR/$path' 2>/dev/null | cut -d' ' -f1" || true)"
  if [[ "$local_hash" != "$remote_hash" ]]; then
    echo "ERROR: hash mismatch for $path (local=$local_hash remote=$remote_hash)" >&2
    exit 1
  fi
done
echo "==> All files byte-exact vs git blobs"

echo "==> Running migrate + collectstatic + check on the box"
ssh_run "
  set -euo pipefail
  cd '$REMOTE_DIR'
  sudo -u $REMOTE_USER .venv/bin/python manage.py migrate --noinput
  sudo -u $REMOTE_USER .venv/bin/python manage.py collectstatic --noinput
  sudo -u $REMOTE_USER .venv/bin/python manage.py check --deploy || sudo -u $REMOTE_USER .venv/bin/python manage.py check
"

echo "==> Restarting services"
ssh_run "systemctl restart gorefer gorefer-qcluster"
sleep 2
ACTIVE="$(ssh_run "systemctl is-active gorefer gorefer-qcluster nginx" | tr '\n' ' ')"
echo "==> Service status: $ACTIVE"
if [[ "$ACTIVE" != "active active active " ]]; then
  echo "ERROR: not all services report active ($ACTIVE)." >&2
  exit 1
fi

echo "==> Writing DEPLOYED_SHA on the box"
ssh_run "echo '$SHORT_SHA' > '$REMOTE_DIR/DEPLOYED_SHA'"

echo "==> Probing $HEALTH_URL"
HTTP_CODE="$(curl -s -o /tmp/gorefer_deploy_health.json -w '%{http_code}' "$HEALTH_URL")"
echo "==> Health probe: HTTP $HTTP_CODE"
cat /tmp/gorefer_deploy_health.json
echo
if [[ "$HTTP_CODE" != "200" ]]; then
  echo "ERROR: health probe did not return 200." >&2
  exit 1
fi

echo "==> Deploy complete: $SHORT_SHA is live and DEPLOYED_SHA updated."
