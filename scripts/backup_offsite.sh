#!/usr/bin/env bash
# GoRefer off-server backup sync (T-162, owner-approved point 24 C).
#
# WHY: the nightly pg_dump (/usr/local/bin/gorefer-pg-backup.sh, installed 2026-07-20)
# writes to /var/backups/postgres ON THE SAME VPS THE DATABASE RUNS ON. That protects
# against "someone dropped a table" and against nothing else. If the VPS is lost —
# disk failure, a bad `rm -rf`, an account suspension, a compromise that wipes the box —
# the backups die with the data they were protecting. This script copies the newest
# dump OFF the box, so a total loss of the production VPS costs at most one day of data.
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
#   # scp mode (a second machine you control — a different provider, not this VPS).
#   # The destination can be Linux OR Windows (OpenSSH server, e.g. a Hostinger
#   # Windows VPS) — the remote-size verification tries `stat` first, falls back
#   # to sftp's `ls -l` (works against either OS's sftp-server), then a
#   # PowerShell one-liner, so no destination-OS assumption is required here:
#   BACKUP_OFFSITE_SSH=user@backup-host:/srv/backups/gorefer
#   # Windows example: BACKUP_OFFSITE_SSH=Administrator@203.0.113.9:C:/Abhay/Backups/gorefer-postgres
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
  notify "P1" "GoRefer: off-site backup FAILED" "$1" "gorefer-offsite-fail-$(date -u +%Y-%m-%d)"
  exit 1
}

# Reads the size (bytes) of a remote file over the SAME ssh key/opts already in
# use, without assuming the remote shell is POSIX. Windows OpenSSH servers default
# the login shell to cmd.exe/PowerShell, so `ssh host stat ...` fails there even
# though the copy itself (scp, which speaks the sftp/scp wire protocol, not the
# remote shell) succeeded. Try three probes, in order, and use the first that
# returns a plain integer:
#   1. `stat -c %s` over ssh   — works for Linux/macOS/WSL remotes.
#   2. `sftp -b - ls -l`       — the sftp wire protocol's directory listing is
#                                 unix-`ls -l`-shaped on every sftp-server
#                                 implementation (incl. Windows OpenSSH's), so
#                                 this is the platform-neutral case.
#   3. a PowerShell one-liner  — last resort for a Windows remote whose sftp
#                                 subsystem is disabled but whose login shell is
#                                 PowerShell/cmd.
remote_file_size() {  # $1 = ssh target (user@host), $2 = remote path, remaining = ssh opts
  local target="$1" path="$2"; shift 2
  local opts=("$@")
  local size

  size="$(ssh "${opts[@]}" "$target" "stat -c %s '$path'" 2>/dev/null)"
  if [ -n "$size" ] && [ "$size" -eq "$size" ] 2>/dev/null; then
    printf '%s' "$size"
    return 0
  fi

  # Windows OpenSSH's sftp-server roots drive-letter paths (`C:/...`) under the
  # login home directory unless given a leading slash (`/C:/...`); a Linux path
  # is already slash-rooted, so only add the extra slash for the drive-letter form.
  local sftp_path="$path"
  case "$path" in
    [A-Za-z]:*) sftp_path="/$path" ;;
  esac
  size="$(sftp -b - "${opts[@]}" "$target" <<EOF 2>/dev/null | grep -oE '[0-9]+ [A-Za-z]{3} +[0-9]+ ' | awk '{print $1}' | head -1
ls -l "$sftp_path"
EOF
  )"
  if [ -n "$size" ] && [ "$size" -eq "$size" ] 2>/dev/null; then
    printf '%s' "$size"
    return 0
  fi

  size="$(ssh "${opts[@]}" "$target" "powershell -NoProfile -NonInteractive -Command \"(Get-Item -LiteralPath '$path').Length\"" 2>/dev/null | tr -d '\r')"
  if [ -n "$size" ] && [ "$size" -eq "$size" ] 2>/dev/null; then
    printf '%s' "$size"
    return 0
  fi

  return 1
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
    REMOTE_SIZE="$(remote_file_size "$SSH_TARGET" "$SSH_PATH/$(basename "$NEWEST")" "${SCP_OPTS[@]}")"
    ;;
  *)
    fail "unknown BACKUP_OFFSITE_MODE='$MODE' (expected 'rclone' or 'scp')."
    ;;
esac

# "Copied" is not "arrived". Compare the byte count at the destination — a truncated
# upload is the classic backup that only fails on the day you need it.
if [ -z "${REMOTE_SIZE:-}" ]; then
  echo "WARN: could not read the size of the copy at the destination — treating as unverified." >&2
  notify "P2" "GoRefer: off-site backup unverified" \
    "$(basename "$NEWEST") was uploaded but its size at the destination could not be read." \
    "gorefer-offsite-unverified-$(date -u +%Y-%m-%d)"
  exit 0
fi
if [ "$REMOTE_SIZE" != "$SIZE" ]; then
  fail "size mismatch after upload: local=$SIZE remote=$REMOTE_SIZE for $(basename "$NEWEST")."
fi

echo "==> Off-site copy verified: $(basename "$NEWEST") ($SIZE bytes) at the configured destination."
