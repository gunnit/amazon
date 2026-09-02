# Database backup and recovery

Everything the platform knows lives in a single Postgres database on Render. If you lose it, very little can be rebuilt from Amazon: the API windows are short and some historical series never come back. This page says what protects you today, how far it reaches, and what to do when it actually matters.

The figures below were verified against the production instance on **01/09/2026**.

## What exists today

The database is `inthezon-db`: Postgres 18, **Basic 256 MB** plan, **1 GB** disk, **Frankfurt** region. No high availability and no read replicas — there is one copy running.

The network is closed: the allowed-IP list is **empty**, so the database accepts no connections from outside Render. You reach it only from the inside (a one-off job on the API service) or through the Render dashboard. That is a good setting; do not widen it for convenience.

The real protection is **point-in-time recovery**. Render keeps it enabled on this plan and the window is roughly **7 rolling days**. At the time of the check it was available from 25/08/2026 onwards.

**Seven days is the whole safety net.** A deletion or corruption that nobody notices within a week is no longer recoverable. That is why the section on off-site copies exists.

## Restoring to a point in time

You do it from the Render dashboard, on the database → **Recovery**, picking a date and time.

Two things to know before pressing the button:

The restore does **not** overwrite the existing database: Render creates a new one. The old one stays until you delete it, which is a safeguard, but it also means the job is not finished when the restore is.

For the application to use the restored database you must update `DATABASE_URL` on the `inthezon-api` service with the new connection string and redeploy. Until you do, the app keeps reading and writing the old database.

After the deploy, check in this order: `/health` returns `ok`; the Alembic revision is the expected one; the table count and the row counts of the large tables (`sales_data`, `orders`) match the moment you picked.

One warning specific to this platform: on a restored database, `ALLOW_DESTRUCTIVE_RETENTION` must stay **unset**. The retention jobs delete data older than the configured window, and on freshly recovered history that is exactly how you lose it a second time.

## On-demand off-site copy

The 7-day window does not cover "we noticed late", and it does not cover losing access to the Render workspace at all. For that you need a copy that lives elsewhere.

Render's API export proved unreliable in testing: the request is accepted but produces no file. What works is `pg_dump` from a one-off job on the API service, which runs inside Render's network and therefore reaches the database without opening anything to the outside:

```python
import os, subprocess
url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
subprocess.run(["pg_dump", "-Fc", "-f", "/tmp/db.dump", url], check=True)
```

Measured on 01/09/2026: **6.9 MB** compressed, 140 tables, about 40 seconds. A file that size keeps anywhere without trouble.

You restore that file with `pg_restore` into an empty database. It is worth rehearsing once locally, while nothing is on fire: a copy that has never been restored is a hypothesis, not a backup.

## What has not been proven yet

Point-in-time recovery has **never been run** on this instance. The feature reports as available and the window is there, but the full drill — restore, repoint the API, verify the data — means creating a temporary paid instance and needs to be agreed first.

Until that drill has been done, treat recovery as a documented procedure, not a tested one.
