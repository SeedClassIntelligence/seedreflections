#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 22.04/24.04 server for SeedReflections (Docker + Caddy, automatic HTTPS).
# Run as root:  bash setup-server.sh app.yourdomain.com [repo-url] [branch]
# Safe to run again: it never overwrites an existing .env.
set -euo pipefail

DOMAIN="${1:?Usage: bash setup-server.sh app.yourdomain.com [repo-url] [branch]}"
REPO="${2:-git@github.com:SeedClassIntelligence/seedreflections.git}"
BRANCH="${3:-main}"
APP=/opt/seedreflections

[ "$(id -u)" -eq 0 ] || { echo "Run this as root (sudo -i)."; exit 1; }
echo "$DOMAIN" | grep -Eq '^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$' || { echo "'$DOMAIN' does not look like a domain name."; exit 1; }

echo "==> Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl git ufw cron openssl gnupg

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker"
  install -m 0755 -d /etc/apt/keyrings
  . /etc/os-release
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

echo "==> Firewall: only SSH, HTTP and HTTPS are open"
ufw allow OpenSSH >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

if [ ! -d "$APP/.git" ]; then
  case "$REPO" in
    git@*|ssh://*)
      KEY=/root/.ssh/seedreflections_deploy
      if [ ! -f "$KEY" ]; then
        mkdir -p /root/.ssh; chmod 700 /root/.ssh
        ssh-keygen -t ed25519 -N "" -C "seedreflections-server" -f "$KEY" >/dev/null
        printf 'Host github.com\n  IdentityFile %s\n  IdentitiesOnly yes\n  StrictHostKeyChecking accept-new\n' "$KEY" >> /root/.ssh/config
        chmod 600 /root/.ssh/config
      fi
      if ! GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" git ls-remote "$REPO" >/dev/null 2>&1; then
        echo
        echo "The server cannot read the repository yet. In GitHub open the repository, then"
        echo "Settings > Deploy keys > Add deploy key, paste this (leave 'Allow write access' OFF), then run this script again:"
        echo
        cat "$KEY.pub"
        exit 0
      fi;;
  esac
  echo "==> Downloading the code ($BRANCH)"
  git clone --branch "$BRANCH" "$REPO" "$APP"
fi

cd "$APP"
if [ ! -f .env ]; then
  echo "==> Creating .env with generated secrets"
  ADMIN_PW="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)"
  MASTER="$(openssl rand 32 | base64 | tr '+/' '-_')"
  umask 077
  cat > .env <<ENV
SEED_REFLECTIONS_DOMAIN=$DOMAIN
ADMIN_PASSWORD=$ADMIN_PW
SEED_REFLECTIONS_CREDENTIAL_MASTER_KEY=$MASTER
# Outgoing email for password reset (required). Fill these in, then run deploy/update.sh or restart the app.
SEED_REFLECTIONS_SMTP_HOST=
SEED_REFLECTIONS_SMTP_PORT=465
SEED_REFLECTIONS_SMTP_SECURITY=ssl
SEED_REFLECTIONS_SMTP_USER=
SEED_REFLECTIONS_SMTP_PASSWORD=
SEED_REFLECTIONS_SMTP_FROM=SeedReflections <noreply@${DOMAIN#*.}>
# Add later, only when you are ready: Google Drive and billing.
SEED_REFLECTIONS_GOOGLE_CLIENT_ID=
SEED_REFLECTIONS_GOOGLE_CLIENT_SECRET=
ENV
  chmod 600 .env
  NEW_ENV=1
fi

echo "==> Daily backup at 03:15 (kept 30 days)"
mkdir -p /var/backups/seedreflections
( crontab -l 2>/dev/null | grep -v 'seedreflections/deploy/backup.sh' ; echo "15 3 * * * $APP/deploy/backup.sh >> /var/log/seedreflections-backup.log 2>&1" ) | crontab -

echo "==> Starting SeedReflections"
docker compose -f docker-compose.prod.yml up -d --build

echo "==> Waiting for the app to answer"
for _ in $(seq 1 60); do
  if docker compose -f docker-compose.prod.yml exec -T seed-reflections python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8476/api/v2/health',timeout=3)" >/dev/null 2>&1; then OK=1; break; fi
  sleep 2
done
[ "${OK:-0}" = 1 ] || { echo "The app did not start. Look at: docker compose -f docker-compose.prod.yml logs --tail 80"; exit 1; }

echo
echo "Done. Next:"
echo "  1. Make sure the DNS record for $DOMAIN points to this server's IP address."
echo "  2. Open https://$DOMAIN (the certificate is fetched automatically; allow a minute)."
echo "  3. Fill in the SMTP_ lines in $APP/.env (a mailbox for password-reset email), then: cd $APP && docker compose -f docker-compose.prod.yml up -d"
echo "  4. Readiness check:  curl -s https://$DOMAIN/api/v2/readiness   (every check must pass)"
if [ "${NEW_ENV:-0}" = 1 ]; then
  echo
  echo "Your generated secrets are in $APP/.env (readable only by root). Save a copy of that file somewhere safe."
  echo "If the master key is lost, stored model keys and Google tokens can no longer be decrypted."
fi
