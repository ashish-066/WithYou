#!/usr/bin/env bash
# Store the API keys an environment needs in SSM Parameter Store, reading
# them from env files (KEY=value lines). Only the names listed below are
# uploaded; anything else in the files is ignored. Values are never printed.
#
#   scripts/aws/put-secrets.sh <staging|production> <avatar-env-file> <worker-env-file>
#
# Use separate keys per environment (own LiveKit project etc.), e.g. files
# like ~/alex-secrets/staging-avatar.env — not your local development .env.
# Settings Terraform creates (database, Redis, auth secret, S3) are not touched.

set -euo pipefail

ENVIRONMENT="${1:?usage: put-secrets.sh <staging|production> <avatar-env-file> <worker-env-file>}"
AVATAR_FILE="${2:?avatar env file}"
WORKER_FILE="${3:?worker env file}"
REGION="${AWS_REGION:-ap-south-1}"

AVATAR_KEYS=(LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET BEY_API_KEY BEY_AVATAR_ID
  DEEPGRAM_API_KEY CARTESIA_API_KEY)
AVATAR_REQUIRED=(LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET BEY_API_KEY
  DEEPGRAM_API_KEY CARTESIA_API_KEY)
WORKER_KEYS=(GOOGLE_API_KEY OPENAI_API_KEY TAVILY_API_KEY HUME_API_KEY GITHUB_TOKEN
  PROXYCURL_API_KEY)
WORKER_REQUIRED=(GOOGLE_API_KEY)

value_of() { # last KEY=value in the file, surrounding quotes removed
  sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$2" | tail -n 1 |
    sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/"
}

upload() { # folder file required-keys... -- keys...
  local folder="$1" file="$2"
  shift 2
  local required=() keys=() seen_sep=0 key value
  for key in "$@"; do
    if [ "$key" = "--" ]; then seen_sep=1; continue; fi
    if [ $seen_sep = 0 ]; then required+=("$key"); else keys+=("$key"); fi
  done
  for key in "${required[@]}"; do
    [ -n "$(value_of "$key" "$file")" ] || { echo "$file: $key is required" >&2; exit 1; }
  done
  for key in "${keys[@]}"; do
    value="$(value_of "$key" "$file")"
    [ -n "$value" ] || continue
    aws ssm put-parameter --region "$REGION" --overwrite --type SecureString \
      --name "/alex/$ENVIRONMENT/$folder/$key" --value "$value" >/dev/null
    echo "  /alex/$ENVIRONMENT/$folder/$key"
  done
}

case "$ENVIRONMENT" in staging | production) ;; *)
  echo "environment must be staging or production" >&2
  exit 2
  ;;
esac

echo "Uploading to $REGION:"
upload avatar "$AVATAR_FILE" "${AVATAR_REQUIRED[@]}" -- "${AVATAR_KEYS[@]}"
upload worker "$WORKER_FILE" "${WORKER_REQUIRED[@]}" -- "${WORKER_KEYS[@]}"
echo "Done. Deploy (or redeploy the current tag) for services to pick them up."
