#!/usr/bin/env bash
# GoRefer production deploy — release directories + atomic `current` symlink cutover.
# Target: the Hostinger production VPS (gorefer-ops/docs/deploy/DEPLOY-TARGET.md is authoritative).
#
# WHY THIS SHAPE (T-162, owner-approved point 9 "Option B: release folders"):
#   The previous runner untarred the new tree ON TOP of the live directory. For the
#   seconds between the first extracted file and the last, prod ran a mix of two
#   commits; a failed migrate or a bad build left that mix serving traffic with no
#   way back except re-deploying the old SHA over it. Release directories make the
#   new tree invisible until it is complete, migrated and health-probed — then one
#   atomic symlink swap makes it live, and `scripts/rollback.sh` puts the previous
#   release back in one command.
#
# LAYOUT ON THE BOX ($ROOT = /var/www/gorefer by default):
#   $ROOT/releases/<UTCstamp>-<shortsha>/   one immutable checkout per deploy
#   $ROOT/current -> releases/<...>         the symlink nginx + systemd serve through
#   $ROOT/shared/.env                       runtime state, shared by every release
#   $ROOT/shared/staticfiles/               collectstatic output
#   $ROOT/shared/var/                       generated reports etc.
#   $ROOT/.venv/                            the virtualenv (shared, never re-created)
#   $ROOT/DEPLOYED_SHA                      short SHA of whatever `current` points at
#   Each release links .env / staticfiles / var / .venv back to those shared paths,
#   so a release directory is a complete, runnable app root.
#
# ORDER OF OPERATIONS (the point of the whole script):
#   1. Resolve the commit; refuse a dirty tree unless --force.
#   2. Create a NEW release dir and stream the exact committed tree into it.
#   3. Hash-verify the release byte-exact against the git blobs.
#   4. Link the shared paths in.
#   5. createcachetable (idempotent) + migrate + collectstatic + check IN THE NEW RELEASE.
#   6. Health-probe the new release on a throwaway localhost gunicorn — BEFORE the flip.
#   7. Atomically flip `current`, write DEPLOYED_SHA, restart gorefer + gorefer-qcluster.
#   8. Probe the public health URL; on failure, AUTO-ROLLBACK to the previous release.
#   9. Prune to the last N releases (default 5).
#
# Usage:
#   scripts/deploy.sh                  # deploy local HEAD
#   scripts/deploy.sh <commit-ish>     # deploy a specific commit/branch/tag
#   scripts/deploy.sh --force          # allow a dirty working tree (deploys HEAD)
#   scripts/deploy.sh --dry-run        # NO SSH: run the release-dir/flip/prune logic
#                                      #   locally against a temp dir and print it
#
# --dry-run exists so the release layout can be proven without touching prod. It runs
# every filesystem step for real (create release, extract tree, hash-verify, link
# shared, flip pointer, prune) in a temp directory, and skips exactly the steps that
# need the box (venv, migrate, systemd, public health probe), printing them instead.
#
# Access defaults to root@$DEPLOY_SSH_HOSTNAME with key ~/.ssh/firekaro_v6_vps. Override via
# DEPLOY_SSH_HOST / DEPLOY_SSH_KEY / DEPLOY_SSH_USER / DEPLOY_REMOTE_DIR /
# DEPLOY_HEALTH_URL / DEPLOY_KEEP_RELEASES / DEPLOY_PROBE_PORT.

set -euo pipefail

DRY_RUN=0
FORCE=0
COMMITISH="HEAD"
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --force) FORCE=1 ;;
    *) COMMITISH="$arg" ;;
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
APP_USER="${DEPLOY_APP_USER:-www-data}"
HEALTH_URL="${DEPLOY_HEALTH_URL:-https://gorefer.in/api/health}"
HEALTH_HOST="${DEPLOY_HEALTH_HOST:-gorefer.in}"
PROBE_PORT="${DEPLOY_PROBE_PORT:-8099}"
KEEP_RELEASES="${DEPLOY_KEEP_RELEASES:-5}"

if (( DRY_RUN )); then
  ROOT="${DEPLOY_REMOTE_DIR:-${TMPDIR:-/tmp}/gorefer-deploy-dryrun}"
else
  ROOT="${DEPLOY_REMOTE_DIR:-/var/www/gorefer}"
fi
RELEASES_DIR="$ROOT/releases"
SHARED_DIR="$ROOT/shared"
CURRENT_LINK="$ROOT/current"

# Runs a script read from stdin on the box — or locally, in dry-run.
remote_sh() {
  if (( DRY_RUN )); then
    bash -s
  else
    ssh "${SSH_OPTS[@]}" "$SSH_HOST" "bash -s"
  fi
}

# Variables the remote script bodies below rely on. Emitted as a preamble so the
# bodies themselves can stay single-quoted heredocs (no local expansion surprises).
preamble() {
  cat <<EOF
set -euo pipefail
ROOT='$ROOT'
RELEASES_DIR='$RELEASES_DIR'
SHARED_DIR='$SHARED_DIR'
CURRENT_LINK='$CURRENT_LINK'
RELEASE_DIR='${RELEASE_DIR:-}'
APP_USER='$APP_USER'
KEEP_RELEASES='$KEEP_RELEASES'
PROBE_PORT='$PROBE_PORT'
HEALTH_HOST='$HEALTH_HOST'
DRY_RUN='$DRY_RUN'
EOF
}

# ---------------------------------------------------------------- resolve commit
if [[ "$COMMITISH" == "HEAD" && "$FORCE" -ne 1 ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: working tree is dirty. Commit/stash first, or pass --force to deploy HEAD as-is." >&2
    exit 1
  fi
fi

SHA="$(git rev-parse "$COMMITISH")"
SHORT_SHA="$(git rev-parse --short "$COMMITISH")"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
RELEASE_NAME="$STAMP-$SHORT_SHA"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_NAME"

if (( DRY_RUN )); then
  echo "==> DRY RUN — no SSH, no prod. Simulating a deploy of $SHORT_SHA under $ROOT"
else
  echo "==> Deploying $SHORT_SHA ($SHA) to $SSH_HOST:$ROOT as release $RELEASE_NAME"
  remote_sh <<<"echo ok" >/dev/null \
    || { echo "ERROR: cannot reach $SSH_HOST over SSH (key: $SSH_KEY)." >&2; exit 1; }
fi

# ------------------------------------------------- 1. prepare layout + release dir
echo "==> Preparing layout and release directory $RELEASE_NAME"
{ preamble; cat <<'EOS'
mkdir -p "$RELEASES_DIR" "$SHARED_DIR" "$RELEASE_DIR"
# Shared runtime state: created empty on first deploy, never overwritten afterwards.
mkdir -p "$SHARED_DIR/staticfiles" "$SHARED_DIR/var"
[ -e "$SHARED_DIR/.env" ] || : > "$SHARED_DIR/.env"
# The pointer is a SYMLINK. On a filesystem/OS that cannot create one (a Windows
# dry-run without Developer Mode), fall back to a plain marker file so the ordering
# and pruning logic is still exercised end to end — loudly, never silently.
if ln -sfn "$SHARED_DIR" "$ROOT/.symlink-probe" 2>/dev/null && [ -L "$ROOT/.symlink-probe" ]; then
  echo "    symlinks: native"
else
  echo "    symlinks: NOT SUPPORTED HERE — using marker-file emulation (dry-run only)"
fi
rm -rf "$ROOT/.symlink-probe"
EOS
} | remote_sh

# ------------------------------------------------------- 2. stream committed tree
echo "==> Streaming committed tree ($SHA) into $RELEASE_DIR"
# -c core.autocrlf=false is required on a Windows dev box: the global autocrlf=true
# setting makes `git archive` silently rewrite LF -> CRLF in every text file it
# streams, which then fails hash verification against the LF git blobs (the "Windows
# git-archive CRLF trap" — hit repeatedly per COORDINATION.md history).
if (( DRY_RUN )); then
  git -c core.autocrlf=false archive "$SHA" | ( cd "$RELEASE_DIR" && tar -x )
else
  git -c core.autocrlf=false archive "$SHA" \
    | ssh "${SSH_OPTS[@]}" "$SSH_HOST" "set -euo pipefail; cd '$RELEASE_DIR' && tar -x && chown -R $APP_USER:$APP_USER '$RELEASE_DIR'"
fi

# -------------------------------------------------------- 3. hash-verify the tree
# One pass on each side, then a single diff — the old per-file SSH round-trip took
# minutes and hid which file drifted behind a wall of output.
echo "==> Hash-verifying the release byte-exact against the git blobs"
LOCAL_EXTRACT="$(mktemp -d)"
trap 'rm -rf "$LOCAL_EXTRACT" "$LOCAL_EXTRACT.manifest" "$LOCAL_EXTRACT.remote-manifest" "$LOCAL_EXTRACT.manifest.norm" "$LOCAL_EXTRACT.remote-manifest.norm"' EXIT
git -c core.autocrlf=false archive "$SHA" | ( cd "$LOCAL_EXTRACT" && tar -x )
# -print0/-0 throughout: the repo has paths with spaces ("review/Claude Output.md"), and a
# newline-split manifest silently turns those into two missing files.
( cd "$LOCAL_EXTRACT" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 md5sum ) > "$LOCAL_EXTRACT.manifest"
{ preamble; cat <<'EOS'
cd "$RELEASE_DIR"
find . -type f -print0 | LC_ALL=C sort -z | xargs -0 md5sum
EOS
} | remote_sh > "$LOCAL_EXTRACT.remote-manifest"

# Windows-binary-marker trap (found live 2026-08-17, first release-dir cutover): Git-Bash/Windows
# md5sum writes "<hash> *./path" (binary-mode marker, a literal '*' before the path); GNU/Linux
# md5sum writes "<hash>  ./path" (text mode, two spaces, no marker). Same bytes, different manifest
# text, so every one of 575 lines diffed as "different" even though content was byte-identical.
# Normalize both manifests to the text-mode form (drop the binary '*' marker) before diffing —
# this makes the comparison platform-independent regardless of which side (or both) is Windows.
normalize_manifest() { sed -E 's/^([0-9a-f]+) \*/\1  /' "$1"; }
normalize_manifest "$LOCAL_EXTRACT.manifest" > "$LOCAL_EXTRACT.manifest.norm"
normalize_manifest "$LOCAL_EXTRACT.remote-manifest" > "$LOCAL_EXTRACT.remote-manifest.norm"

if ! diff -q "$LOCAL_EXTRACT.manifest.norm" "$LOCAL_EXTRACT.remote-manifest.norm" >/dev/null; then
  echo "ERROR: deployed release does not match the git blobs. Differences:" >&2
  diff "$LOCAL_EXTRACT.manifest.norm" "$LOCAL_EXTRACT.remote-manifest.norm" | head -40 >&2
  echo "The release directory was NOT activated; 'current' still points at the old release." >&2
  exit 1
fi
echo "==> All $(wc -l < "$LOCAL_EXTRACT.manifest.norm" | tr -d ' ') files byte-exact vs git blobs"

# ------------------------------------------------------- 4. link the shared paths
echo "==> Linking shared runtime state into the release"
{ preamble; cat <<'EOS'
link_shared() {  # $1 = name inside the release, $2 = absolute shared target
  rm -rf "$RELEASE_DIR/$1"
  if ln -sfn "$2" "$RELEASE_DIR/$1" 2>/dev/null && [ -L "$RELEASE_DIR/$1" ]; then
    return 0
  fi
  # Emulation fallback (dry-run on a no-symlink filesystem): record the intent. The
  # failed `ln` may have left a COPY behind (MSYS ln -s copies), so clear it first.
  rm -rf "$RELEASE_DIR/$1"
  printf '%s\n' "$2" > "$RELEASE_DIR/$1"
  echo "    [emulated] $1 -> $2"
}
link_shared ".env"         "$SHARED_DIR/.env"
link_shared "staticfiles"  "$SHARED_DIR/staticfiles"
link_shared "var"          "$SHARED_DIR/var"
link_shared ".venv"        "$ROOT/.venv"
EOS
} | remote_sh

# ------------------------------- 5. cache table + migrate + collectstatic + check
if (( DRY_RUN )); then
  echo "==> [dry-run] skipping: createcachetable / migrate / collectstatic / check (needs the box's venv + DB)"
else
  echo "==> Running createcachetable + migrate + collectstatic + check in the new release"
  { preamble; cat <<'EOS'
cd "$RELEASE_DIR"
# createcachetable is idempotent: Django prints "already exists" and exits 0 when the
# table is there. Running it every deploy is what stops the T-162 failure mode where a
# fresh box (or a restored DB) has no cache table and the rate limiter blows up.
sudo -u "$APP_USER" .venv/bin/python manage.py createcachetable
sudo -u "$APP_USER" .venv/bin/python manage.py migrate --noinput
sudo -u "$APP_USER" .venv/bin/python manage.py collectstatic --noinput
sudo -u "$APP_USER" .venv/bin/python manage.py check --deploy \
  || sudo -u "$APP_USER" .venv/bin/python manage.py check
EOS
  } | remote_sh
fi

# ---------------------------------------------- 6. health-probe BEFORE the flip
if (( DRY_RUN )); then
  echo "==> [dry-run] skipping: pre-flip gunicorn health probe on 127.0.0.1:$PROBE_PORT"
else
  echo "==> Health-probing the NEW release on 127.0.0.1:$PROBE_PORT (before the flip)"
  { preamble; cat <<'EOS'
cd "$RELEASE_DIR"
PIDFILE="/tmp/gorefer-preflip-probe.pid"
rm -f "$PIDFILE"
sudo -u "$APP_USER" .venv/bin/gunicorn gorefer.wsgi:application \
  --bind "127.0.0.1:$PROBE_PORT" --workers 1 --timeout 30 --daemon \
  --pid "$PIDFILE" --access-logfile /dev/null --error-logfile /tmp/gorefer-preflip-probe.err
cleanup() { [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null || true; }
trap cleanup EXIT
CODE=000
for _ in $(seq 1 30); do
  CODE="$(curl -s -o /tmp/gorefer-preflip-probe.json -w '%{http_code}' \
      -H "Host: $HEALTH_HOST" -H 'X-Forwarded-Proto: https' \
      "http://127.0.0.1:$PROBE_PORT/api/health" || true)"
  [ "$CODE" = "200" ] && break
  sleep 1
done
cleanup
if [ "$CODE" != "200" ]; then
  echo "ERROR: the new release failed its pre-flip health probe (HTTP $CODE)." >&2
  echo "       'current' was NOT flipped — prod is untouched and still on the old release." >&2
  tail -20 /tmp/gorefer-preflip-probe.err >&2 || true
  exit 1
fi
echo "    pre-flip health probe: HTTP 200"
EOS
  } | remote_sh
fi

# ------------------------------------------------------- 7. atomic pointer flip
echo "==> Flipping 'current' to $RELEASE_NAME (atomic)"
PREVIOUS_RELEASE="$(
  { preamble; cat <<'EOS'
if [ -L "$CURRENT_LINK" ]; then
  readlink "$CURRENT_LINK"
elif [ -f "$CURRENT_LINK" ]; then
  cat "$CURRENT_LINK"
fi
EOS
  } | remote_sh
)"
echo "    previous release: ${PREVIOUS_RELEASE:-<none — first release-dir deploy>}"

{ preamble; cat <<'EOS'
# `ln -sfn` on an EXISTING symlink-to-a-directory creates the link INSIDE it, which is
# why the swap goes through a temp name + `mv -T`: mv over a symlink is atomic (a single
# rename(2)), so no request ever sees a missing or half-written 'current'.
if ln -sfn "$RELEASE_DIR" "$CURRENT_LINK.tmp" 2>/dev/null && [ -L "$CURRENT_LINK.tmp" ]; then
  mv -Tf "$CURRENT_LINK.tmp" "$CURRENT_LINK"
else
  rm -rf "$CURRENT_LINK.tmp"
  printf '%s\n' "$RELEASE_DIR" > "$CURRENT_LINK.tmp"
  rm -rf "$CURRENT_LINK"
  mv -f "$CURRENT_LINK.tmp" "$CURRENT_LINK"
  echo "    [emulated] current -> $RELEASE_DIR"
fi
EOS
} | remote_sh

echo "==> Writing DEPLOYED_SHA"
{ preamble; cat <<EOF
printf '%s\n' '$SHORT_SHA' > "\$ROOT/DEPLOYED_SHA"
EOF
} | remote_sh

# --------------------------------------------------------- 8. restart + verify
if (( DRY_RUN )); then
  echo "==> [dry-run] skipping: systemctl restart gorefer gorefer-qcluster + public health probe"
else
  echo "==> Restarting services"
  remote_sh <<<"systemctl restart gorefer gorefer-qcluster"
  sleep 2
  ACTIVE="$(remote_sh <<<"systemctl is-active gorefer gorefer-qcluster nginx" | tr '\n' ' ')"
  echo "==> Service status: $ACTIVE"

  echo "==> Probing $HEALTH_URL"
  HTTP_CODE="$(curl -s -o /tmp/gorefer_deploy_health.json -w '%{http_code}' "$HEALTH_URL" || true)"
  echo "==> Health probe: HTTP $HTTP_CODE"
  cat /tmp/gorefer_deploy_health.json 2>/dev/null || true
  echo

  if [[ "$ACTIVE" != "active active active " || "$HTTP_CODE" != "200" ]]; then
    echo "ERROR: post-flip verification failed (services='$ACTIVE' health=$HTTP_CODE)." >&2
    if [[ -n "$PREVIOUS_RELEASE" ]]; then
      echo "==> AUTO-ROLLBACK to $PREVIOUS_RELEASE" >&2
      { preamble; cat <<EOF
if ln -sfn '$PREVIOUS_RELEASE' "\$CURRENT_LINK.tmp" 2>/dev/null && [ -L "\$CURRENT_LINK.tmp" ]; then
  mv -Tf "\$CURRENT_LINK.tmp" "\$CURRENT_LINK"
else
  rm -rf "\$CURRENT_LINK.tmp" "\$CURRENT_LINK"
  printf '%s\n' '$PREVIOUS_RELEASE' > "\$CURRENT_LINK"
fi
basename '$PREVIOUS_RELEASE' | sed 's/^[0-9]*-[0-9]*-//' > "\$ROOT/DEPLOYED_SHA"
systemctl restart gorefer gorefer-qcluster
EOF
      } | remote_sh
      echo "==> Rolled back to the previous release. Investigate before re-deploying." >&2
    else
      echo "       No previous release to roll back to — fix forward." >&2
    fi
    exit 1
  fi
fi

# ------------------------------------------------------------------- 9. prune
echo "==> Pruning old releases (keeping the newest $KEEP_RELEASES)"
{ preamble; cat <<'EOS'
CUR=""
if [ -L "$CURRENT_LINK" ]; then CUR="$(readlink "$CURRENT_LINK")"; elif [ -f "$CURRENT_LINK" ]; then CUR="$(cat "$CURRENT_LINK")"; fi
cd "$RELEASES_DIR"
# Names sort chronologically (UTC stamp first), so "all but the newest N" is a head cut.
TOTAL="$(ls -1 | LC_ALL=C sort | wc -l)"
if [ "$TOTAL" -gt "$KEEP_RELEASES" ]; then
  ls -1 | LC_ALL=C sort | head -n "$((TOTAL - KEEP_RELEASES))" | while IFS= read -r old; do
    # Never delete whatever 'current' points at, whatever the ordering says.
    if [ "$RELEASES_DIR/$old" = "$CUR" ]; then
      echo "    keeping $old (it is 'current')"
      continue
    fi
    echo "    removing $old"
    rm -rf "${RELEASES_DIR:?}/$old"
  done
fi
echo "    releases now: $(ls -1 | LC_ALL=C sort | tr '\n' ' ')"
EOS
} | remote_sh

if (( DRY_RUN )); then
  echo "==> DRY RUN complete. Layout under $ROOT:"
  { preamble; cat <<'EOS'
ls -1 "$ROOT"
echo "current -> $( [ -L "$CURRENT_LINK" ] && readlink "$CURRENT_LINK" || cat "$CURRENT_LINK" )"
echo "DEPLOYED_SHA = $(cat "$ROOT/DEPLOYED_SHA")"
EOS
  } | remote_sh
else
  echo "==> Deploy complete: $SHORT_SHA is live via $CURRENT_LINK -> $RELEASE_DIR"
  echo "    Roll back with: scripts/rollback.sh"
fi
