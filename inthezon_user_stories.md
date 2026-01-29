# Inthezon Amazon Automation Platform
## User Stories for Development

**Project:** Amazon Multi-Account Management & Analytics Platform  
**Client:** Inthezon (Libera Brand Building Group)  
**Date:** January 2026  

---

## Personas

| Persona | Role | Goals |
|---------|------|-------|
| **Account Manager** | Manages multiple Amazon seller/vendor accounts | Reduce manual data extraction, monitor performance |
| **Data Analyst** | Creates reports and presentations for clients | Access aggregated data, generate insights |
| **Strategist** | Makes decisions on pricing, inventory, campaigns | Get actionable recommendations, predictive insights |

---

## Epic 1: Multi-Account Authentication & Management

### US-1.1: Centralized Account Connection
**As an** Account Manager  
**I want to** connect multiple Amazon Seller and Vendor Central accounts in one place  
**So that** I don't have to log in manually to each account separately  

**Acceptance Criteria:**
- [ ] User can add new Seller Central accounts via SP-API credentials
- [ ] User can add new Vendor Central accounts via credentials
- [ ] System stores credentials securely (encrypted)
- [ ] User can view list of all connected accounts with status (active/inactive)
- [ ] User can remove/disconnect accounts
- [ ] System supports accounts across multiple EU marketplaces (IT, DE, FR, ES, UK, etc.)

**Priority:** 🔴 High  
**Story Points:** 8

---

### US-1.2: OTP Management
**As an** Account Manager  
**I want to** handle OTP authentication seamlessly  
**So that** I'm not blocked every time I need to access an account  

**Acceptance Criteria:**
- [ ] System caches authentication tokens where possible
- [ ] When OTP is required, user receives notification with input field
- [ ] OTP can be entered once and session maintained for extended period
- [ ] System logs authentication events for troubleshooting

**Priority:** 🔴 High  
**Story Points:** 5

---

### US-1.3: Account Health Dashboard
**As an** Account Manager  
**I want to** see the connection status of all accounts at a glance  
**So that** I know immediately if any account has issues  

**Acceptance Criteria:**
- [ ] Dashboard shows all accounts with connection status (green/yellow/red)
- [ ] Last sync timestamp displayed per account
- [ ] Alerts for accounts that haven't synced in >24 hours
- [ ] Quick-action button to re-authenticate problematic accounts

**Priority:** 🟡 Medium  
**Story Points:** 3

---

## Epic 2: Automated Data Extraction

### US-2.1: Scheduled Sales Report Download
**As a** Data Analyst  
**I want to** automatically download sales reports on a schedule  
**So that** I don't have to manually extract data every month  

**Acceptance Criteria:**
- [ ] User can configure download schedule (daily, weekly, monthly, custom)
- [ ] System downloads sales data for all connected accounts
- [ ] Data includes: units sold, revenue, order count, refunds
- [ ] Historical data stored in database (not just files)
- [ ] User receives notification when downloads complete
- [ ] Failed downloads trigger error notification with retry option

**Priority:** 🔴 High  
**Story Points:** 8

---

### US-2.2: Inventory Report Extraction
**As an** Account Manager  
**I want to** pull inventory/stock levels automatically  
**So that** I can monitor availability across all accounts  

**Acceptance Criteria:**
- [ ] System extracts current stock levels per SKU/ASIN
- [ ] Data includes: FBA inventory, inbound shipments, reserved units
- [ ] Supports both Seller and Vendor Central inventory formats
- [ ] Low stock alerts configurable per product threshold

**Priority:** 🔴 High  
**Story Points:** 5

---

### US-2.3: Advertising/PPC Data Extraction
**As a** Data Analyst  
**I want to** download advertising performance data automatically  
**So that** I can analyze campaign effectiveness  

**Acceptance Criteria:**
- [ ] System extracts Sponsored Products, Brands, and Display data
- [ ] Metrics include: impressions, clicks, CTR, spend, sales, ROAS, ACoS
- [ ] Data available at campaign, ad group, and keyword level
- [ ] Historical data stored beyond Amazon's 3-month limit
- [ ] Data refreshed daily for active campaigns

**Priority:** 🔴 High  
**Story Points:** 8

---

### US-2.4: BSR (Best Seller Rank) Tracking
**As a** Strategist  
**I want to** track BSR for products by category over time  
**So that** I can monitor competitive positioning  

**Acceptance Criteria:**
- [ ] User can add ASINs to track (client and competitor products)
- [ ] System captures BSR daily per category
- [ ] Historical BSR data stored for trend analysis
- [ ] BSR changes visualized in charts
- [ ] Alerts for significant BSR movements (e.g., >20% change)

**Priority:** 🟡 Medium  
**Story Points:** 5

---

### US-2.5: Competitor Data Collection
**As a** Strategist  
**I want to** track competitor products' performance  
**So that** I can benchmark against the market  

**Acceptance Criteria:**
- [ ] User can add competitor ASINs to monitor
- [ ] System tracks: price, BSR, review count, rating
- [ ] Price history stored for trend analysis
- [ ] Competitor data displayed alongside client data for comparison
- [ ] Alerts for competitor price changes

**Priority:** 🟡 Medium  
**Story Points:** 8

---

### US-2.6: Order Data Extraction
**As a** Data Analyst  
**I want to** extract order-level data  
**So that** I can analyze purchasing patterns  

**Acceptance Criteria:**
- [ ] System extracts order details (order ID, date, items, quantities, prices)
- [ ] Includes shipping status and delivery information
- [ ] Returns/refunds linked to original orders
- [ ] Data filterable by date range, marketplace, account

**Priority:** 🟡 Medium  
**Story Points:** 5

---

## Epic 3: Data Storage & Historical Analysis

### US-3.1: Long-Term Data Retention
**As a** Data Analyst  
**I want to** access historical data beyond Amazon's retention limits  
**So that** I can analyze long-term trends  

**Acceptance Criteria:**
- [ ] All extracted data stored in persistent database
- [ ] Data retained for minimum 24 months
- [ ] User can query data by any date range
- [ ] Ads data preserved beyond Amazon's 3-month limit
- [ ] Data exportable in full for backup purposes

**Priority:** 🔴 High  
**Story Points:** 8

---

### US-3.2: Period-Over-Period Comparison
**As a** Data Analyst  
**I want to** compare metrics across different time periods  
**So that** I can measure growth and identify trends  

**Acceptance Criteria:**
- [ ] User can select two date ranges for comparison
- [ ] System calculates % change for all KPIs
- [ ] Comparison available for: sales, units, returns, ROAS, CTR
- [ ] Visual indicators for positive/negative changes (green/red)
- [ ] Preset comparisons: MoM, QoQ, YoY

**Priority:** 🔴 High  
**Story Points:** 5

---

### US-3.3: Data Normalization Across Sources
**As a** Data Analyst  
**I want to** have consistent data even when Amazon changes formats  
**So that** historical comparisons remain accurate  

**Acceptance Criteria:**
- [ ] System normalizes data from different report versions
- [ ] Currency conversions applied consistently
- [ ] Marketplace differences handled (VAT, fees)
- [ ] Data validation flags anomalies for review

**Priority:** 🟡 Medium  
**Story Points:** 5

---

## Epic 4: KPI Dashboard & Visualization

### US-4.1: Unified Performance Dashboard
**As an** Account Manager  
**I want to** see all account performance in one aggregated view  
**So that** I can quickly assess overall business health  

**Acceptance Criteria:**
- [ ] Dashboard shows total revenue, units, orders across all accounts
- [ ] Filterable by: account, marketplace, date range, product category
- [ ] Key metrics displayed: Units Sold, Revenue, Returns, ROAS, CTR
- [ ] Sparkline trends for each metric
- [ ] Drill-down from aggregate to individual account

**Priority:** 🔴 High  
**Story Points:** 8

---

### US-4.2: Client vs Competitor View
**As a** Strategist  
**I want to** compare client performance against competitors  
**So that** I can identify competitive gaps and opportunities  

**Acceptance Criteria:**
- [ ] Side-by-side comparison of client vs competitor metrics
- [ ] Metrics: price, BSR, reviews, estimated sales
- [ ] Market share visualization (pie/bar chart)
- [ ] Gap analysis highlighting where client underperforms

**Priority:** 🟡 Medium  
**Story Points:** 5

---

### US-4.3: Advertising Performance Dashboard
**As a** Strategist  
**I want to** visualize advertising performance trends  
**So that** I can optimize campaign spending  

**Acceptance Criteria:**
- [ ] Charts showing ROAS, ACoS, CTR over time
- [ ] Campaign-level breakdown with sortable table
- [ ] Top performing and underperforming keywords highlighted
- [ ] Spend vs Revenue correlation visualization
- [ ] Alerts for campaigns below target ROAS

**Priority:** 🟡 Medium  
**Story Points:** 5

---

### US-4.4: Returns Analysis View
**As a** Data Analyst  
**I want to** analyze return rates and reasons  
**So that** I can identify product quality or listing issues  

**Acceptance Criteria:**
- [ ] Return rate calculated per product/account
- [ ] Return reasons categorized and displayed
- [ ] Trend visualization of returns over time
- [ ] Alerts for products with return rate >threshold

**Priority:** 🟢 Low  
**Story Points:** 3

---

## Epic 5: Export & Reporting

### US-5.1: Excel Export
**As a** Data Analyst  
**I want to** export data to Excel format  
**So that** I can perform custom analysis and share with stakeholders  

**Acceptance Criteria:**
- [ ] One-click export of any dashboard view to .xlsx
- [ ] Export includes all visible data with proper formatting
- [ ] Multiple sheets for different data categories
- [ ] Formulas preserved where applicable (e.g., % calculations)
- [ ] Custom date range selection for export

**Priority:** 🔴 High  
**Story Points:** 5

---

### US-5.2: Google Sheets Integration
**As a** Data Analyst  
**I want to** push data directly to Google Sheets  
**So that** I can collaborate with team members in real-time  

**Acceptance Criteria:**
- [ ] User can connect Google account
- [ ] Data can be exported to new or existing sheet
- [ ] Scheduled sync to update sheets automatically
- [ ] Sheet formatting maintained on updates

**Priority:** 🟡 Medium  
**Story Points:** 5

---

### US-5.3: PowerPoint Report Generation
**As a** Data Analyst  
**I want to** generate presentation-ready reports automatically  
**So that** I don't have to manually format data for client meetings  

**Acceptance Criteria:**
- [ ] User can select report template
- [ ] System populates template with current data
- [ ] Charts and tables auto-generated with branding
- [ ] Export as .pptx file
- [ ] Customizable sections (include/exclude metrics)

**Priority:** 🔴 High  
**Story Points:** 8

---

### US-5.4: Scheduled Report Delivery
**As an** Account Manager  
**I want to** schedule reports to be generated and sent automatically  
**So that** clients receive updates without manual effort  

**Acceptance Criteria:**
- [ ] User can schedule weekly/monthly reports per client
- [ ] Reports generated in selected format (Excel/PPT/PDF)
- [ ] Reports sent via email to configured recipients
- [ ] Delivery confirmation logged

**Priority:** 🟡 Medium  
**Story Points:** 5

---

## Epic 6: Catalog Management

### US-6.1: Bulk Product Listing Updates
**As an** Account Manager  
**I want to** update multiple product listings in bulk  
**So that** I can make changes efficiently across the catalog  

**Acceptance Criteria:**
- [ ] User can upload Excel file with listing changes
- [ ] System validates data before submission
- [ ] Supported fields: title, bullet points, description, backend keywords
- [ ] Changes pushed to Amazon via API
- [ ] Success/failure report generated per SKU

**Priority:** 🔴 High  
**Story Points:** 8

---

### US-6.2: Price Management
**As an** Account Manager  
**I want to** update prices across accounts and marketplaces  
**So that** I can maintain pricing strategy efficiently  

**Acceptance Criteria:**
- [ ] User can set prices per SKU per marketplace
- [ ] Bulk price upload via Excel
- [ ] Price change history tracked
- [ ] Validation against minimum/maximum price rules
- [ ] Competitor price comparison before submission

**Priority:** 🔴 High  
**Story Points:** 5

---

### US-6.3: Inventory/Availability Updates
**As an** Account Manager  
**I want to** update product availability status  
**So that** I can control what's shown as in-stock  

**Acceptance Criteria:**
- [ ] User can enable/disable products
- [ ] Bulk availability updates supported
- [ ] Quantity adjustments for merchant-fulfilled items
- [ ] Change log maintained

**Priority:** 🟡 Medium  
**Story Points:** 3

---

### US-6.4: Image Management
**As an** Account Manager  
**I want to** update product images in bulk  
**So that** I can refresh visual content across the catalog  

**Acceptance Criteria:**
- [ ] User can upload images mapped to SKUs
- [ ] Supported positions: main image, gallery images
- [ ] Image validation (size, format, Amazon requirements)
- [ ] Preview before submission
- [ ] Status report of successful/failed uploads

**Priority:** 🟡 Medium  
**Story Points:** 5

---

## Epic 7: Predictive Analytics & AI Recommendations

### US-7.1: Sales Trend Forecasting
**As a** Strategist  
**I want to** see predicted future sales based on historical data  
**So that** I can plan inventory and campaigns proactively  

**Acceptance Criteria:**
- [ ] System generates 30/60/90 day sales forecasts
- [ ] Forecasts based on historical trends and seasonality
- [ ] Confidence intervals displayed
- [ ] Forecast vs actual comparison for model validation
- [ ] Alerts when forecast indicates significant changes

**Priority:** 🔴 High (stated client priority)  
**Story Points:** 13

---

### US-7.2: Product Trend Prediction
**As a** Strategist  
**I want to** identify which products are trending up or down  
**So that** I can adjust strategy accordingly  

**Acceptance Criteria:**
- [ ] System calculates trend score per product
- [ ] Products ranked by trend momentum
- [ ] Visualization of trend direction and strength
- [ ] Alerts for products with declining trends

**Priority:** 🔴 High (stated client priority)  
**Story Points:** 8

---

### US-7.3: Listing Optimization Suggestions
**As an** Account Manager  
**I want to** receive AI-powered suggestions for listing improvements  
**So that** I can optimize content without manual analysis  

**Acceptance Criteria:**
- [ ] System analyzes listing content vs best practices
- [ ] Suggestions for: title, bullets, description, keywords
- [ ] Competitor comparison insights
- [ ] Priority score for each suggestion
- [ ] One-click implementation option

**Priority:** 🟡 Medium  
**Story Points:** 8

---

### US-7.4: Image Quality Assessment
**As an** Account Manager  
**I want to** receive feedback on product image quality  
**So that** I can identify images that need improvement  

**Acceptance Criteria:**
- [ ] System scores images on Amazon compliance
- [ ] Identifies issues: resolution, background, text overlays
- [ ] Comparison with competitor image quality
- [ ] Prioritized list of images to improve

**Priority:** 🟢 Low  
**Story Points:** 5

---

### US-7.5: Strategy Recommendations
**As a** Strategist  
**I want to** receive actionable strategy recommendations  
**So that** I can make data-driven decisions faster  

**Acceptance Criteria:**
- [ ] System generates weekly recommendations
- [ ] Categories: pricing, advertising, inventory, content
- [ ] Each recommendation includes rationale and expected impact
- [ ] User can mark recommendations as implemented/dismissed
- [ ] Track outcomes of implemented recommendations

**Priority:** 🟡 Medium  
**Story Points:** 8

---

## Epic 8: Alerts & Notifications

### US-8.1: Configurable Alerts
**As an** Account Manager  
**I want to** set up custom alerts for important events  
**So that** I'm notified immediately when action is needed  

**Acceptance Criteria:**
- [ ] Alert types: low stock, price changes, BSR drops, sync failures
- [ ] Configurable thresholds per alert type
- [ ] Delivery channels: email, in-app, SMS (optional)
- [ ] Alert history log
- [ ] Snooze/dismiss options

**Priority:** 🟡 Medium  
**Story Points:** 5

---

### US-8.2: Daily Summary Digest
**As an** Account Manager  
**I want to** receive a daily summary of key metrics and events  
**So that** I stay informed without checking the platform constantly  

**Acceptance Criteria:**
- [ ] Daily email with key metrics across all accounts
- [ ] Highlights: top sellers, biggest changes, alerts triggered
- [ ] Configurable delivery time
- [ ] Option to disable or customize content

**Priority:** 🟢 Low  
**Story Points:** 3

---

## Story Map Summary

| Epic | Stories | Total Points | Priority |
|------|---------|--------------|----------|
| 1. Multi-Account Auth | 3 | 16 | 🔴 High |
| 2. Data Extraction | 6 | 39 | 🔴 High |
| 3. Data Storage | 3 | 18 | 🔴 High |
| 4. KPI Dashboard | 4 | 21 | 🔴 High |
| 5. Export & Reporting | 4 | 23 | 🔴 High |
| 6. Catalog Management | 4 | 21 | 🟡 Medium |
| 7. Predictive Analytics | 5 | 42 | 🔴 High |
| 8. Alerts | 2 | 8 | 🟢 Low |
| **TOTAL** | **31** | **188** | |

---

## Suggested MVP Scope (Phase 1)

Based on client priorities, recommended MVP:

| Story ID | Story Name | Points |
|----------|------------|--------|
| US-1.1 | Centralized Account Connection | 8 |
| US-1.2 | OTP Management | 5 |
| US-2.1 | Scheduled Sales Report Download | 8 |
| US-2.3 | Advertising/PPC Data Extraction | 8 |
| US-3.1 | Long-Term Data Retention | 8 |
| US-3.2 | Period-Over-Period Comparison | 5 |
| US-4.1 | Unified Performance Dashboard | 8 |
| US-5.1 | Excel Export | 5 |
| US-7.1 | Sales Trend Forecasting | 13 |
| US-7.2 | Product Trend Prediction | 8 |
| **MVP Total** | | **76 points** |

---

## Technical Dependencies

1. **Amazon SP-API** - Required for Seller Central integration
2. **Amazon Vendor Central API** - Required for Vendor accounts
3. **Database** - PostgreSQL recommended for time-series data
4. **Authentication** - OAuth 2.0 for Amazon, secure credential storage
5. **Scheduler** - Cron or job queue for automated data extraction
6. **ML/Analytics** - Python (pandas, scikit-learn) or similar for forecasting

---

## Test Account for Development

| Field | Value |
|-------|-------|
| Email | assistente42@inthezon.com |
| Password | Bayerinsect-22 |
| Type | Seller Central (inactive) |
| OTP Contact | Gioia: +39 327 867 9673 |
| ⚠️ Restrictions | Read-only, no modifications |

---

*Document generated: January 2026*  
*For: Niuexa / Inthezon*
