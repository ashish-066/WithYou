# Backups and restore

## What needs backing up

| Store | Holds | Loss impact | Backup |
|---|---|---|---|
| **Postgres** | Organizations, users, invites, job roles, interview records and **final reports/scores**, consent records, audit log | Severe — customer data and results | Provider automated backups + point-in-time recovery (PITR), plus periodic logical dumps |
| **Redis** | Live interview state, message streams, locks, rate limits, ELO ratings, DSA problem library | Interviews in progress are disrupted; ended interviews are already in Postgres. ELO ratings and the DSA library would need rebuilding (re-seed problems) | Enable AOF persistence (`appendonly yes`, `appendfsync everysec`); provider snapshots if managed |
| **Object storage (S3)** | Interview recordings | Recordings lost | Bucket versioning + lifecycle rules; optionally cross-region replication |

## Production setup (checklist)

- [ ] Managed Postgres with **automated daily backups, ≥ 14 days retention, and PITR** enabled.
- [ ] A weekly logical dump (`scripts/backup_postgres.sh`) copied to a **different account/region**
      (protects against account compromise or provider-side deletion). Encrypt at rest.
- [ ] Redis with AOF persistence (or provider snapshots).
- [ ] S3 bucket: private, default encryption on, versioning on.
- [ ] **Restore drill every quarter** (below), result recorded in the launch log / runbook.

## Taking a backup

```bash
DATABASE_URL=postgresql://user:pass@host:5432/alex scripts/backup_postgres.sh backups/
```

Uses `pg_dump --format=custom` and verifies the archive is readable. Use client tools of the
**same major version** as the server (a newer `pg_dump`/`pg_restore` can write settings an
older server rejects).

## Restoring

1. Create an empty database (never restore over the live one):
   `CREATE DATABASE alex_restore;`
2. Restore, stopping on the first error:
   `pg_restore --no-owner --exit-on-error -d postgresql://.../alex_restore backups/alex-<time>.dump`
3. Check it: row counts of `interviews`, `users`, `invites`; `SELECT version_num FROM alembic_version`
   matches the code (`python -m alex_db.migrate` would upgrade it if older).
4. Point `DATABASE_URL` at the restored database (or rename databases during a maintenance
   window), restart the API and workers.
5. Ended interviews whose outcome is newer than the backup can be re-copied from Redis:
   `cd worker && uv run python -m scripts.backfill_outcomes`.

For managed PITR, restore to a new instance at the chosen timestamp, verify as in step 3,
then switch `DATABASE_URL`.

## Drill log

| Date | What | Result |
|---|---|---|
| 2026-10-31 | Local dev: dump of `alex` (Postgres 16 tools) → restore into `alex_restore_drill` with `--exit-on-error` → compare | ✅ 4/4 interviews, 4/4 reports, schema revision 0001 identical. Found: host `pg_dump` 18 output fails on a 16 server → documented the version rule. |
