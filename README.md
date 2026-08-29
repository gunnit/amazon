# Inthezon

Multi-tenant platform for managing Amazon Seller and Vendor Central accounts:
automated data extraction, analytics, forecasting and reporting.

## Where the real documentation lives

The authoritative documentation is **inside the application**, at `/docs` once
it is running, and in the repository at `frontend/src/content/docs/{it,en}/`.
It is written for the people who operate and maintain the system, and it is
kept in sync with the running code:

| Page | What it answers |
|---|---|
| `tech-architecture.md` | What actually runs in production, and what does not |
| `tech-config.md` | Every environment variable and what breaks without it |
| `tech-data-model.md` | The schema and the metric invariants |
| `tech-scheduler.md` | The scheduled jobs, their cadence and where they run |
| `tech-api.md` | Every endpoint — **generated**, see below |
| `connect-account.md` | Connecting an Amazon account |
| `secret-rotation.md` | Rotating the Amazon client secret (needed every 180 days) |
| `account-errors.md` | Reading sync errors: configuration vs Amazon vs product bug |
| `manage-users.md` | Creating users and issuing invite links |
| `email-reports.md` | Scheduled reports and the state of email delivery |
| `known-limits.md` | What the product deliberately does not do |

`TECHNICAL_ARCHITECTURE.md` and `DEVELOPMENT_PLAN.md` in this directory are
historical design documents. Where they disagree with the pages above, the
pages above are right.

## Running it locally

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env      # then fill it in — see tech-config.md
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Registration is closed by design, so a fresh database has no way in. Create the
first organization and administrator with:

```bash
cd backend
python scripts/create_admin.py --email you@example.com --org "Your Company"
```

Everyone after that is created from **Impostazioni → Utenti** by an
administrator, who copies the generated invite link and sends it over chat —
email delivery is not currently available. See `manage-users.md`.

## Deployment

`render.yaml` is the blueprint: one web service for the API, one static site
for the frontend, one Postgres database. Pushing to `master` auto-deploys.
There is **no** Celery worker, no Redis and no S3 in production — scheduled
work runs in-process inside the API service. `tech-architecture.md` explains
why and what that costs.

## Things that will bite you

- **Never run `celery beat`** against a production or restored database. It
  schedules data-retention tasks that delete history Amazon will not serve
  again. They refuse to run unless `ALLOW_DESTRUCTIVE_RETENTION=true`; leave
  it unset.
- **`tech-api.md` is generated.** After changing any route, regenerate it with
  `python backend/scripts/gen_tech_docs.py`.
- **The Amazon client secret expires every 180 days** and the failure is
  silent from Amazon's side. `secret-rotation.md` covers the symptoms and the
  fix; the app shows a banner when it detects it.
- **Credentials are never committed.** Everything sensitive comes from the
  environment; the QA specs read `QA_EMAIL` / `QA_PASSWORD`.
