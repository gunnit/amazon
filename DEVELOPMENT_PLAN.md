# Inthezon — Prioritized Development Plan

> Generated April 13, 2026 — based on "Avanzamento tool Niuexa.xlsx" and current codebase analysis.

Each task is ordered by business impact (highest to lowest). For each one, the current state, what's concretely missing in the code, and a ready-to-use Claude Code prompt are provided.

---

## PHASE 1 — CRITICAL IMPACT (Core Data Pipeline)

These tasks unblock most downstream features (analytics, forecasting, reporting). Without complete data, everything else is partial.

---

### 1.1 Inventory Report Extraction 🔴

**Current state:** The `InventoryData` model exists (ASIN, fulfillment_channel, quantity, date). The `/reports/inventory` endpoint exists but only returns data if present in DB. `DataExtractionService.sync_account()` syncs sales but the inventory flow is incomplete — it doesn't call the FBA Manage Inventory report or GET_FBA_MYI_ALL_INVENTORY_DATA from SP-API.

**What's missing:** Real integration with SP-API Reports for FBA inventory (reportType `GET_FBA_MYI_ALL_INVENTORY_DATA`), CSV report parsing, persistence to `InventoryData`, inclusion in periodic sync.

**Claude Code Prompt:**
```
Implement automatic FBA inventory report extraction via SP-API.

Context:
- The InventoryData model is already in backend/app/models/inventory_data.py (fields: account_id, asin, date, fulfillment_channel, quantity)
- The DataExtractionService is in backend/app/services/data_extraction.py
- The SP-API client is in backend/app/core/amazon/sp_api_client.py

Steps:
1. In sp_api_client.py, add a `fetch_inventory_report()` method that:
   - Requests the GET_FBA_MYI_ALL_INVENTORY_DATA report via SP-API Reports API
   - Implements polling to wait for report completion (with exponential backoff)
   - Downloads and parses the resulting TSV/CSV file
   - Returns a list of dicts with: asin, sku, fulfillment_channel, quantity (afn-fulfillable-quantity), reserved_quantity, inbound_quantity

2. In data_extraction.py, in the sync_account() method or a new dedicated `sync_inventory()` method:
   - Call fetch_inventory_report()
   - Upsert into InventoryData (conflict on account_id + asin + date + fulfillment_channel)
   - Log the number of updated records

3. In workers/tasks/extraction.py, ensure sync_account() also calls sync_inventory()

4. Verify that the GET /api/v1/reports/inventory endpoint in backend/app/api/v1/reports.py correctly returns the newly extracted data, with filters for account_id, asin, date range.

Do not modify the frontend — data will be consumed by existing pages.
```

---

### 1.2 Advertising/PPC Data Extraction 🔴

**Current state:** The `AdvertisingCampaign` and `AdvertisingMetrics` models exist. The `/analytics/advertising` endpoint exists. `sp_api_client.py` has a `fetch_advertising_metrics()` method but it uses the Seller Central endpoint, not the dedicated Amazon Advertising API. The sync doesn't regularly populate this data.

**What's missing:** Client for Amazon Advertising API (separate from SP-API), download of Sponsored Products/Brands/Display reports, parsing and persistence of daily per-campaign metrics.

**Claude Code Prompt:**
```
Implement advertising data extraction from the Amazon Advertising API.

Context:
- Models exist: AdvertisingCampaign and AdvertisingMetrics in backend/app/models/advertising.py
- Advertising API credentials are separate from SP-API (client_id, client_secret, refresh_token for Advertising)
- The /analytics/advertising endpoint exists in analytics.py

Steps:
1. Create a new client backend/app/core/amazon/advertising_client.py:
   - AdvertisingAPIClient class with OAuth authentication (refresh token → access token)
   - Support for profile IDs (each marketplace has a different profile_id)
   - Method list_campaigns(profile_id) → returns SP/SB/SD campaigns
   - Method request_report(profile_id, report_type, date_range) to request async reports
   - Method download_report(report_id) to download the generated report (GZIP JSON)
   - Throttling handling with retry and Retry-After header

2. Add Advertising API credential fields to the AmazonAccount model or Organization (advertising_profile_id, advertising_refresh_token) — create an Alembic migration.

3. In data_extraction.py, add sync_advertising():
   - Call list_campaigns() → upsert into AdvertisingCampaign
   - Call request_report() for Sponsored Products (metrics: impressions, clicks, cost, sales, orders) for the last 7 days
   - Parse the report and upsert into AdvertisingMetrics (conflict on campaign_id + date)

4. Include sync_advertising() in the sync_account() task in workers/tasks/extraction.py

5. Verify that the /analytics/advertising endpoint returns real data by calculating ROAS, ACoS, CTR from the metrics.
```

---

### 1.3 Order Data Extraction 🔴

**Current state:** `SalesData` tracks aggregate sales per day/ASIN, but there are no order-by-order records (order ID, items, buyer info). The `/analytics/orders-by-hour` endpoint attempts to call SP-API Orders but doesn't persist the data.

**What's missing:** Model for individual orders, sync via SP-API Orders API, endpoint to query them.

**Claude Code Prompt:**
```
Implement extraction and persistence of individual order data from SP-API.

Context:
- SalesData in backend/app/models/sales_data.py only tracks daily aggregate sales
- SP-API Orders endpoint is already referenced in analytics.py (orders-by-hour) but data is not saved

Steps:
1. Create a new model backend/app/models/order.py:
   - Order class: id, account_id (FK), amazon_order_id (unique), purchase_date, order_status, fulfillment_channel, order_total, currency, marketplace_id, number_of_items, created_at
   - OrderItem class: id, order_id (FK), asin, sku, title, quantity, item_price, item_tax
   - Create the corresponding Alembic migration with indexes on (account_id, purchase_date) and (amazon_order_id)

2. In sp_api_client.py, add:
   - fetch_orders(created_after, created_before) → calls GET /orders/v0/orders with pagination (NextToken)
   - fetch_order_items(order_id) → calls GET /orders/v0/orders/{orderId}/orderItems

3. In data_extraction.py, add sync_orders():
   - Call fetch_orders() for the last 7 days (or since last sync)
   - For each order, call fetch_order_items() (with rate limiting: max 1 req/sec for Orders API)
   - Upsert into Order and OrderItem (conflict on amazon_order_id)

4. Add sync_orders() to the sync_account() task

5. Create endpoint GET /api/v1/reports/orders with filters (account_id, date_range, order_status, asin) and pagination. Register it in the router.
```

---

### 1.4 Long-Term Data Retention 🔴

**Current state:** Data is saved in PostgreSQL but there's no retention strategy, no partitioning, no archiving. The requirement is a minimum of 24 months.

**What's missing:** Retention policy, date-based partitioning on time-series tables, optional cold storage for data beyond 24 months.

**Claude Code Prompt:**
```
Implement long-term data retention strategy (minimum 24 months).

Context:
- Main time-series tables are: sales_data, inventory_data, advertising_metrics, bsr_history, orders (if created)
- DB is PostgreSQL on Render.com
- Migrations are managed with Alembic in backend/app/db/migrations/versions/

Steps:
1. Create an Alembic migration that:
   - Adds monthly partitioning (range partitioning on "date" column) for sales_data, inventory_data, advertising_metrics, bsr_history
   - Uses pg_partman if available, otherwise creates manual partitions for the next 24 months
   - Adds a BRIN index on (date) for each partitioned table for efficient range queries

2. Create a periodic Celery task in workers/tasks/maintenance.py:
   - manage_partitions(): automatically creates partitions for the next 3 future months and archives/detaches partitions beyond 36 months
   - Schedule it weekly in the Celery beat schedule

3. Add a DATA_RETENTION_MONTHS = 24 setting in backend/app/config.py

4. Create an endpoint GET /api/v1/admin/data-health that returns:
   - Available date ranges for each time-series table
   - Record count per table
   - Disk space used (pg_total_relation_size)

Do not touch the frontend. Document the strategy in a comment in the migration.
```

---

## PHASE 2 — HIGH IMPACT (Analytics & Intelligence)

With complete data, these features enable the analysis the team uses daily.

---

### 2.1 Advertising vs Organic Data Correlation 🔴

**Current state:** Sales data (SalesData) and advertising data (AdvertisingMetrics) exist as separate silos. There's no logic correlating them to show organic vs. PPC-driven sales.

**What's missing:** Calculation logic for organic sales = total sales − advertising-attributed sales. Dedicated endpoint. Frontend component.

**Claude Code Prompt:**
```
Implement correlation analysis between advertising sales and organic sales.

Context:
- SalesData contains ordered_product_sales (total sales) per account/asin/date
- AdvertisingMetrics contains attributed_sales_7d (ad-attributed sales) per campaign/date
- The analytics endpoint is in backend/app/api/v1/analytics.py
- The frontend Analytics is in frontend/src/pages/Analytics.tsx

Steps:
1. In backend/app/services/analytics_service.py, add a method `get_ads_vs_organic(account_ids, date_from, date_to, group_by)`:
   - JOIN SalesData with AdvertisingMetrics on the same date and account
   - Calculate: total_sales = SUM(ordered_product_sales), ad_sales = SUM(attributed_sales_7d), organic_sales = total_sales - ad_sales
   - Calculate percentages: ad_share = ad_sales/total_sales, organic_share = organic_sales/total_sales
   - Group by group_by (day/week/month) and return time-series
   - Include per-ASIN breakdown if requested

2. Add endpoint GET /api/v1/analytics/ads-vs-organic in analytics.py with query params: account_ids, date_from, date_to, group_by, asin (optional)

3. In the frontend, in Analytics.tsx:
   - Add a new "Adv vs Organic" tab
   - Use a stacked AreaChart (Recharts) with two areas: "Advertising Sales" (orange) and "Organic Sales" (green)
   - Below the chart, show KPI cards: % sales from Adv, % organic sales, trend vs previous period
   - Add an optional ASIN selector for per-product drill-down

4. Add the Pydantic schema for the response in backend/app/schemas/.
```

---

### 2.2 Period-over-Period Comparison (improvement) 🟡

**Current state:** The `/analytics/comparison` endpoint exists and calculates metrics for two periods, but the frontend doesn't show an immediate visual comparison. YoY/MoM comparison with visual trends is missing.

**Claude Code Prompt:**
```
Improve the period-over-period comparison in the frontend with immediate visualization.

Context:
- The GET /api/v1/analytics/comparison endpoint already exists and returns metrics for current_period and previous_period with change_pct
- The frontend Analytics.tsx has a comparisons tab but rendering is basic
- ComparisonFilter and DateRangeFilter are in frontend/src/components/filters/

Steps:
1. In frontend/src/pages/Analytics.tsx, comparison section:
   - Add quick presets: "Month vs Previous Month", "Year vs Previous Year", "Quarter vs Previous Quarter", "Custom"
   - For each metric (revenue, units, orders, AOV), show a card with: current value, previous value, delta % with color (green if positive, red if negative), sparkline mini-chart of the trend
   - Below the cards, add a grouped BarChart (Recharts) showing metrics side by side for both periods
   - If the comparison spans more than 30 days, show a LineChart with both series overlaid (current period = solid line, previous = dashed line)

2. If the endpoint doesn't yet return time-series data for both periods (only aggregates), extend GET /api/v1/analytics/comparison in analytics.py by adding a "daily_series" field with daily datapoints for both periods.

3. Add an "Export comparison" button that calls the existing Excel export with both periods' parameters.
```

---

### 2.3 Competitor Data Collection (improvement) 🟡

**Current state:** The `Competitor` and `MarketResearchReport` models exist. The `MarketResearchService` discovers competitors via SP-API catalog. But in the preview, data was not being returned correctly.

**Claude Code Prompt:**
```
Fix and improve competitor data collection.

Context:
- MarketResearchService is in backend/app/services/market_research_service.py
- The Competitor model is in backend/app/models/market_research.py
- The endpoint is /api/v1/market-research/ in market_research.py
- The SP-API client is in backend/app/core/amazon/sp_api_client.py

Steps:
1. Debug the market research flow:
   - In market_research_service.py, verify that search_catalog_by_keyword() returns valid results (log the raw response)
   - Check that get_competitive_pricing() and get_product_pricing() don't fail silently — add granular try/except with logging for each ASIN
   - If SP-API returns 403/429 errors for pricing, implement fallback: use catalog data (catalogItems) as baseline

2. Add a refresh_competitor_data(competitor_id) method to the service that:
   - Re-fetches pricing, BSR, review count for a specific competitor
   - Updates the Competitor record in DB
   - Updates the competitor_data field in the associated MarketResearchReport

3. Add a periodic Celery task (daily) in workers/tasks/ that refreshes active competitor data (those in reports from the last 30 days)

4. In the frontend MarketResearch.tsx:
   - Verify that CompetitorTable displays all fields: price, BSR, reviews, rating
   - Add a "Refresh data" button per competitor that triggers the refresh
   - Show a "Last updated: X hours ago" badge for each competitor
   - If a field is null/undefined, display "N/A" instead of leaving it blank
```

---

### 2.4 Client vs Competitor Comparison (improvement) 🟡

**Current state:** Partially implemented in MarketResearch with RadarChart. But data was not being returned correctly (same issue as section 2.3).

**Claude Code Prompt:**
```
Improve direct client-vs-competitor comparison in the Market Research section.

Context:
- The RadarComparison component exists in frontend/src/components/market-research/
- The MarketResearchReport contains product_snapshot (client data) and competitor_data (array of competitors)
- Depends on the fix from section 2.3 (working competitor data)

Steps:
1. In the backend, in market_research_service.py, add a method get_comparison_matrix(report_id):
   - Return a structured matrix: for each dimension (price, BSR, reviews, rating) show the client's value and each competitor's
   - Calculate the client's "rank" for each dimension (e.g., 2nd out of 5 for price)
   - Calculate an overall "competitive score" (weighted average of normalized ranks)
   - Identify gaps and opportunities (e.g., "Price 15% above competitor average")

2. Add endpoint GET /api/v1/market-research/{id}/comparison-matrix

3. In the frontend MarketResearch.tsx:
   - Below the RadarChart, add a comparison table with columns: Dimension | Your Product | Competitor Average | Best Competitor | Gap
   - Color cells: green if client is better, red if worse
   - Add an "Opportunities" section showing AI-identified gaps as actionable cards
   - Allow selecting/deselecting specific competitors from the comparison
```

---

### 2.5 Sales Forecasting (verification) 🟡

**Current state:** The ForecastService with Prophet is implemented, the /forecasts/generate endpoint works. But verification is needed to ensure predictions are realistic.

**Claude Code Prompt:**
```
Improve the accuracy and presentation of sales forecasts.

Context:
- ForecastService in backend/app/services/forecast_service.py uses Prophet
- Forecasts are saved with MAPE and RMSE in the Forecast model
- The /forecasts/ endpoint is in backend/app/api/v1/forecasts.py
- The frontend is in frontend/src/pages/Forecasts.tsx

Steps:
1. In forecast_service.py:
   - Add pre-training validation: require at least 90 days of historical data (currently the minimum is unclear)
   - Add cross-validation using Prophet's built-in cross_validation() to calculate MAPE on holdout set
   - If MAPE > 30%, flag the forecast as "low_confidence" and show it in the response
   - Add external regressors if available: day of week (already handled by Prophet), Amazon holidays (Prime Day, Black Friday — use the holidays module), advertising spend trend
   - Log accuracy metrics for monitoring

2. In the frontend Forecasts.tsx:
   - Show a confidence badge: "High" (MAPE < 15%), "Medium" (15-30%), "Low" (> 30%)
   - In the chart, show the confidence interval as a shaded area
   - Add a table below the chart with: date, predicted value, lower bound, upper bound
   - Add a disclaimer for low-confidence forecasts: "Insufficient historical data for a reliable forecast"
```

---

### 2.6 Product Trend Prediction 🔴

**Current state:** `ProductTrendsService` exists and calculates trend scores. The `/analytics/product-trends` endpoint is implemented. But there's no proactive alert system or dedicated view.

**Claude Code Prompt:**
```
Implement a complete product trend detection system.

Context:
- ProductTrendsService is in backend/app/services/product_trends_service.py
- The calculate_trend_scores task is in workers/tasks/forecasting.py
- The /analytics/product-trends endpoint is in analytics.py

Steps:
1. In product_trends_service.py:
   - Improve the trend score calculation using: 7d sales change vs previous 7d, BSR change, review velocity change (new reviews/week)
   - Classify products as: "rising_fast" (>20% growth), "rising" (5-20%), "stable" (-5% to +5%), "declining" (-5% to -20%), "declining_fast" (<-20%)
   - For each trending product, generate a text insight (e.g., "Sales +35% this week, BSR improved by 1,200 positions")

2. Create a widget in the Dashboard (frontend/src/pages/Dashboard.tsx):
   - "Trending Products" section with top 5 rising and top 5 declining products
   - For each product: ASIN, title, colored trend badge, mini 14d sales sparkline, delta %
   - Clicking a product navigates to the Analytics page filtered by that ASIN

3. Integrate with the Alert system: when a product moves to "declining_fast", automatically generate an Alert with severity "warning" — add this logic in product_trends_service.py by calling Alert creation.
```

---

## PHASE 3 — MEDIUM IMPACT (Reporting & Delivery)

Features that improve team productivity and client communication.

---

### 3.1 PowerPoint Report Generation (improvement) 🟡

**Current state:** A PdfExportButton exists in the frontend. PDF reports work. But PPT generation is not yet integrated despite being requested.

**Claude Code Prompt:**
```
Implement automatic PowerPoint report generation.

Context:
- ExportService in backend/app/services/export_service.py handles CSV/Excel/PDF
- PDFService in backend/app/services/pdf_service.py generates PDFs with ReportLab
- The /exports/ endpoint is in backend/app/api/v1/exports.py
- python-pptx is the library to use

Steps:
1. Create backend/app/services/pptx_service.py:
   - PPTXService class with method generate_report(account_ids, date_from, date_to, report_sections)
   - Slide 1: Title slide with account name, period, logo placeholder
   - Slide 2: Executive Summary — main KPIs (revenue, units, orders, YoY change) in formatted boxes
   - Slide 3: Sales Trend — line chart (use python-pptx chart API) with daily/weekly sales
   - Slide 4: Top Products — table with top 10 products by revenue
   - Slide 5: Advertising Performance — ad KPIs (spend, ROAS, ACoS) + chart
   - Slide 6: Competitor Overview — comparative table (if data available)
   - Slide 7: Recommendations — bullet points from AI analysis (if available)
   - Use a professional theme: white background, blue accents (#1a73e8), Calibri font

2. Add endpoint POST /api/v1/exports/pptx in exports.py with body: account_ids, date_from, date_to, sections (optional)

3. In the frontend, on the Reports.tsx page:
   - Add an "Export PowerPoint" button next to existing Excel/PDF buttons
   - The button calls the new endpoint and downloads the .pptx file

4. Integrate into the ScheduledReport system: add "pptx" as an available format in the ScheduledReport model and service.
```

---

### 3.2 Scheduled Report Delivery 🔴

**Current state:** The `ScheduledReport` and `ScheduledReportRun` models exist. The Celery tasks `scan_scheduled_reports_due` and `process_scheduled_report_run_task` are implemented. But in the preview, the feature was not yet integrated in the frontend.

**Claude Code Prompt:**
```
Complete the frontend integration for scheduled report delivery.

Context:
- Backend fully implemented: ScheduledReport model, ScheduledReportRun, CRUD endpoints in reports.py, Celery tasks for scan/process/deliver
- The frontend Reports.tsx exists but lacks the UI for managing scheduled reports
- SendGrid is configured for email delivery

Steps:
1. In frontend Reports.tsx, add a "Scheduled Reports" tab:
   - List of existing scheduled reports with: name, frequency, format, recipients, next execution, last delivery status
   - "New Scheduled Report" button that opens a Dialog/Modal with form:
     - Report name
     - Report type (sales, inventory, advertising, full)
     - Accounts to include (multi-select)
     - Format (Excel, PDF, PPT)
     - Frequency (daily, weekly, monthly)
     - Delivery day/time (for weekly: day of week; for monthly: day of month)
     - Email recipients (input with chips/tags for multiple emails)
   - For each report in the list: Edit, Delete, "Send now" (manual trigger) buttons
   - Execution history: clicking a report shows the last 10 runs with status (success/failed), date, error if present

2. Create necessary components in frontend/src/components/reports/:
   - ScheduledReportForm.tsx (create/edit form)
   - ScheduledReportList.tsx (list with actions)
   - ScheduledReportHistory.tsx (execution history)

3. Add API calls in frontend/src/services/api.ts for the /reports/scheduled-reports endpoints.
```

---

### 3.3 Returns Analysis Visualization 🔴

**Current state:** The dashboard calculates a `return_rate` but there's no data model for individual returns nor an analysis of return reasons.

**Claude Code Prompt:**
```
Implement returns analysis with reasons and trends.

Context:
- No returns model exists — needs to be created
- SP-API has the GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA report for FBA returns
- The analytics endpoint exists in analytics.py

Steps:
1. Create model backend/app/models/returns_data.py:
   - ReturnData class: id, account_id (FK), amazon_order_id, asin, sku, return_date, quantity, reason (string: "DEFECTIVE", "NOT_AS_DESCRIBED", "WRONG_ITEM", etc.), disposition ("SELLABLE", "DAMAGED", "CUSTOMER_DAMAGED"), detailed_disposition, created_at
   - Create Alembic migration with indexes on (account_id, return_date) and (asin)

2. In sp_api_client.py, add fetch_returns_report():
   - Request report GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA
   - Polling + download + TSV parsing

3. In data_extraction.py, add sync_returns() and include it in sync_account()

4. Create endpoint GET /api/v1/analytics/returns with response:
   - return_rate per period (returns/orders)
   - Breakdown by reason (pie chart data)
   - Top ASINs by return rate
   - Return rate trend over time
   - Filters: account_ids, date_range, asin

5. In frontend Analytics.tsx:
   - Add "Returns Analysis" tab
   - PieChart for reason distribution
   - BarChart for top 10 ASINs with most returns
   - LineChart for return rate trend over time
   - Detail table with columns: ASIN, Product, Reason, Quantity, % of total orders
```

---

## PHASE 4 — MEDIUM-LOW IMPACT (Catalog Management & Operations)

Operational features for catalog management. Useful but not blocking for analytics.

---

### 4.1 Bulk Product Listing Updates 🔴

**Claude Code Prompt:**
```
Implement bulk product listing updates via Excel upload.

Context:
- The /catalog/bulk-update endpoint exists in backend/app/api/v1/catalog.py but only accepts updates to the internal DB, doesn't push changes to Amazon
- SP-API Listings API (PUT /listings/2021-08-01/items/{sellerId}/{sku}) allows updating title, bullet points, description, keywords
- The Product model is in backend/app/models/product.py

Steps:
1. In sp_api_client.py, add:
   - update_listing(seller_id, sku, attributes) → calls PUT /listings/2021-08-01/items/{sellerId}/{sku} with JSON Patch payload
   - Payload must follow Amazon Product Type Definition format (productType required)
   - Handle validation errors and return issues per SKU

2. In backend/app/services/catalog_service.py (create if doesn't exist):
   - Method bulk_update_from_excel(file, account_id):
     - Parse Excel file with columns: SKU, Title, BulletPoint1-5, Description, SearchTerms
     - For each row, call update_listing() via SP-API
     - Collect results: successes and errors per SKU
     - Return an execution report

3. Modify the POST /catalog/bulk-update endpoint to:
   - Accept Excel file upload (multipart/form-data)
   - Execute the update via Celery task (to avoid blocking the request)
   - Return a job_id for tracking

4. In the frontend, on the dedicated page (or in Settings):
   - Add "Bulk Catalog Update" section
   - Excel file upload with drag-and-drop
   - "Download template" button that generates an Excel with correct columns and pre-filled current data
   - After upload: progress bar and results table (SKU | Status | Error)
```

---

### 4.2 Price Management 🔴

**Claude Code Prompt:**
```
Implement price management with competitor comparison.

Context:
- The /catalog/prices endpoint exists for bulk updates via JSON
- SP-API Pricing API: updateListingPrice via Listings API
- The Competitor model has current_price

Steps:
1. In sp_api_client.py, add update_price(seller_id, sku, price, currency):
   - Use Listings API to update the price
   - Handle errors (e.g., price below Amazon floor)

2. Create backend/app/services/pricing_service.py:
   - get_pricing_overview(account_id): for each active product, return current price, competitor average price, competitor minimum price, difference %
   - update_prices_bulk(account_id, prices): update prices via SP-API and in local DB
   - suggest_price(asin): based on competitor data, suggest a competitive price

3. Add endpoints GET /api/v1/catalog/pricing-overview and POST /api/v1/catalog/update-prices

4. In the frontend, create page or tab "Price Management":
   - Table: ASIN | Title | Current Price | Competitor Average | Competitor Min | Gap % | Action
   - Action column: input for new price + "Update" button
   - Highlight rows where price is >10% above competitor average
   - "Update all" button to apply bulk changes
```

---

### 4.3 Availability/Inventory Updates 🔴

**Claude Code Prompt:**
```
Implement product availability management.

Context:
- InventoryData model exists with quantity and fulfillment_channel fields
- There's no mechanism to mark products as available/unavailable

Steps:
1. In the Product model (backend/app/models/product.py), add is_available field (Boolean, default True) and availability_override (nullable, for manual override). Create Alembic migration.

2. In sp_api_client.py, add set_listing_status(seller_id, sku, status) where status is "ACTIVE" or "INACTIVE"

3. In catalog_service.py, add:
   - toggle_availability(account_id, asin, available: bool) → calls SP-API + updates DB
   - get_availability_dashboard(account_id) → product list with: ASIN, title, FBA stock, FBM stock, current status, estimated days of remaining stock (based on average daily sales)

4. Endpoints PATCH /api/v1/catalog/products/{asin}/availability and GET /api/v1/catalog/availability-dashboard

5. In the frontend, add a "Stock Status" widget to the Dashboard with:
   - Products at risk of stockout (< 14 days of estimated stock) highlighted in red
   - Toggle to activate/deactivate visibility of each product
```

---

### 4.4 Image Management 🔴

**Claude Code Prompt:**
```
Implement bulk product image updates.

Context:
- SP-API Listings API supports image upload via the "image" field in the payload
- No image management flow currently exists

Steps:
1. In sp_api_client.py, add upload_product_image(seller_id, sku, image_type, image_url_or_bytes):
   - Use Listings API with attribute "main_product_image_locator" or "other_product_image_locator_1" etc.
   - Support both URL and direct upload (for direct upload, first upload to S3/R2 and pass the URL)

2. Create an endpoint POST /api/v1/catalog/products/{asin}/images:
   - Accept multipart/form-data with: image_type (MAIN, PT01-PT08), file
   - Upload to S3/R2 → get URL → call SP-API
   - Return operation status

3. Create endpoint POST /api/v1/catalog/images/bulk-upload:
   - Accept ZIP file containing images named as {SKU}_{IMAGE_TYPE}.jpg
   - Process in background via Celery task
   - Return job_id for tracking

4. In the frontend, add "Image Management" section in the catalog page:
   - Product grid with current image thumbnails
   - Drag-and-drop to replace individual images
   - ZIP upload for bulk updates
   - Preview before upload
```

---

## PHASE 5 — LOW IMPACT (Nice-to-have / AI Recommendations)

Advanced features that add value but are not blocking.

---

### 5.1 Strategic Recommendations (improvement) 🟡

**Claude Code Prompt:**
```
Improve the strategic recommendations system with AI.

Context:
- AIAnalysisService in backend/app/services/ai_analysis_service.py uses Anthropic API
- ProductTrendsService generates text insights
- The /analytics/product-trends endpoint includes AI insights

Steps:
1. Create backend/app/services/strategic_recommendations_service.py:
   - Method generate_weekly_recommendations(account_id):
     - Aggregate: sales trends, inventory levels, ad performance, competitor changes, return rates
     - Build a structured prompt for Claude API with all aggregated data
     - Request recommendations in 4 areas: Pricing, Advertising, Inventory, Content
     - For each recommendation: suggested action, estimated impact (high/medium/low), priority, involved ASINs
   - Save to DB (create StrategicRecommendation model with Alembic migration)

2. Weekly Celery task (or on-demand) in workers/tasks/:
   - generate_strategic_recommendations() for all active accounts

3. Endpoints GET /api/v1/recommendations (list) and POST /api/v1/recommendations/generate (manual trigger)

4. In the frontend, add a "Recommendations" page or section:
   - Card for each recommendation with: area, action, impact, ASINs, rationale
   - Filter by area and impact
   - "Generate new recommendations" button
   - Recommendation history with dates
```

---

### 5.2 Google Sheets Integration (verification) 🟢

**Claude Code Prompt:**
```
Verify and complete the Google Sheets integration.

Context:
- Backend implemented: GoogleSheetsService, OAuth flow, sync configs in backend/app/services/google_sheets_service.py
- Celery task process_google_sheets_sync() exists
- Frontend Settings.tsx has Google Sheets section

Steps:
1. Test the full end-to-end flow:
   - Verify the "Connect Google Sheets" button in Settings generates the correct OAuth URL
   - Verify the callback correctly saves the token in GoogleSheetsConnection
   - Verify that creating a sync config works (spreadsheet_id, range, mapping)
   - Verify that manual sync ("Sync now") pushes data correctly

2. Fix any issues:
   - If OAuth token expires, verify automatic refresh works in google_sheets_service.py
   - If mapping doesn't work, verify the structure of pushed data (header row + data rows)

3. In frontend Settings.tsx:
   - Show connection status (connected/disconnected) with Google email
   - List sync configs with: spreadsheet name, last sync, frequency, status
   - Preview of data that will be synced before confirming
```

---

## Recommended Execution Sequence

```
Week 1-2:   1.1 (Inventory) + 1.2 (PPC) — in parallel, independent
Week 3:     1.3 (Orders) + 1.4 (Retention) — in parallel
Week 4:     2.1 (Adv vs Organic) — requires 1.2 completed
Week 5:     2.2 (Period comparison) + 2.3 (Competitor fix) — in parallel
Week 6:     2.4 (Client vs Competitor) + 2.5 (Forecast verification)
Week 7:     2.6 (Product trends) + 3.1 (PPT reports)
Week 8:     3.2 (Scheduled reports) + 3.3 (Returns)
Week 9-10:  4.1-4.4 (Catalog management) — in parallel where possible
Week 11:    5.1 (AI Recommendations) + 5.2 (Google Sheets verification)
```
