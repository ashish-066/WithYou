#!/usr/bin/env bash
# Deploy one release (image tag = commit SHA) on the app server, or roll back
# by deploying an earlier tag. Run as root from /opt/alex/release (the deploy
# workflow does this through SSM):
#
#   bash deploy.sh <image-tag>
#
# Steps: settings from SSM -> pull images -> migrate -> start services ->
# health checks + sandbox self-check -> new agent up, old agent drains.
# If a check fails, the previous release is started again and this exits 1.
# Migrations are not reversed, so they must stay compatible with the previous
# release (add columns first, remove them a release later).

set -euo pipefail
export PATH="$PATH:/snap/bin"

TAG="${1:?usage: deploy.sh <image-tag>}"
if ! [[ "$TAG" =~ ^[A-Za-z0-9._-]{1,128}$ ]]; then
  echo "invalid image tag: $TAG" >&2
  exit 2
fi
RELEASE_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="${ALEX_APP_DIR:-/opt/alex}"

# ENVIRONMENT AWS_REGION SSM_PREFIX REGISTRY DOMAIN SANDBOX_HOST (written at first boot).
# Optional overrides there: SANDBOX_RUNTIME (default runsc = gVisor; empty =
# Docker's default runtime), HTTP_PORT / HTTPS_PORT (default 80 / 443).
# shellcheck source=/dev/null
source "${ALEX_SETTINGS_FILE:-/etc/alex/env}"

log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }

# Everything written below holds secrets or is only for root
umask 077
cd "$APP_DIR"
cp "$RELEASE_DIR"/docker-compose.prod.yml "$RELEASE_DIR"/docker-compose.agent.yml "$RELEASE_DIR"/Caddyfile .
chmod 644 Caddyfile # read by the caddy container

# ---- settings ---------------------------------------------------------------------

fetch_env() { # one SSM folder -> KEY=value lines
  aws ssm get-parameters-by-path --region "$AWS_REGION" --path "$SSM_PREFIX/$1" \
    --with-decryption --query 'Parameters[].[Name,Value]' --output text |
    while IFS=$'\t' read -r name value; do printf '%s=%s\n' "${name##*/}" "$value"; done
}
for part in common avatar worker; do
  fetch_env "$part" >"$part.env.new"
  mv "$part.env.new" "$part.env"
done

mkdir -p sandbox-certs
for f in ca cert key; do
  # Capture, don't redirect: under SSM run-command the snap AWS CLI (2.35) exits 0 but
  # writes nothing when its stdout is a regular file, which left these files empty.
  pem="$(aws ssm get-parameter --region "$AWS_REGION" --name "$SSM_PREFIX/sandbox-client/$f" \
    --with-decryption --query Parameter.Value --output text)"
  [[ "$pem" == "-----BEGIN "* ]] || { echo "sandbox-client/$f from SSM is not a PEM file" >&2; exit 1; }
  printf '%s\n' "$pem" >"sandbox-certs/$f.pem"
done
chown -R 10001:10001 sandbox-certs # the worker's user
chmod 644 sandbox-certs/ca.pem sandbox-certs/cert.pem
chmod 600 sandbox-certs/key.pem

REDIS_PASSWORD="$(sed -n 's/^REDIS_PASSWORD=//p' common.env)"
PREVIOUS_TAG="$(cat current-tag 2>/dev/null || true)"

write_dotenv() { # compose variables for one tag
  cat >.env <<EOF
IMAGE_TAG=$1
REGISTRY=$REGISTRY
ENVIRONMENT=$ENVIRONMENT
DOMAIN=$DOMAIN
SANDBOX_HOST=$SANDBOX_HOST
SANDBOX_RUNTIME=${SANDBOX_RUNTIME-runsc}
HTTP_PORT=${HTTP_PORT:-80}
HTTPS_PORT=${HTTPS_PORT:-443}
REDIS_PASSWORD=$REDIS_PASSWORD
EOF
}

compose() { docker compose -f docker-compose.prod.yml "$@"; }
agent_compose() { docker compose -f docker-compose.agent.yml -p "alex-agent-${1:0:12}" "${@:2}"; }

wait_healthy() { # container names...; up to 3 minutes
  local deadline=$((SECONDS + 180)) c state
  for c in "$@"; do
    while true; do
      state="$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null || echo missing)"
      [ "$state" = healthy ] && break
      if [ $SECONDS -ge $deadline ]; then
        log "$c is $state"
        docker logs --tail 50 "$c" 2>&1 || true
        return 1
      fi
      sleep 3
    done
  done
}

check_release() {
  wait_healthy alex-api-1 alex-worker-1 alex-frontend-1 &&
    compose exec -T frontend wget -q -O - http://127.0.0.1:8080/api/ready &&
    echo &&
    compose exec -T worker python -m sandbox.selfcheck
}

start_release() {
  write_dotenv "$1"
  compose up -d --remove-orphans
}

# ---- deploy -------------------------------------------------------------------------

log "deploying $TAG to $ENVIRONMENT (previous: ${PREVIOUS_TAG:-none})"
aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$REGISTRY" >/dev/null

write_dotenv "$TAG"
compose pull --quiet
docker compose -f docker-compose.agent.yml pull --quiet

log "running migrations"
compose run --rm migrate

rollback() {
  if [ -n "$PREVIOUS_TAG" ] && [ "$PREVIOUS_TAG" != "$TAG" ]; then
    log "rolling back to $PREVIOUS_TAG"
    if start_release "$PREVIOUS_TAG" && check_release; then
      log "rolled back to $PREVIOUS_TAG"
    else
      log "previous release $PREVIOUS_TAG is unhealthy too: needs attention"
    fi
  else
    log "no previous release to roll back to"
  fi
}

log "starting services"
# `up` itself fails when a service never gets healthy, so treat that as a failed check
if ! { start_release "$TAG" && check_release; }; then
  log "checks failed for $TAG"
  rollback
  exit 1
fi

# ---- agent: start the new one, drain the old one ------------------------------------

log "starting agent for $TAG"
agent_compose "$TAG" up -d
if ! wait_healthy "alex-agent-${TAG:0:12}-agent-1"; then
  log "new agent is unhealthy; keeping the previous agent"
  agent_compose "$TAG" down --timeout 10 || true
  # Roll the rest back too, so agent and API stay on the same release
  rollback
  exit 1
fi

for project in $(docker compose ls -a --format json | python3 -c '
import json, sys
print("\n".join(p["Name"] for p in json.load(sys.stdin) if p["Name"].startswith("alex-agent-")))'); do
  [ "$project" = "alex-agent-${TAG:0:12}" ] && continue
  log "draining old agent $project (up to an hour, in the background)"
  drain=(docker compose -f "$APP_DIR/docker-compose.agent.yml" -p "$project" down --timeout 3630)
  if command -v systemd-run >/dev/null; then
    # A transient unit keeps going after this SSM command returns
    systemd-run --unit "drain-$project-$(date +%s)" --collect "${drain[@]}"
  else
    nohup "${drain[@]}" >"drain-$project.log" 2>&1 &
  fi
done

echo "$TAG" >current-tag
docker image prune -af --filter "until=168h" >/dev/null || true
log "deployed $TAG"
