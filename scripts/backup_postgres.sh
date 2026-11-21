#!/usr/bin/env bash
# Logical backup of the Alex Postgres database (custom format, compressed).
#
#   DATABASE_URL=postgresql://user:pass@host:5432/alex scripts/backup_postgres.sh [out_dir]
#
# Managed Postgres (RDS, Cloud SQL, Neon, Supabase...) should ALSO have its own
# automated backups + point-in-time recovery enabled; this script is for
# self-hosted setups and for extra off-site copies. See docs/BACKUPS.md.
#
# Use pg_dump/pg_restore of the SAME major version as the server: a newer
# client writes settings an older server rejects on restore (seen with
# pg_dump 18 against Postgres 16: "unrecognized configuration parameter
# transaction_timeout").
set -euo pipefail

: "${DATABASE_URL:?set DATABASE_URL}"
out_dir="${1:-backups}"
mkdir -p "$out_dir"
url="${DATABASE_URL/postgresql+asyncpg:/postgresql:}"
file="$out_dir/alex-$(date -u +%Y%m%dT%H%M%SZ).dump"

pg_dump --format=custom --no-owner --no-privileges --file="$file" "$url"
# Verify the archive is readable before trusting it
pg_restore --list "$file" > /dev/null
echo "backup written: $file ($(du -h "$file" | cut -f1))"
