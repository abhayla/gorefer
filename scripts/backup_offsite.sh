#!/usr/bin/env bash
# GoRefer off-server backup sync (T-162, owner-approved point 24 C).
#
# WHY: the nightly pg_dump (/usr/local/bin/gorefer-pg-backup.sh, installed 2026-07-20)
# writes to /var/backups/postgres ON THE SAME VPS THE DATABASE RUNS ON. That protects
# against "someone dropped a table" and against nothing else. If the VPS is lost —
# disk failure, a bad `rm -rf`, an account suspension, a compromise that wipes the box —
# the backups die with the data they were protecting. This script copies the newest
# dump OFF the box, so a total loss of <PROD-VPS> costs at most one day of data.
#
# It is deliberately dumb: newest dump in, one file out, verify it landed, alert on
# failure. No rotation logic of its own — the remote destination owns retention.
#
# Install (dispatcher-owned at landing — see docs/deploy/DEPLOY-TARGET.md):
#   sudo install -m 755 /var/www/gorefer/current/scripts/backup_offsite.sh \
#        /usr/local/bin/gorefer-backup-offsite.sh
#   # runs after the 02:30 IST dump
#   printf '15 3 * * * root /usr/local/bin/gorefer-backup-offsite.sh >> /var/backups/postgres/offsite.log 2>&1\n' \
#        | sudo tee /etc/cron.d/gorefer-backup-offsite
#
# CONFIGURATION — the destination is OPERATOR-CHOSEN and lives in env, never in git.
# Put these in /etc/default/gorefer-backup-offsite (root-only, chmod 600):
#
#   BACKUP_OFFSITE_MODE=rclone            # or: scp
#   # rclone mode (recommended: any S3/B2/Drive/Dropbox remote configured with
#   # `rclone config` as root; credentials live in /root/.config/rclone/rclone.conf):
#   BACKUP_OFFSITE_REMOTE=gorefer-backups:gorefer/postgres
#   # scp mode (a second machine you control — a different provider, not this VPS):
#   BACKUP_OFFSITE_SSH=user@backup-host:/srv/backups/gorefer
#   BACKUP_OFFSITE_SSH_KEY=/root/.ssh/gorefer_backup
#   # optional, for the failure alert:
#   NOTIFIER_URL=... ; NOTIFIER_KEY=...
#
# NO CREDENTIAL OF ANY KIND BELONGS IN THIS FILE OR THIS REPO. The script reads the
# config file if it exists and refuses to run — loudly — when it is not configured.

set -uo pipefail

CONFIG_FILE="${BACKUP_OFFSITE_CONFIG:-/etc/default/gorefer-backup-offsite}"
# shellcheck disable=SC1090
[ -r "$CONFIG_FILE" ] && . "$CONFIG_FILE"

BACKUP_DIR="${BACKUP_OFFSITE_SOURCE_DIR:-/var/backups/postgres}"
MODE="${BACKUP_OFFSITE_MODE:-}"
PROJECT="gorefer"

notify() {  # $1 severity, $2 title, $3 body, $4 dedupeKey
  [ -n "${NOTIFIER_URL:-}" ] && [ -n "${NOTIFIER_KEY:-}" ] || return 0
  curl -s -o /dev/null -w 'notifier: HTTP %{http_code}\n' \
    -X POST "${NOTIFIER_URL%/}/notify" \
    -H 'Content-Type: application/json' -H "X-Api-Key: $NOTIFIER_KEY" \
    --data "$(printf '{"project":"%s","severity":"%s","title":"%s","body":"%s","type":"ops","dedupeKey":"%s"}' \
                "$PROJECT" "$1" "$2" "$3" "$4")"
}

fail() {  # $1 = message
  echo "ERROR: $1" >&2
  notify "warning" "GoRefer: off-site backup FAILED" "$1" "gorefer-offsite-fail-$(date -u +%Y-%m-%d)"
  exit 1
}

[ -n "$MODE" ] || fail "off-site backups are NOT configured ($CONFIG_FILE missing or has no BACKUP_OFFSITE_MODE). The nightly dump is still local-only."

NEWEST="$(ls -1t "$BACKUP_DIR"/*.dump "$BACKUP_DIR"/*.sql.gz "$BACKUP_DIR"/*.pgdump 2>/dev/null | head -1)"
[ -n "$NEWEST" ] || fail "no dump found in $BACKUP_DIR — the nightly pg_dump may have stopped running."

# A dump older than ~2 days means the nightly job died; copying it off-site would look
# like success while the real problem is upstream.
AGE_HOURS=$(( ( $(date +%s) - $(stat -c %Y "$NEWEST") ) / 3600 ))
if [ "$AGE_HOURS" -gt 48 ]; then
  fail "newest dump $NEWEST is ${AGE_HOURS}h old — the nightly pg_dump has stopped producing backups."
fi

SIZE="$(stat -c %s "$NEWEST")"
echo "==> Newest dump: $NEWEST (${SIZE} bytes, ${AGE_HOURS}h old)"

case "$MODE" in
  rclone)
    [ -n "${BACKUP_OFFSITE_REMOTE:-}" ] || fail "BACKUP_OFFSITE_MODE=rclone but BACKUP_OFFSITE_REMOTE is unset."
    command -v rclone >/dev/null || fail "rclone is not installed on the box."
    rclone copy --no-traverse "$NEWEST" "$BACKUP_OFFSITE_REMOTE" \
      || fail "rclone copy of $NEWEST to $BACKUP_OFFSITE_REMOTE failed."
    REMOTE_SIZE="$(rclone size --json "$BACKUP_OFFSITE_REMOTE/$(basename "$NEWEST")" 2>/dev/null \
      | sed -n 's/.*"bytes": *\([0-9]*\).*/\1/p')"
    ;;
  scp)
    [ -n "${BACKUP_OFFSITE_SSH:-}" ] || fail "BACKUP_OFFSITE_MODE=scp but BACKUP_OFFSITE_SSH is unset."
    SCP_OPTS=(-o BatchMode=yes -o ConnectTimeout=15)
    [ -n "${BACKUP_OFFSITE_SSH_KEY:-}" ] && SCP_OPTS+=(-i "$BACKUP_OFFSITE_SSH_KEY")
    scp "${SCP_OPTS[@]}" "$NEWEST" "$BACKUP_OFFSITE_SSH/" \
      || fail "scp of $NEWEST to $BACKUP_OFFSITE_SSH failed."
    SSH_TARGET="${BACKUP_OFFSITE_SSH%%:*}"
    SSH_PATH="${BACKUP_OFFSITE_SSH#*:}"
    REMOTE_SIZE="$(ssh "${SCP_OPTS[@]}" "$SSH_TARGET" "stat -c %s '$SSH_PATH/$(basename "$NEWEST")'" 2>/dev/null)"
    ;;
  *)
    fail "unknown BACKUP_OFFSITE_MODE='$MODE' (expected 'rclone' or 'scp')."
    ;;
esac

# "Copied" is not "arrived". Compare the byte count at the destination — a truncated
# upload is the classic backup that only fails on the day you need it.
if [ -z "${REMOTE_SIZE:-}" ]; then
  echo "WARN: could not read the size of the copy at the destination — treating as unverified." >&2
  notify "warning" "GoRefer: off-site backup unverified" \
    "$(basename "$NEWEST") was uploaded but its size at the destination could not be read." \
    "gorefer-offsite-unverified-$(date -u +%Y-%m-%d)"
  exit 0
fi
if [ "$REMOTE_SIZE" != "$SIZE" ]; then
  fail "size mismatch after upload: local=$SIZE remote=$REMOTE_SIZE for $(basename "$NEWEST")."
fi

echo "==> Off-site copy verified: $(basename "$NEWEST") ($SIZE bytes) at the configured destination."
