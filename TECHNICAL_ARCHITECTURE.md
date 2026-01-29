# Inthezon Amazon Platform - Technical Architecture

## System Overview

A multi-tenant SaaS platform for managing multiple Amazon Seller/Vendor Central accounts with automated data extraction, analytics, and predictive insights.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              INTHEZON PLATFORM                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │   Frontend   │    │   Backend    │    │   Workers    │                   │
│  │   (React)    │◄──►│  (FastAPI)   │◄──►│   (Celery)   │                   │
│  │   Render     │    │   Render     │    │   Render     │                   │
│  │   Static     │    │   Web Svc    │    │   Background │                   │
│  └──────────────┘    └──────┬───────┘    └──────┬───────┘                   │
│                             │                    │                           │
│         ┌───────────────────┼────────────────────┤                           │
│         │                   │                    │                           │
│         ▼                   ▼                    ▼                           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │  PostgreSQL  │    │    Redis     │    │  Amazon S3   │                   │
│  │   Render     │    │   Render     │    │   (Reports)  │                   │
│  │   Managed    │    │   Managed    │    │              │                   │
│  └──────────────┘    └──────────────┘    └──────────────┘                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
              ┌─────────────────────────────────────────┐
              │           EXTERNAL SERVICES             │
              ├─────────────────────────────────────────┤
              │  • Amazon SP-API (Seller Central)       │
              │  • Amazon Vendor Central API            │
              │  • Amazon Advertising API               │
              │  • SendGrid (Email notifications)       │
              └─────────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Frontend** | React 18 + TypeScript | Modern, component-based UI |
| **UI Framework** | Tailwind CSS + shadcn/ui | Rapid styling, professional look |
| **Charts** | Recharts / Plotly | Time-series visualization |
| **Backend** | Python 3.11 + FastAPI | Async support, excellent for APIs |
| **ORM** | SQLAlchemy 2.0 | Mature, async support |
| **Task Queue** | Celery + Redis | Reliable background jobs |
| **Database** | PostgreSQL 15 | Time-series, JSON support |
| **Cache** | Redis | Session, rate limiting, queues |
| **ML/Analytics** | pandas, scikit-learn, Prophet | Forecasting capabilities |
| **File Storage** | AWS S3 / Cloudflare R2 | Report storage |
| **Auth** | JWT + OAuth2 | Secure, stateless |
| **Hosting** | Render | Simple deployment, managed services |

---

## Render Services Architecture

```yaml
Services Required:
├── Web Service (Backend API)
│   ├── Type: Python
│   ├── Plan: Starter ($7/mo) or Standard ($25/mo)
│   └── Auto-deploy from GitHub
│
├── Static Site (Frontend)
│   ├── Type: Static
│   ├── Plan: Free or Starter
│   └── Build: npm run build
│
├── Background Worker
│   ├── Type: Background Worker
│   ├── Plan: Starter ($7/mo)
│   └── Runs Celery workers
│
├── Cron Job (Scheduler)
│   ├── Type: Cron Job
│   ├── Schedule: Various (hourly, daily)
│   └── Triggers data extraction
│
├── PostgreSQL Database
│   ├── Plan: Starter ($7/mo) or Standard ($20/mo)
│   └── 1GB - 25GB storage
│
└── Redis
    ├── Plan: Starter ($10/mo)
    └── For Celery + caching
```

**Estimated Monthly Cost:** $40-80/month (starter tier)

---

## Project Structure

```
inthezon-platform/
├── render.yaml                 # Render Blueprint (IaC)
├── docker-compose.yml          # Local development
├── .env.example                # Environment template
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI app entry
│   │   ├── config.py           # Settings management
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py         # Dependencies (auth, db)
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── router.py   # Main router
│   │   │       ├── auth.py     # Authentication endpoints
│   │   │       ├── accounts.py # Amazon account management
│   │   │       ├── reports.py  # Data extraction & reports
│   │   │       ├── analytics.py# KPIs & dashboards
│   │   │       ├── catalog.py  # Product management
│   │   │       ├── forecasts.py# Predictive analytics
│   │   │       └── exports.py  # Excel/PPT generation
│   │   │
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── security.py     # JWT, password hashing
│   │   │   ├── amazon/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── sp_api.py   # Seller Central API client
│   │   │   │   ├── vendor_api.py # Vendor Central client
│   │   │   │   └── advertising_api.py
│   │   │   └── exceptions.py
│   │   │
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── amazon_account.py
│   │   │   ├── sales_data.py
│   │   │   ├── inventory.py
│   │   │   ├── advertising.py
│   │   │   ├── product.py
│   │   │   └── competitor.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── account.py
│   │   │   ├── report.py
│   │   │   └── analytics.py
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── data_extraction.py
│   │   │   ├── analytics_service.py
│   │   │   ├── forecast_service.py
│   │   │   ├── export_service.py
│   │   │   └── notification_service.py
│   │   │
│   │   └── db/
│   │       ├── __init__.py
│   │       ├── session.py
│   │       └── migrations/     # Alembic migrations
│   │
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── celery_app.py       # Celery configuration
│   │   └── tasks/
│   │       ├── __init__.py
│   │       ├── extraction.py   # Data extraction tasks
│   │       ├── forecasting.py  # ML prediction tasks
│   │       └── notifications.py
│   │
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic.ini
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ui/             # shadcn components
│   │   │   ├── Dashboard/
│   │   │   ├── Accounts/
│   │   │   ├── Reports/
│   │   │   ├── Analytics/
│   │   │   └── Catalog/
│   │   │
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Accounts.tsx
│   │   │   ├── Reports.tsx
│   │   │   ├── Analytics.tsx
│   │   │   ├── Forecasts.tsx
│   │   │   └── Settings.tsx
│   │   │
│   │   ├── hooks/
│   │   ├── services/
│   │   │   └── api.ts          # API client
│   │   ├── store/              # Zustand state
│   │   ├── types/
│   │   └── utils/
│   │
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
│
└── docs/
    ├── TECHNICAL_ARCHITECTURE.md
    ├── API.md
    └── DEPLOYMENT.md
```

---

## Database Schema

```sql
-- Core Tables

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    is_superuser BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE organization_members (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'member', -- admin, member, viewer
    PRIMARY KEY (user_id, organization_id)
);

-- Amazon Account Management

CREATE TABLE amazon_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    account_name VARCHAR(255) NOT NULL,
    account_type VARCHAR(20) NOT NULL, -- 'seller' or 'vendor'
    marketplace_id VARCHAR(20) NOT NULL, -- e.g., 'A1PA6795UKMFR9' for IT
    marketplace_country VARCHAR(10) NOT NULL, -- e.g., 'IT', 'DE', 'FR'
    
    -- SP-API Credentials (encrypted)
    refresh_token_encrypted TEXT,
    client_id_encrypted TEXT,
    client_secret_encrypted TEXT,
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    sync_status VARCHAR(50) DEFAULT 'pending', -- pending, syncing, success, error
    sync_error_message TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_amazon_accounts_org ON amazon_accounts(organization_id);

-- Sales Data (Time-series)

CREATE TABLE sales_data (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID REFERENCES amazon_accounts(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    asin VARCHAR(20) NOT NULL,
    sku VARCHAR(100),
    
    -- Metrics
    units_ordered INTEGER DEFAULT 0,
    units_ordered_b2b INTEGER DEFAULT 0,
    ordered_product_sales DECIMAL(12,2) DEFAULT 0,
    ordered_product_sales_b2b DECIMAL(12,2) DEFAULT 0,
    total_order_items INTEGER DEFAULT 0,
    
    -- Currency
    currency VARCHAR(3) DEFAULT 'EUR',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(account_id, date, asin)
);

-- Partitioning by month for performance
CREATE INDEX idx_sales_data_account_date ON sales_data(account_id, date DESC);
CREATE INDEX idx_sales_data_asin ON sales_data(asin);

-- Inventory Data

CREATE TABLE inventory_data (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID REFERENCES amazon_accounts(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    asin VARCHAR(20) NOT NULL,
    sku VARCHAR(100),
    fnsku VARCHAR(20),
    
    -- Stock Levels
    afn_fulfillable_quantity INTEGER DEFAULT 0,
    afn_inbound_working_quantity INTEGER DEFAULT 0,
    afn_inbound_shipped_quantity INTEGER DEFAULT 0,
    afn_reserved_quantity INTEGER DEFAULT 0,
    afn_total_quantity INTEGER DEFAULT 0,
    
    -- MFN (Merchant Fulfilled)
    mfn_fulfillable_quantity INTEGER DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(account_id, snapshot_date, asin)
);

CREATE INDEX idx_inventory_account_date ON inventory_data(account_id, snapshot_date DESC);

-- Advertising Data

CREATE TABLE advertising_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES amazon_accounts(id) ON DELETE CASCADE,
    campaign_id VARCHAR(50) NOT NULL,
    campaign_name VARCHAR(255),
    campaign_type VARCHAR(50), -- sponsoredProducts, sponsoredBrands, sponsoredDisplay
    state VARCHAR(20), -- enabled, paused, archived
    daily_budget DECIMAL(10,2),
    targeting_type VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(account_id, campaign_id)
);

CREATE TABLE advertising_metrics (
    id BIGSERIAL PRIMARY KEY,
    campaign_id UUID REFERENCES advertising_campaigns(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    
    -- Performance Metrics
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    cost DECIMAL(10,2) DEFAULT 0,
    attributed_sales_1d DECIMAL(10,2) DEFAULT 0,
    attributed_sales_7d DECIMAL(10,2) DEFAULT 0,
    attributed_sales_14d DECIMAL(10,2) DEFAULT 0,
    attributed_sales_30d DECIMAL(10,2) DEFAULT 0,
    attributed_units_ordered_1d INTEGER DEFAULT 0,
    attributed_units_ordered_7d INTEGER DEFAULT 0,
    attributed_units_ordered_14d INTEGER DEFAULT 0,
    attributed_units_ordered_30d INTEGER DEFAULT 0,
    
    -- Calculated (stored for query performance)
    ctr DECIMAL(8,4),
    cpc DECIMAL(8,4),
    acos DECIMAL(8,4),
    roas DECIMAL(8,4),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(campaign_id, date)
);

CREATE INDEX idx_ad_metrics_campaign_date ON advertising_metrics(campaign_id, date DESC);

-- Products & Catalog

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES amazon_accounts(id) ON DELETE CASCADE,
    asin VARCHAR(20) NOT NULL,
    sku VARCHAR(100),
    
    -- Product Info
    title TEXT,
    brand VARCHAR(255),
    category VARCHAR(255),
    subcategory VARCHAR(255),
    
    -- Current State
    current_price DECIMAL(10,2),
    current_bsr INTEGER,
    review_count INTEGER,
    rating DECIMAL(3,2),
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(account_id, asin)
);

-- BSR History (for trend analysis)
CREATE TABLE bsr_history (
    id BIGSERIAL PRIMARY KEY,
    product_id UUID REFERENCES products(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    category VARCHAR(255),
    bsr INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(product_id, date, category)
);

CREATE INDEX idx_bsr_product_date ON bsr_history(product_id, date DESC);

-- Competitor Tracking

CREATE TABLE competitors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    asin VARCHAR(20) NOT NULL,
    marketplace VARCHAR(10) NOT NULL,
    
    -- Info
    title TEXT,
    brand VARCHAR(255),
    
    -- Current State
    current_price DECIMAL(10,2),
    current_bsr INTEGER,
    review_count INTEGER,
    rating DECIMAL(3,2),
    
    is_tracking BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(organization_id, asin, marketplace)
);

CREATE TABLE competitor_history (
    id BIGSERIAL PRIMARY KEY,
    competitor_id UUID REFERENCES competitors(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    price DECIMAL(10,2),
    bsr INTEGER,
    review_count INTEGER,
    rating DECIMAL(3,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(competitor_id, date)
);

-- Forecasts & Predictions

CREATE TABLE forecasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES amazon_accounts(id) ON DELETE CASCADE,
    asin VARCHAR(20),
    forecast_type VARCHAR(50), -- 'sales', 'units', 'revenue'
    
    -- Forecast Data
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    forecast_horizon_days INTEGER,
    model_used VARCHAR(50), -- 'prophet', 'arima', 'xgboost'
    confidence_interval DECIMAL(5,2), -- e.g., 0.95
    
    -- Stored as JSONB for flexibility
    predictions JSONB, -- [{date, value, lower, upper}, ...]
    
    -- Model Metrics
    mape DECIMAL(8,4), -- Mean Absolute Percentage Error
    rmse DECIMAL(12,4) -- Root Mean Square Error
);

CREATE INDEX idx_forecasts_account ON forecasts(account_id, generated_at DESC);

-- Scheduled Jobs & Sync History

CREATE TABLE sync_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES amazon_accounts(id) ON DELETE CASCADE,
    job_type VARCHAR(50) NOT NULL, -- 'sales', 'inventory', 'advertising', 'catalog'
    
    -- Scheduling
    schedule_cron VARCHAR(100), -- e.g., '0 2 * * *' for daily at 2am
    is_enabled BOOLEAN DEFAULT true,
    
    -- Last Run
    last_run_at TIMESTAMP WITH TIME ZONE,
    last_run_status VARCHAR(20), -- 'success', 'error', 'running'
    last_run_error TEXT,
    last_run_records_processed INTEGER,
    
    -- Next Run
    next_run_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Alerts Configuration

CREATE TABLE alert_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    
    -- Rule Definition
    name VARCHAR(255) NOT NULL,
    alert_type VARCHAR(50) NOT NULL, -- 'low_stock', 'bsr_drop', 'price_change', 'sync_failure'
    conditions JSONB NOT NULL, -- {metric, operator, threshold, ...}
    
    -- Targeting
    applies_to_accounts UUID[], -- NULL = all accounts
    applies_to_asins VARCHAR[], -- NULL = all products
    
    -- Notification
    notification_channels VARCHAR[], -- ['email', 'webhook', 'slack']
    notification_emails VARCHAR[],
    webhook_url TEXT,
    
    -- Status
    is_enabled BOOLEAN DEFAULT true,
    last_triggered_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Views for common queries

CREATE VIEW v_account_summary AS
SELECT 
    aa.id,
    aa.account_name,
    aa.marketplace_country,
    aa.account_type,
    aa.sync_status,
    aa.last_sync_at,
    COALESCE(SUM(sd.ordered_product_sales), 0) as total_sales_30d,
    COALESCE(SUM(sd.units_ordered), 0) as total_units_30d,
    COUNT(DISTINCT sd.asin) as active_asins
FROM amazon_accounts aa
LEFT JOIN sales_data sd ON aa.id = sd.account_id 
    AND sd.date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY aa.id;
```

---

## API Endpoints

### Authentication
```
POST   /api/v1/auth/login          # Login, get JWT
POST   /api/v1/auth/register       # Register new user
POST   /api/v1/auth/refresh        # Refresh JWT token
POST   /api/v1/auth/logout         # Invalidate token
GET    /api/v1/auth/me             # Current user profile
```

### Amazon Accounts
```
GET    /api/v1/accounts            # List all connected accounts
POST   /api/v1/accounts            # Connect new Amazon account
GET    /api/v1/accounts/{id}       # Get account details
PUT    /api/v1/accounts/{id}       # Update account settings
DELETE /api/v1/accounts/{id}       # Disconnect account
POST   /api/v1/accounts/{id}/sync  # Trigger manual sync
GET    /api/v1/accounts/{id}/status # Get sync status
```

### Reports & Data
```
GET    /api/v1/reports/sales       # Get sales data
GET    /api/v1/reports/inventory   # Get inventory data
GET    /api/v1/reports/advertising # Get advertising data
GET    /api/v1/reports/orders      # Get order data
POST   /api/v1/reports/schedule    # Schedule recurring report
```

### Analytics
```
GET    /api/v1/analytics/dashboard      # Aggregated KPIs
GET    /api/v1/analytics/trends         # Trend analysis
GET    /api/v1/analytics/comparison     # Period comparison
GET    /api/v1/analytics/competitors    # Competitor analysis
GET    /api/v1/analytics/advertising    # Ads performance
```

### Forecasts
```
GET    /api/v1/forecasts                # List forecasts
POST   /api/v1/forecasts/generate       # Generate new forecast
GET    /api/v1/forecasts/{id}           # Get forecast details
GET    /api/v1/forecasts/products/{asin} # Forecast for product
```

### Catalog Management
```
GET    /api/v1/catalog/products         # List products
GET    /api/v1/catalog/products/{asin}  # Get product details
PUT    /api/v1/catalog/products/{asin}  # Update product
POST   /api/v1/catalog/bulk-update      # Bulk update via Excel
POST   /api/v1/catalog/prices           # Update prices
POST   /api/v1/catalog/images           # Upload images
```

### Exports
```
POST   /api/v1/exports/excel            # Generate Excel export
POST   /api/v1/exports/powerpoint       # Generate PPT report
POST   /api/v1/exports/google-sheets    # Push to Google Sheets
GET    /api/v1/exports/{id}/download    # Download generated file
```

### Alerts
```
GET    /api/v1/alerts/rules             # List alert rules
POST   /api/v1/alerts/rules             # Create alert rule
PUT    /api/v1/alerts/rules/{id}        # Update rule
DELETE /api/v1/alerts/rules/{id}        # Delete rule
GET    /api/v1/alerts/history           # Alert history
```

---

## Environment Variables

```bash
# ===========================================
# Application
# ===========================================
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=your-secret-key-min-32-chars
APP_API_URL=https://api.inthezon.niuexa.ai
APP_FRONTEND_URL=https://inthezon.niuexa.ai

# ===========================================
# Database
# ===========================================
DATABASE_URL=postgresql://user:pass@host:5432/inthezon
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# ===========================================
# Redis
# ===========================================
REDIS_URL=redis://user:pass@host:6379/0
CELERY_BROKER_URL=redis://user:pass@host:6379/1
CELERY_RESULT_BACKEND=redis://user:pass@host:6379/2

# ===========================================
# Amazon SP-API
# ===========================================
AMAZON_SP_API_APP_ID=amzn1.sp.solution.xxxxx
AMAZON_SP_API_CLIENT_ID=amzn1.application-oa2-client.xxxxx
AMAZON_SP_API_CLIENT_SECRET=xxxxx
AMAZON_SP_API_AWS_ACCESS_KEY=AKIA...
AMAZON_SP_API_AWS_SECRET_KEY=xxxxx
AMAZON_SP_API_ROLE_ARN=arn:aws:iam::xxxxx:role/xxxxx

# ===========================================
# Amazon Advertising API
# ===========================================
AMAZON_ADS_CLIENT_ID=amzn1.application-oa2-client.xxxxx
AMAZON_ADS_CLIENT_SECRET=xxxxx
AMAZON_ADS_PROFILE_ID=xxxxx

# ===========================================
# AWS S3 (for file storage)
# ===========================================
AWS_S3_BUCKET=inthezon-reports
AWS_S3_REGION=eu-south-1
AWS_ACCESS_KEY_ID=xxxxx
AWS_SECRET_ACCESS_KEY=xxxxx

# ===========================================
# Email (SendGrid)
# ===========================================
SENDGRID_API_KEY=SG.xxxxx
SENDGRID_FROM_EMAIL=noreply@niuexa.ai

# ===========================================
# Encryption
# ===========================================
ENCRYPTION_KEY=your-fernet-key-base64

# ===========================================
# JWT
# ===========================================
JWT_SECRET_KEY=your-jwt-secret
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ===========================================
# Rate Limiting
# ===========================================
RATE_LIMIT_PER_MINUTE=60
```

---

## Render Deployment Blueprint

See `render.yaml` in project root.

---

## Security Considerations

### Data Encryption
- Amazon credentials encrypted at rest using Fernet (symmetric encryption)
- TLS 1.3 for all API communications
- Database connections over SSL

### Authentication
- JWT with short-lived access tokens (30 min)
- Refresh tokens with rotation
- Password hashing with bcrypt (12 rounds)

### API Security
- Rate limiting (60 req/min per user)
- CORS restricted to frontend domain
- Input validation with Pydantic
- SQL injection prevention via ORM

### Amazon API Compliance
- OAuth refresh token stored encrypted
- Rate limiting to stay within SP-API limits
- Automatic token refresh

---

## Scalability Considerations

### Database
- Table partitioning for time-series data (by month)
- Indexes on frequently queried columns
- Connection pooling (PgBouncer if needed)

### Background Jobs
- Celery with multiple queues (high, default, low priority)
- Concurrency configurable per worker
- Dead letter queue for failed jobs

### Caching
- Redis for session data
- API response caching for dashboard (5 min TTL)
- Rate limiter counters

### Horizontal Scaling
- Stateless API servers (add more Render instances)
- Database read replicas if needed
- Celery workers scale independently

---

## Monitoring & Logging

### Recommended Setup
- **Logging:** Structured JSON logs → Render logs
- **APM:** Sentry for error tracking
- **Metrics:** Prometheus + Grafana (or Render metrics)
- **Uptime:** UptimeRobot / Better Uptime

### Key Metrics to Track
- API response times (p50, p95, p99)
- Sync job success/failure rates
- Database query performance
- Background job queue depth
- Amazon API rate limit consumption

---

## Development Setup

```bash
# Clone repository
git clone https://github.com/niuexa/inthezon-platform.git
cd inthezon-platform

# Start services with Docker
docker-compose up -d

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend setup (new terminal)
cd frontend
npm install
npm run dev

# Celery worker (new terminal)
cd backend
celery -A workers.celery_app worker --loglevel=info

# Celery beat scheduler (new terminal)
cd backend
celery -A workers.celery_app beat --loglevel=info
```

---

## Next Steps

1. **Phase 1 (MVP):** Core data extraction + dashboard
2. **Phase 2:** Catalog management + exports
3. **Phase 3:** Predictive analytics + recommendations
4. **Phase 4:** Advanced features (alerts, integrations)

---

*Document Version: 1.0*  
*Last Updated: January 2026*
