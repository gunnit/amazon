# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Inthezon** is a multi-tenant SaaS platform for managing multiple Amazon Seller/Vendor Central accounts with automated data extraction, analytics, and predictive insights. The platform is designed for account managers, data analysts, and strategists at Libera Brand Building Group.

## Architecture

The system follows a three-tier architecture deployed on Render.com:

```
Frontend (React/Vite)  ←→  Backend (FastAPI)  ←→  PostgreSQL
 Render Static Site          Render Web Service
                             └── APScheduler, in-process (21 jobs)
```

### Core Services
- **Frontend**: React 18 + TypeScript + Tailwind CSS + shadcn/ui (Render Static Site)
- **Backend**: Python 3.11 + FastAPI + SQLAlchemy 2.0 (Render Web Service)
- **Database**: PostgreSQL with time-series optimized schema
- **Scheduling**: APScheduler running inside the API process
  (`ENABLE_INPROCESS_SCHEDULER=true`)

**Not deployed, despite the code being present:** Celery workers, Celery beat,
Redis and S3/R2. The Celery task modules still exist and still work, but
nothing in `render.yaml` runs them — scheduling collapsed into the web service
deliberately. Consequences worth knowing: report artifacts are `LargeBinary`
columns in Postgres rather than object storage, catalog images are
unavailable, and the API must stay at a single instance. See
`frontend/src/content/docs/{it,en}/tech-architecture.md`.

### External Integrations
- Amazon SP-API (Seller Central)
- Amazon Vendor Central API
- Amazon Advertising API
- Anthropic API for AI narratives (degrades to templates without credit)
- SendGrid for email notifications — **no verified sender, so no email is
  delivered today**: password resets, scheduled reports, alerts and digests
  all depend on it

## Project Structure

```
inthezon-platform/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Settings management
│   │   ├── api/v1/              # API endpoints
│   │   ├── core/amazon/         # Amazon API clients (SP-API, Vendor, Ads)
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── services/            # Business logic
│   │   └── db/                  # Database session and migrations
│   └── workers/
│       ├── celery_app.py        # Celery configuration
│       └── tasks/               # Background tasks
├── frontend/
│   ├── src/
│   │   ├── components/          # React components (incl. shadcn/ui)
│   │   ├── pages/               # Page components
│   │   ├── hooks/               # Custom React hooks
│   │   ├── services/api.ts      # API client
│   │   └── store/               # Zustand state management
│   └── vite.config.ts
└── render.yaml                  # Render deployment blueprint
```

## Development Commands

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head                    # Run migrations
uvicorn app.main:app --reload           # Start dev server
```

### Frontend
```bash
cd frontend
npm install
npm run dev                             # Start dev server
npm run build                           # Production build
```

### Workers
```bash
cd backend
celery -A workers.celery_app worker --loglevel=info     # Run worker
celery -A workers.celery_app beat --loglevel=info       # Run scheduler
```

### Docker (Local Development)
```bash
docker-compose up -d
```

## Key Technical Decisions

### Database Schema
- Time-series data (sales, inventory, ads) uses date-partitioned tables with composite indexes on `(account_id, date)`
- Amazon credentials stored encrypted using Fernet symmetric encryption
- JSONB used for flexible forecast predictions storage
- Views provided for common aggregations (e.g., `v_account_summary`)

### Authentication
- JWT with short-lived access tokens (30 min) + refresh token rotation
- bcrypt for password hashing (12 rounds)

### Amazon API Integration
- All three Amazon APIs (SP-API, Vendor Central, Advertising) require separate credential sets
- OAuth refresh tokens stored encrypted and auto-refreshed
- Rate limiting implemented to stay within SP-API limits

### State Management
- Frontend uses Zustand for global state
- Redis for server-side session caching and rate limiting

## Deployment

Deployment is on Render.com using the `render.yaml` blueprint:
- Auto-deploy enabled on main branch push to GitHub
- Backend requires environment variables for Amazon APIs and the database;
  `REDIS_URL`/`CELERY_BROKER_URL` are deliberately empty and `SENTRY_DSN`
  is the only working out-of-band alert channel. See `tech-config.md`.
- Frontend served as static site with API calls to backend service

## Gotchas that cost time

- **`frontend/src/content/docs/*/tech-api.md` is generated.** After adding,
  removing or renaming a route, regenerate it with
  `python backend/scripts/gen_tech_docs.py`, or the in-app API reference
  silently drifts from reality.
- **The in-app docs are authoritative, not the root markdown.**
  `TECHNICAL_ARCHITECTURE.md` and `DEVELOPMENT_PLAN.md` describe an
  architecture that was never deployed (Celery, Redis, S3). What actually runs
  is in `frontend/src/content/docs/{it,en}/tech-architecture.md`.
- **Production runs no Celery worker.** Scheduled work happens in-process in
  the API service (`ENABLE_INPROCESS_SCHEDULER=true`), which is why
  `render.yaml` pins `numInstances: 1` — a second instance runs every job
  twice.
- **Never start `celery beat`** against a production or restored database. It
  schedules retention tasks that delete history Amazon will not serve again.
  They refuse to run without `ALLOW_DESTRUCTIVE_RETENTION=true`.
- **`pytest tests/` must stay green in a single process.** `tests/conftest.py`
  undoes the `sys.modules` stubbing that individual test modules do; without
  it the result depends on file order.
- **Registration is closed.** The first admin on an empty database comes from
  `backend/scripts/create_admin.py`; everyone else from an admin-issued invite
  link, because email delivery is unavailable.

## QA Validation

After deployments, use the `playwright-qa-validator` agent to run comprehensive automated tests:
- Functional correctness
- UI/UX quality
- Error handling
- Console errors/warnings
- API integration verification
