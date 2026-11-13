#!/usr/bin/env bash
# Consistent backup of the SeedReflections data (databases plus uploaded source files) into /var/backups/seedreflections.
# Keeps 30 days. Run by cron every night and before each update.
set -euo pipefail
APP=/opt/seedreflections
OUT=/var/backups/seedreflections
mkdir -p "$OUT"; chmod 700 "$OUT"
FILE="$OUT/seedreflections-$(date +%Y%m%d-%H%M%S).tar.gz"
cd "$APP"
docker compose -f docker-compose.prod.yml exec -T seed-reflections python deploy/backup_snapshot.py /data > "$FILE.partial"
gzip -t "$FILE.partial"
mv "$FILE.partial" "$FILE"
find "$OUT" -name 'seedreflections-*.tar.gz' -mtime +30 -delete
echo "Backup written: $FILE ($(du -h "$FILE" | cut -f1))"
