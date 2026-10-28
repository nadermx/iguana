#!/bin/bash
# Nightly database backup for Iguana Comedy, installed by deploy.yml, run by /etc/cron.d/iguana-backup as root.
#
# Dump, then PROVE the dump restores, then prune. A backup that has never been restored is a hope, so every
# night the fresh dump is loaded into a scratch database and its row counts are checked against the live ones
# before anything old is deleted. If any step fails, nothing is pruned and an email goes out.
#
#   daily/   every night, kept KEEP_DAILY days
#   weekly/  Sunday's dump, kept KEEP_WEEKLY days
#   media/   Sunday tarball of backend/media (uploaded posters), kept KEEP_MEDIA days
#   agent/   nightly tarball of the /chat/ agent's Claude Code sessions, kept KEEP_DAILY days. The transcript is
#            in the database, but the agent resumes a conversation from these files, so without them a
#            restored server shows old conversations it can no longer continue.
#
# The dev box pulls this directory every night (ansible/files/pull-iguana-backups.sh), because a backup that
# lives on the same disk as the database dies with it.
# No -E: an ERR trap inherited into $(...) subshells fires there, the subshell exits, and the script
# carries on to fail a second time. Without it the failed substitution trips the trap once, in the main shell.
set -euo pipefail

DB=iguana
DIR=/var/backups/iguana
MEDIA=/home/www/iguana/backend/media
AGENT_SESSIONS=/home/claude/.claude/projects
KEEP_DAILY=30
KEEP_WEEKLY=182
KEEP_MEDIA=56
ALERT_TO=${IGUANA_BACKUP_ALERT:-john@iguanacomedy.com}
SCRATCH=iguana_restore_test
# Tables whose loss would hurt; each must come back with at least as many rows as the live table had just
# before the dump (rows only ever get added between the count and the dump, never the other way).
TABLES=(catalog_event catalog_tickettype sales_order sales_orderitem sales_ticket crm_contact catalog_formsubmission
        assistant_conversation assistant_turn)

ts=$(date -u +%Y%m%dT%H%M%SZ)
log() { logger -t iguana-backup "$*"; echo "$*"; }
fail() {
  logger -t iguana-backup -p user.err "FAILED: $*"
  printf 'Subject: [iguana] database backup FAILED\nFrom: "Iguana Comedy" <no-reply@iguanacomedy.com>\nTo: %s\n\n%s\n\nHost %s, run %s. Nothing was pruned. journalctl -t iguana-backup\n' \
    "$ALERT_TO" "$*" "$(hostname)" "$ts" | /usr/sbin/sendmail -f no-reply@iguanacomedy.com "$ALERT_TO" || true
  sudo -u postgres dropdb --if-exists "$SCRATCH" >/dev/null 2>&1 || true
  exit 1
}
trap 'fail "step at line $LINENO exited non-zero"' ERR
q() { sudo -u postgres psql -Atq -d "$1" -c "$2"; }

install -d -m 0750 -o root -g iguana "$DIR" "$DIR/daily" "$DIR/weekly" "$DIR/media" "$DIR/agent"

declare -A live
for t in "${TABLES[@]}"; do live[$t]=$(q "$DB" "select count(*) from $t") || fail "could not count $t in $DB"; done

out="$DIR/daily/iguana-$ts.sql.gz"
sudo -u postgres pg_dump --no-owner --no-acl "$DB" | gzip -9 > "$out.part"
mv "$out.part" "$out"
chown root:iguana "$out"; chmod 0640 "$out"
gzip -t "$out"

# The restore test.
sudo -u postgres dropdb --if-exists "$SCRATCH"
sudo -u postgres createdb "$SCRATCH"
gunzip -c "$out" | sudo -u postgres psql -q -v ON_ERROR_STOP=1 -d "$SCRATCH" >/dev/null
summary=()
for t in "${TABLES[@]}"; do
  got=$(q "$SCRATCH" "select count(*) from $t")
  if [ "$got" -lt "${live[$t]}" ]; then fail "restore check: $t has $got rows, live had ${live[$t]}"; fi
  summary+=("$t=$got")
done
[ "${live[catalog_event]}" -gt 0 ] || fail "restore check: catalog_event is empty, which is never true here"
sudo -u postgres dropdb "$SCRATCH"

if [ "$(date -u +%u)" = 7 ]; then
  cp -p "$out" "$DIR/weekly/"
  tar -czf "$DIR/media/media-$ts.tar.gz.part" -C "$(dirname "$MEDIA")" "$(basename "$MEDIA")"
  mv "$DIR/media/media-$ts.tar.gz.part" "$DIR/media/media-$ts.tar.gz"
  chown root:iguana "$DIR/media/media-$ts.tar.gz"; chmod 0640 "$DIR/media/media-$ts.tar.gz"
fi

if [ -d "$AGENT_SESSIONS" ]; then
  tar -czf "$DIR/agent/agent-$ts.tar.gz.part" -C "$(dirname "$AGENT_SESSIONS")" "$(basename "$AGENT_SESSIONS")"
  mv "$DIR/agent/agent-$ts.tar.gz.part" "$DIR/agent/agent-$ts.tar.gz"
  chown root:iguana "$DIR/agent/agent-$ts.tar.gz"; chmod 0640 "$DIR/agent/agent-$ts.tar.gz"
fi

# Prune only now that tonight's copy is proven.
find "$DIR/daily" -name 'iguana-*.sql.gz' -mtime +"$KEEP_DAILY" -delete
find "$DIR/weekly" -name 'iguana-*.sql.gz' -mtime +"$KEEP_WEEKLY" -delete
find "$DIR/media" -name 'media-*.tar.gz' -mtime +"$KEEP_MEDIA" -delete
find "$DIR/agent" -name 'agent-*.tar.gz' -mtime +"$KEEP_DAILY" -delete
find "$DIR" -name '*.part' -mmin +120 -delete

echo "$ts $(stat -c %s "$out") bytes, restored ${summary[*]}" > "$DIR/LAST_OK"
chown root:iguana "$DIR/LAST_OK"; chmod 0640 "$DIR/LAST_OK"
log "OK $out ($(stat -c %s "$out") bytes) restored and verified: ${summary[*]}"
