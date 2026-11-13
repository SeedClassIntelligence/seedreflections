#!/usr/bin/env bash
# Bring the server up to date with GitHub. Run as root:  /opt/seedreflections/deploy/update.sh [branch]
# It takes a backup first, rebuilds, checks health, and rolls back to the previous version if the new one does not start.
set -euo pipefail
APP=/opt/seedreflections
cd "$APP"
BRANCH="${1:-$(git rev-parse --abbrev-ref HEAD)}"
COMPOSE="docker compose -f docker-compose.prod.yml"
PREVIOUS="$(git rev-parse HEAD)"

echo "==> Backup before updating"
"$APP/deploy/backup.sh"

echo "==> Fetching $BRANCH"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git merge --ff-only "origin/$BRANCH"
NEW="$(git rev-parse HEAD)"
if [ "$NEW" = "$PREVIOUS" ]; then echo "Already up to date ($NEW)."; fi

healthy() {
  for _ in $(seq 1 60); do
    if $COMPOSE exec -T seed-reflections python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8476/api/v2/health',timeout=3)" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  return 1
}

echo "==> Rebuilding and restarting"
$COMPOSE up -d --build
if healthy; then
  echo "==> Running now: $NEW"
  DOMAIN="$(grep -E '^SEED_REFLECTIONS_DOMAIN=' .env | cut -d= -f2-)"
  echo "==> Readiness: $(curl -s "https://$DOMAIN/api/v2/readiness" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("ready" if d.get("ready") else "NOT READY: "+", ".join(c["name"] for c in d["checks"] if not c["passed"]))' 2>/dev/null || echo "could not read (is DNS pointing here yet?)")"
else
  echo "!! The new version did not start. Rolling back to $PREVIOUS"
  git checkout --detach "$PREVIOUS"
  $COMPOSE up -d --build
  healthy && echo "Rolled back. The site is running the previous version." || echo "Rollback did not start either: run '$COMPOSE logs --tail 80'."
  exit 1
fi
