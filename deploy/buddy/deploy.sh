#!/usr/bin/env bash
# Deploy the study buddy to one Ubuntu server from this machine.
#
#   deploy/buddy/deploy.sh <server-ip> [ssh-key]
#
# Sends the committed code (git archive, nothing untracked) plus avatar/.env and
# worker/.env over SSH, installs Docker on first run, writes production settings
# (random DB/Redis passwords and auth secret, kept across deploys), then builds
# and starts everything. The app is at https://<ip>.sslip.io.
set -euo pipefail
IP="${1:?usage: deploy.sh <server-ip> [ssh-key]}"
KEY="${2:-$HOME/.ssh/study_buddy}"
DOMAIN="$IP.sslip.io"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "ubuntu@$IP")
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo "==> code ($(git rev-parse --short HEAD))"
git archive --format=tar HEAD | "${SSH[@]}" 'mkdir -p ~/buddy && tar -x -C ~/buddy'
echo "==> secrets"
scp -q -i "$KEY" avatar/.env "ubuntu@$IP:buddy/avatar/.env"
scp -q -i "$KEY" worker/.env "ubuntu@$IP:buddy/worker/.env"

"${SSH[@]}" DOMAIN="$DOMAIN" bash -s <<'REMOTE'
set -euo pipefail
cd ~/buddy
if ! command -v docker >/dev/null; then
  echo "==> installing docker"
  curl -fsSL https://get.docker.com | sudo sh >/dev/null
  sudo usermod -aG docker ubuntu
fi
if [ ! -f .env ]; then
  echo "==> production settings"
  umask 077
  {
    echo "DOMAIN=$DOMAIN"
    echo "ENVIRONMENT=production"
    echo "REDIS_PASSWORD=$(openssl rand -hex 24)"
    echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
    echo "AUTH_SECRET=$(openssl rand -hex 32)"
  } > .env
fi
# The API reads AUTH_SECRET from its env file
grep -q '^AUTH_SECRET=' avatar/.env || grep '^AUTH_SECRET=' .env >> avatar/.env
chmod 600 .env avatar/.env worker/.env
echo "==> build + start"
sudo docker compose -f docker-compose.yml -f deploy/buddy/compose.yml up -d --build --remove-orphans
sudo docker compose -f docker-compose.yml -f deploy/buddy/compose.yml ps --format 'table {{.Service}}\t{{.Status}}'
REMOTE
echo "==> https://$DOMAIN"
