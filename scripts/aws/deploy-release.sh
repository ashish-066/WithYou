#!/usr/bin/env bash
# Deploy one image tag to an environment from CI (or a laptop with AWS access):
#
#   scripts/aws/deploy-release.sh <staging|production> <image-tag>
#
# Uploads deploy/ to the environment's ops bucket, runs deploy.sh on the app
# server through SSM Run Command (no SSH), waits, and prints the server's
# output. Exits non-zero if the deploy failed (deploy.sh then rolled back).
# Rollback = run this with an earlier tag.

set -euo pipefail

ENVIRONMENT="${1:?usage: deploy-release.sh <staging|production> <image-tag>}"
TAG="${2:?usage: deploy-release.sh <staging|production> <image-tag>}"
REGION="${AWS_REGION:-ap-south-1}"
PREFIX="/alex/$ENVIRONMENT/deploy"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

case "$ENVIRONMENT" in staging | production) ;; *)
  echo "environment must be staging or production" >&2
  exit 2
  ;;
esac
if ! [[ "$TAG" =~ ^[A-Za-z0-9._-]{1,128}$ ]]; then
  echo "invalid image tag: $TAG" >&2
  exit 2
fi

param() { aws ssm get-parameter --region "$REGION" --name "$PREFIX/$1" --query Parameter.Value --output text; }
INSTANCE_ID="$(param instance-id)"
BUCKET="$(param ops-bucket)"
REGISTRY="$(param registry)"

# Refuse to deploy a tag whose images were never built
for image in api agent worker frontend; do
  aws ecr describe-images --region "$REGION" --repository-name "alex-$image" \
    --image-ids imageTag="$TAG" >/dev/null ||
    { echo "image $REGISTRY/alex-$image:$TAG not found" >&2; exit 1; }
done

RELEASE="s3://$BUCKET/releases/$TAG"
aws s3 sync --region "$REGION" --delete "$ROOT/deploy/" "$RELEASE/"

COMMANDS="$(python3 - "$RELEASE" "$TAG" <<'PY'
import json, shlex, sys
release, tag = sys.argv[1], sys.argv[2]
print(json.dumps({"commands": [
    "set -eu",  # SSM runs these with /bin/sh (dash): no pipefail, and none of them pipe
    "export PATH=$PATH:/snap/bin",
    f"aws s3 sync --delete {shlex.quote(release)}/ /opt/alex/release/",
    f"bash /opt/alex/release/deploy.sh {shlex.quote(tag)}",
]}))
PY
)"

COMMAND_ID="$(aws ssm send-command --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "deploy $TAG" \
  --timeout-seconds 600 \
  --parameters "$COMMANDS" \
  --query Command.CommandId --output text)"
echo "deploying $TAG to $ENVIRONMENT ($INSTANCE_ID), command $COMMAND_ID"

status=Pending
for _ in $(seq 1 240); do # up to 20 minutes
  sleep 5
  status="$(aws ssm get-command-invocation --region "$REGION" --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" --query Status --output text 2>/dev/null || echo Pending)"
  case "$status" in Pending | InProgress | Delayed) ;; *) break ;; esac
done

aws ssm get-command-invocation --region "$REGION" --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" --query '[StandardOutputContent,StandardErrorContent]' --output text || true
echo "status: $status"
[ "$status" = Success ]
