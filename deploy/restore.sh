#!/usr/bin/env bash
# Restore SeedReflections from a backup file. Run as root:
#   /opt/seedreflections/deploy/restore.sh /var/backups/seedreflections/seedreflections-YYYYMMDD-HHMMSS.tar.gz
# The backup is checked, the current data is backed up and moved aside (never deleted), the backup is unpacked, and the
# app is started again. If anything fails part-way, the previous data is put back and the app is started on it.
set -euo pipefail
FILE="${1:?Usage: restore.sh /var/backups/seedreflections/<backup>.tar.gz}"
[ -f "$FILE" ] || { echo "No such file: $FILE"; exit 1; }
gzip -t "$FILE" || { echo "That file is not a valid .tar.gz."; exit 1; }
APP="${SEEDREFLECTIONS_APP:-/opt/seedreflections}"
cd "$APP"
COMPOSE="docker compose -f docker-compose.prod.yml"
ABS="$(readlink -f "$FILE")"

echo "==> Taking a safety backup of the current data first"
if ! "$APP/deploy/backup.sh"; then
  if [ "${RESTORE_WITHOUT_SAFETY_BACKUP:-0}" = 1 ]; then
    echo "!! The safety backup failed; continuing only because RESTORE_WITHOUT_SAFETY_BACKUP=1 was set."
  else
    echo "!! The safety backup of the current data failed, so nothing has been changed and the app is still running."
    echo "   Fix that first (disk space? app running?). To restore anyway, run again with RESTORE_WITHOUT_SAFETY_BACKUP=1."
    exit 1
  fi
fi

STOPPED=0; DONE=0
bring_back() {
  # If anything goes wrong after the app was stopped, start it again on whatever data is in place
  # (the restore undoes itself on failure, so that is the data from before).
  if [ "$STOPPED" = 1 ] && [ "$DONE" != 1 ]; then
    echo "!! The restore did not complete. Starting the app again on the data that is in place."
    $COMPOSE up -d seed-reflections || echo "!! The app could not be started: look at: $COMPOSE logs --tail 80"
  fi
}
trap bring_back EXIT

echo "==> Stopping the app"
$COMPOSE stop seed-reflections
STOPPED=1

echo "==> Restoring $ABS"
$COMPOSE run --rm --no-deps -v "$ABS:/restore/backup.tar.gz:ro" seed-reflections python deploy/restore_snapshot.py /restore/backup.tar.gz /data
DONE=1   # the data is restored; anything after this is about the app starting, not the restore

echo "==> Starting the app"
$COMPOSE up -d seed-reflections
for _ in $(seq 1 60); do
  if $COMPOSE exec -T seed-reflections python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8476/api/v2/health',timeout=3)" >/dev/null 2>&1; then
    echo "==> Restore complete and the app is healthy."
    echo "Check the data in the app. The previous data was kept in a .before-restore-* folder inside the data volume."
    exit 0
  fi
  sleep 2
done
echo "!! The app did not come back. Look at: $COMPOSE logs --tail 80"
echo "   The previous data is in a .before-restore-* folder in the data volume; it can be moved back."
exit 1
