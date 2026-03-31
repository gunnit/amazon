// User types
export interface User {
  id: string
  email: string
  full_name: string | null
  is_active: boolean
  is_superuser: boolean
  created_at: string
}

export interface Organization {
  id: string
  name: string
  slug: string
  timezone: string
  created_at: string
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
}

// Amazon Account types
export type AccountType = 'seller' | 'vendor'
export type SyncStatus = 'pending' | 'syncing' | 'success' | 'error'

export interface AmazonAccount {
  id: string
  organization_id: string
  account_name: string
  account_type: AccountType
  marketplace_id: string
  marketplace_country: string
  is_active: boolean
  last_sync_at: string | null
  sync_status: SyncStatus
  sync_error_message: string | null
  has_refresh_token: boolean
  created_at: string
  updated_at: string
}

export interface AccountSummary {
  total_accounts: number
  active_accounts: number
  syncing_accounts: number
  error_accounts: number
  accounts: AccountStatus[]
}

export interface AccountStatus {
  id: string
  account_name: string
  marketplace_country: string
  sync_status: SyncStatus
  last_sync_at: string | null
  sync_error_message: string | null
  total_sales_30d: number
  total_units_30d: number
  active_asins: number
}

// Analytics types
export interface MetricValue {
  value: number
  previous_value: number | null
  change_percent: number | null
  trend: 'up' | 'down' | 'stable'
  is_available?: boolean
  unavailable_reason?: string | null
}

export interface DashboardKPIs {
  total_revenue: MetricValue
  total_units: MetricValue
  total_orders: MetricValue
  average_order_value: MetricValue
  return_rate: MetricValue
  roas: MetricValue
  acos: MetricValue
  ctr: MetricValue
  active_asins: number
  accounts_synced: number
  period_start: string
  period_end: string
}

export interface TrendDataPoint {
  date: string
  value: number
}

export interface TrendData {
  metric_name: string
  data_points: TrendDataPoint[]
  total: number
  average: number
  min_value: number
  max_value: number
}

export interface ComparisonPeriod {
  start: string
  end: string
}

export interface ComparisonMetric {
  metric_name: 'revenue' | 'units' | 'orders' | 'returns' | 'roas' | 'ctr'
  label: string
  current_value: number | null
  previous_value: number | null
  change_percent: number | null
  trend: 'up' | 'down' | 'stable'
  format: 'currency' | 'number' | 'percent' | 'ratio'
  is_available: boolean
  unavailable_reason: string | null
}

export interface ComparisonResponse {
  preset: 'mom' | 'qoq' | 'yoy' | null
  category: string | null
  period_1: ComparisonPeriod
  period_2: ComparisonPeriod
  metrics: ComparisonMetric[]
}

export interface CategorySalesData {
  category: string
  total_revenue: number
  total_units: number
  total_orders: number
}

export interface TopPerformerData {
  asin: string
  title: string | null
  total_revenue: number
  total_units: number
  total_orders: number
}

export interface TopPerformersResponse {
  by_revenue: TopPerformerData[]
  by_units: TopPerformerData[]
}

export interface HourlyOrdersData {
  hour: number
  orders: number
}

export type TrendDirection = 'up' | 'down' | 'stable'
export type TrendStrength = 'weak' | 'moderate' | 'strong'
export type TrendDataQuality = 'high' | 'medium' | 'low'

export interface ProductTrendRecommendation {
  priority: 'high' | 'medium' | 'low'
  action: string
  rationale: string
  expected_impact: string
}

export interface ProductTrendInsights {
  summary: string
  key_trends: string[]
  risks: string[]
  opportunities: string[]
  recommendations: ProductTrendRecommendation[]
}

export interface ProductTrendItem {
  asin: string
  title: string | null
  category: string | null
  trend_score: number
  direction: TrendDirection
  strength: TrendStrength
  current_revenue: number
  previous_revenue: number
  current_units: number
  previous_units: number
  revenue_change_percent: number
  units_change_percent: number
  current_bsr: number | null
  previous_bsr: number | null
  bsr_change_percent: number | null
  data_quality: TrendDataQuality
  reason_tags: string[]
}

export interface ProductTrendSummary {
  eligible_products: number
  rising_count: number
  declining_count: number
  stable_count: number
  average_trend_score: number
  strongest_riser: ProductTrendItem | null
  strongest_decliner: ProductTrendItem | null
}

export interface ProductTrendsResponse {
  summary: ProductTrendSummary
  rising_products: ProductTrendItem[]
  declining_products: ProductTrendItem[]
  insights: ProductTrendInsights
  generated_with_ai: boolean
  ai_available: boolean
}

// Sales data types
export interface SalesData {
  id: number
  account_id: string
  date: string
  asin: string
  sku: string | null
  units_ordered: number
  units_ordered_b2b: number
  ordered_product_sales: number
  ordered_product_sales_b2b: number
  total_order_items: number
  currency: string
}

export interface SalesAggregated {
  date: string
  total_units: number
  total_sales: number
  total_orders: number
  currency: string
}

export interface InventoryReportItem {
  id: number
  account_id: string
  snapshot_date: string
  asin: string
  sku: string | null
  fnsku: string | null
  afn_fulfillable_quantity: number
  afn_inbound_working_quantity: number
  afn_inbound_shipped_quantity: number
  afn_reserved_quantity: number
  afn_total_quantity: number
  mfn_fulfillable_quantity: number
}

export interface AdvertisingMetricsItem {
  id: number
  campaign_id: string
  campaign_name: string
  campaign_type: string
  date: string
  impressions: number
  clicks: number
  cost: number | string
  attributed_sales_7d: number | string
  attributed_units_ordered_7d: number
  ctr: number | string | null
  cpc: number | string | null
  acos: number | string | null
  roas: number | string | null
}

export type ScheduledReportType = 'sales' | 'inventory' | 'advertising'
export type ScheduledReportFrequency = 'weekly' | 'monthly'
export type ScheduledReportFormat = 'excel' | 'pdf'
export type ScheduledReportRunStatus = 'pending' | 'processing' | 'generated' | 'delivered' | 'failed'

export interface ScheduledReportParameters {
  group_by: 'day' | 'week' | 'month'
  low_stock_only: boolean
  language: 'en' | 'it'
  include_comparison: boolean
}

export interface ScheduledReport {
  id: string
  name: string
  report_types: ScheduledReportType[]
  frequency: ScheduledReportFrequency
  format: ScheduledReportFormat
  timezone: string
  account_ids: string[]
  recipients: string[]
  parameters: ScheduledReportParameters
  schedule_config: Record<string, unknown>
  is_enabled: boolean
  last_run_at: string | null
  last_run_status: string | null
  next_run_at: string | null
  created_at: string
  updated_at: string
}

export interface ScheduledReportRun {
  id: string
  scheduled_report_id: string
  status: ScheduledReportRunStatus
  generation_status: string
  delivery_status: string
  progress_step: string | null
  error_message: string | null
  triggered_at: string
  period_start: string
  period_end: string
  completed_at: string | null
  artifact_filename: string | null
  download_ready: boolean
  recipients: string[]
}

// Product types
export interface Product {
  id: string
  account_id: string
  asin: string
  sku: string | null
  title: string | null
  brand: string | null
  category: string | null
  current_price: number | null
  current_bsr: number | null
  review_count: number | null
  rating: number | null
  is_active: boolean
}

// Forecast types
export interface ForecastPrediction {
  date: string
  predicted_value: number
  lower_bound: number
  upper_bound: number
}

export interface ForecastProductOption {
  asin: string
  title: string | null
  history_days: number
  last_sale_date: string | null
}

export interface ForecastHistoricalPoint {
  date: string
  value: number
}

export interface Forecast {
  id: string
  account_id: string
  asin: string | null
  forecast_type: string
  generated_at: string
  horizon_days: number
  model_used: string
  confidence_interval: number
  predictions: ForecastPrediction[]
  historical_data: ForecastHistoricalPoint[]
  mape: number | null
  rmse: number | null
}

export interface ForecastExportJob {
  id: string
  forecast_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress_step: string | null
  progress_pct: number
  error_message: string | null
  include_insights: boolean
  template: 'clean' | 'corporate' | 'executive'
  language: 'en' | 'it'
  download_ready: boolean
  created_at: string
  completed_at: string | null
}

// Market Research types
export interface ProductSnapshot {
  asin: string
  title: string | null
  brand: string | null
  category: string | null
  price: number | null
  bsr: number | null
  review_count: number | null
  rating: number | null
}

export interface CompetitorSnapshot extends ProductSnapshot {}

export interface AIRecommendation {
  area: string
  priority: 'high' | 'medium' | 'low'
  action: string
  expected_impact: string
}

export interface AIAnalysis {
  strengths: string[]
  weaknesses: string[]
  recommendations: AIRecommendation[]
  overall_score: number
  summary: string
}

export interface MarketResearchReport {
  id: string
  organization_id: string
  account_id: string
  source_asin: string
  marketplace: string | null
  language: 'en' | 'it'
  title: string | null
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress_step: string | null
  progress_pct: number
  error_message: string | null
  product_snapshot: ProductSnapshot | null
  competitor_data: CompetitorSnapshot[] | null
  ai_analysis: AIAnalysis | null
  created_at: string
  completed_at: string | null
}

export interface MarketResearchListItem {
  id: string
  title: string | null
  source_asin: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  language: 'en' | 'it'
  created_at: string
  competitor_count: number
}

// Market Tracker 360 types
export interface MarketSearchResult {
  asin: string
  title: string | null
  brand: string | null
  category: string | null
  price: number | null
  bsr: number | null
  review_count: number | null
  rating: number | null
}

export interface MarketSearchResponse {
  results: MarketSearchResult[]
  total_found: number
  query: string
  search_type: string
  error?: string
  error_code?: string
}

export interface CompetitorSuggestion {
  asin: string
  title: string | null
  brand: string | null
  marketplace: string
  current_price: number | null
  current_bsr: number | null
  review_count: number | null
  rating: number | null
}

// Alert types
export interface AlertRule {
  id: string
  organization_id: string
  name: string
  alert_type: string
  conditions: Record<string, unknown>
  applies_to_accounts: string[] | null
  applies_to_asins: string[] | null
  notification_channels: string[] | null
  notification_emails: string[] | null
  webhook_url: string | null
  is_enabled: boolean
}

// Organization API Keys
export interface ApiKeysUpdate {
  sp_api_client_id?: string
  sp_api_client_secret?: string
  sp_api_aws_access_key?: string
  sp_api_aws_secret_key?: string
  sp_api_role_arn?: string
}

export interface ApiKeysResponse {
  sp_api_client_id: string | null
  sp_api_aws_access_key: string | null
  sp_api_role_arn: string | null
  has_client_secret: boolean
  has_aws_secret_key: boolean
}
