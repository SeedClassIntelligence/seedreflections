#!/usr/bin/env bash
# Restore SeedReflections from a backup file. Run as root:
#   /opt/seedreflections/deploy/restore.sh /var/backups/seedreflections/seedreflections-YYYYMMDD-HHMMSS.tar.gz
# The app is stopped, the backup is checked and unpacked, the current data is moved aside (not deleted), and the app is started again.
set -euo pipefail
FILE="${1:?Usage: restore.sh /var/backups/seedreflections/<backup>.tar.gz}"
[ -f "$FILE" ] || { echo "No such file: $FILE"; exit 1; }
gzip -t "$FILE" || { echo "That file is not a valid .tar.gz."; exit 1; }
APP=/opt/seedreflections
cd "$APP"
COMPOSE="docker compose -f docker-compose.prod.yml"
ABS="$(readlink -f "$FILE")"

echo "==> Taking a safety backup of the current data first"
"$APP/deploy/backup.sh" || echo "(no current backup could be taken; continuing because the data is moved aside, not deleted)"

echo "==> Stopping the app"
$COMPOSE stop seed-reflections

echo "==> Restoring $ABS"
$COMPOSE run --rm --no-deps -v "$ABS:/restore/backup.tar.gz:ro" seed-reflections python deploy/restore_snapshot.py /restore/backup.tar.gz /data

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
