#!/bin/bash
# Nightly OFF-BOX copy of the Iguana Comedy backups (runs on the DEV BOX, from john's crontab).
#
# The server keeps its own dumps in /var/backups/iguana (iguana-db-backup.sh), which is worthless the day the
# VPS dies. This pulls them here and checks the newest one is recent and a valid gzip.
#
# No --delete: if the server's backup folder is ever emptied, by accident or by an attacker, a mirroring pull
# would empty this copy too. Local pruning is by age instead, and keeps more than the server does.
# Failures are greppable as `ERROR iguana_backup_pull` in the log.
set -uo pipefail

HOST=iguana@38.86.78.36
DEST=/home/john/backups/iguana
LOG="$DEST/pull.log"
LOCK=/tmp/iguana_backup_pull.lock
KEEP_DAILY=90

mkdir -p "$DEST"
chmod 700 "$DEST"
exec >>"$LOG" 2>&1
echo "=== $(date -Is) iguana_backup_pull start ==="

flock -n "$LOCK" timeout 20m rsync -a -e "ssh -o BatchMode=yes -o ConnectTimeout=20" "$HOST:/var/backups/iguana/" "$DEST/"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "ERROR iguana_backup_pull: rsync exited $rc"
  exit "$rc"
fi

# The uploads that live only on the server: /upload/'s documents, /comic/ submissions, and the original videos and
# chat attachments (2026-10-28). Never mirrored with --delete, so a file removed on the server stays here. Skipped:
# half-finished upload pieces, the clip finder's scratch, the trash, and the web copies (made again from originals).
flock -n "$LOCK.files" timeout 3h rsync -a -e "ssh -o BatchMode=yes -o ConnectTimeout=20" \
  --exclude '.parts/' --exclude 'clips-work/' --exclude '.trash/' \
  "$HOST:/var/lib/iguana/drop" "$HOST:/var/lib/iguana/comics" "$HOST:/var/lib/iguana/chat-files" "$DEST/files/"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "ERROR iguana_backup_pull: uploads rsync exited $rc"
fi

newest=$(ls -1t "$DEST"/daily/iguana-*.sql.gz 2>/dev/null | head -1)
if [ -z "$newest" ]; then
  echo "ERROR iguana_backup_pull: no daily dump arrived"
  exit 1
fi
age_h=$(( ( $(date +%s) - $(stat -c %Y "$newest") ) / 3600 ))
if [ "$age_h" -gt 36 ]; then
  echo "ERROR iguana_backup_pull: newest dump is ${age_h}h old ($newest), so the server's nightly backup has stopped"
  exit 1
fi
if ! gzip -t "$newest"; then
  echo "ERROR iguana_backup_pull: $newest is not a valid gzip"
  exit 1
fi
find "$DEST/daily" -name 'iguana-*.sql.gz' -mtime +"$KEEP_DAILY" -delete
echo "OK $(date -Is) $newest ($(stat -c %s "$newest") bytes, ${age_h}h old); server says: $(cat "$DEST/LAST_OK" 2>/dev/null)"
