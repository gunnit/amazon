export interface UserProfile {
  id: string;
  email: string;
  full_name?: string | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
}

export interface OrganizationProfile {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface OrganizationApiKeysResponse {
  sp_api_client_id?: string | null;
  sp_api_aws_access_key?: string | null;
  sp_api_role_arn?: string | null;
  has_client_secret: boolean;
  has_aws_secret_key: boolean;
}

export interface OrganizationApiKeysUpdate {
  sp_api_client_id?: string;
  sp_api_client_secret?: string;
  sp_api_aws_access_key?: string;
  sp_api_aws_secret_key?: string;
  sp_api_role_arn?: string;
}

export type AccountType = "seller" | "vendor";
export type SyncStatus = "pending" | "syncing" | "success" | "error" | string;

export interface AmazonAccount {
  id: string;
  organization_id: string;
  account_name: string;
  account_type: AccountType;
  marketplace_id: string;
  marketplace_country: string;
  advertising_profile_id?: string | null;
  is_active: boolean;
  last_sync_at?: string | null;
  sync_status: SyncStatus;
  sync_error_message?: string | null;
  last_sync_started_at?: string | null;
  last_sync_succeeded_at?: string | null;
  last_sync_failed_at?: string | null;
  last_sync_attempt_at?: string | null;
  last_sync_heartbeat_at?: string | null;
  sync_error_code?: string | null;
  sync_error_kind?: string | null;
  has_refresh_token: boolean;
  has_advertising_refresh_token: boolean;
  created_at: string;
  updated_at: string;
}

export interface AmazonAccountStatus {
  id: string;
  account_name: string;
  marketplace_country: string;
  sync_status: SyncStatus;
  last_sync_at?: string | null;
  sync_error_message?: string | null;
  total_sales_30d?: number;
  total_units_30d?: number;
  active_asins?: number;
}

export interface AccountSummary {
  total_accounts: number;
  active_accounts: number;
  syncing_accounts: number;
  error_accounts: number;
  accounts: AmazonAccountStatus[];
}

export interface CreateAmazonAccountInput {
  account_name: string;
  account_type: AccountType;
  marketplace_id: string;
  marketplace_country: string;
  refresh_token?: string;
  client_id?: string;
  client_secret?: string;
  advertising_profile_id?: string;
  advertising_refresh_token?: string;
  login_email?: string;
  login_password?: string;
}

export interface UpdateAmazonAccountInput {
  account_name?: string;
  is_active?: boolean;
  refresh_token?: string;
  client_id?: string;
  client_secret?: string;
  advertising_profile_id?: string;
  advertising_refresh_token?: string;
  login_email?: string;
  login_password?: string;
}

export interface MetricValue {
  value: number;
  previous_value?: number | null;
  change_percent?: number | null;
  trend: string;
  is_available?: boolean;
  unavailable_reason?: string | null;
}

export interface DashboardKpis {
  total_revenue: MetricValue;
  total_units: MetricValue;
  total_orders: MetricValue;
  average_order_value: MetricValue;
  return_rate: MetricValue;
  roas: MetricValue;
  acos: MetricValue;
  ctr: MetricValue;
  active_asins: number;
  accounts_synced: number;
  period_start: string;
  period_end: string;
}

export interface TrendPoint {
  date: string;
  value: number;
  label?: string | null;
}

export interface TrendSeries {
  metric_name: string;
  data_points: TrendPoint[];
  total: number;
  average: number;
  min_value: number;
  max_value: number;
}

export interface ProductRecord {
  id: string;
  account_id: string;
  asin: string;
  sku?: string | null;
  title?: string | null;
  brand?: string | null;
  category?: string | null;
  current_price?: number | null;
  current_bsr?: number | null;
  review_count?: number | null;
  rating?: number | null;
  is_active: boolean;
}

export interface ProductPerformance {
  asin: string;
  title?: string | null;
  sku?: string | null;
  total_units: number;
  total_revenue: number;
  total_orders: number;
  avg_price?: number | null;
  current_bsr?: number | null;
  bsr_change?: number | null;
  revenue_share: number;
}

export interface TopPerformers {
  by_revenue: ProductPerformance[];
  by_units: ProductPerformance[];
  by_growth: ProductPerformance[];
}

export interface ForecastPrediction {
  date: string;
  predicted_value: number;
  lower_bound: number;
  upper_bound: number;
}

export interface ForecastHistoricalPoint {
  date: string;
  value: number;
}

export interface ForecastRecord {
  id: string;
  account_id: string;
  asin?: string | null;
  forecast_type: string;
  generated_at: string;
  horizon_days: number;
  model_used: string;
  confidence_interval: number;
  predictions: ForecastPrediction[];
  historical_data?: ForecastHistoricalPoint[];
  mape?: number | null;
  rmse?: number | null;
  confidence_level?: number | null;
  data_quality_notes?: string[] | null;
}

export interface ForecastProductOption {
  asin: string;
  title?: string | null;
  history_days: number;
  last_sale_date?: string | null;
}

export interface SalesRecord {
  id: number;
  account_id: string;
  date: string;
  asin: string;
  sku?: string | null;
  units_ordered: number;
  units_ordered_b2b: number;
  ordered_product_sales: number;
  ordered_product_sales_b2b: number;
  total_order_items: number;
  currency: string;
}

export interface SalesAggregate {
  date: string;
  total_units: number;
  total_sales: number;
  total_orders: number;
  currency: string;
}

export interface InventoryRecord {
  id: number;
  account_id: string;
  snapshot_date: string;
  asin: string;
  sku?: string | null;
  fnsku?: string | null;
  afn_fulfillable_quantity: number;
  afn_inbound_working_quantity: number;
  afn_inbound_shipped_quantity: number;
  afn_reserved_quantity: number;
  afn_total_quantity: number;
  mfn_fulfillable_quantity: number;
}

export interface AdvertisingMetricsRecord {
  id: number;
  campaign_id: string;
  campaign_name: string;
  campaign_type: string;
  date: string;
  impressions: number;
  clicks: number;
  cost: number;
  attributed_sales_7d: number;
  attributed_units_ordered_7d: number;
  ctr?: number | null;
  cpc?: number | null;
  acos?: number | null;
  roas?: number | null;
}

export interface OrderItemRecord {
  id: number;
  asin?: string | null;
  sku?: string | null;
  title?: string | null;
  quantity: number;
  item_price?: number | null;
  item_tax?: number | null;
}

export interface OrderRecord {
  id: number;
  account_id: string;
  amazon_order_id: string;
  purchase_date: string;
  order_status: string;
  fulfillment_channel?: string | null;
  order_total?: number | null;
  currency?: string | null;
  marketplace_id?: string | null;
  number_of_items: number;
  created_at: string;
  items: OrderItemRecord[];
}

export interface OrderListResponse {
  items: OrderRecord[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export type AlertType =
  | "low_stock"
  | "bsr_drop"
  | "price_change"
  | "sync_failure"
  | "product_trend";
export type AlertSeverity = "info" | "warning" | "critical";
export type AlertStatus = "unread" | "read" | "all";

export interface AlertRule {
  id: string;
  organization_id: string;
  name: string;
  alert_type: AlertType;
  conditions: Record<string, unknown>;
  applies_to_accounts?: string[] | null;
  applies_to_asins?: string[] | null;
  notification_channels?: string[] | null;
  notification_emails?: string[] | null;
  webhook_url?: string | null;
  is_enabled: boolean;
  last_triggered_at?: string | null;
  alert_count: number;
}

export interface AlertRuleInput {
  name: string;
  alert_type: AlertType;
  conditions: Record<string, unknown>;
  applies_to_accounts?: string[];
  applies_to_asins?: string[];
  notification_channels?: string[];
  notification_emails?: string[];
  webhook_url?: string;
  is_enabled?: boolean;
}

export interface AlertRecord {
  id: string;
  rule_id: string;
  account_id?: string | null;
  asin?: string | null;
  event_kind: string;
  dedup_key: string;
  message: string;
  details: Record<string, unknown>;
  severity: AlertSeverity;
  is_read: boolean;
  triggered_at: string;
  last_seen_at: string;
  resolved_at?: string | null;
  notification_status?: string | null;
  rule_name?: string | null;
  alert_type?: AlertType | null;
}

export interface AlertListResponse {
  items: AlertRecord[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface AlertSummaryResponse {
  unread_count: number;
  critical_count: number;
  active_rule_count: number;
  total_rule_count: number;
}

export interface ComparisonMetric {
  metric_name: string;
  label: string;
  current_value?: number | null;
  previous_value?: number | null;
  change_percent?: number | null;
  trend: string;
  format: string;
  is_available: boolean;
  unavailable_reason?: string | null;
}

export interface ComparisonResponse {
  preset?: string | null;
  category?: string | null;
  period_1: { start: string; end: string };
  period_2: { start: string; end: string };
  metrics: ComparisonMetric[];
  daily_series?: Array<Record<string, unknown>> | null;
}

export interface CategorySalesData {
  category: string;
  total_revenue: number;
  total_units: number;
  total_orders: number;
}

export interface HourlyOrdersData {
  hour: number;
  orders: number;
}

export interface AdvertisingInsights {
  total_spend: number;
  total_sales: number;
  total_impressions: number;
  total_clicks: number;
  overall_roas: number;
  overall_acos: number;
  overall_ctr: number;
  top_campaigns: Array<Record<string, unknown>>;
  underperforming_campaigns: Array<Record<string, unknown>>;
  recommendations: string[];
}

export interface ProductTrendsResponse {
  summary: Record<string, unknown>;
  rising_products: Array<Record<string, unknown>>;
  declining_products: Array<Record<string, unknown>>;
  products: Array<Record<string, unknown>>;
  insights: Record<string, unknown>;
  generated_with_ai: boolean;
  ai_available: boolean;
}

export interface ReturnsAnalyticsResponse {
  summary: Record<string, unknown>;
  return_rate_over_time: Array<Record<string, unknown>>;
  reason_breakdown: Array<Record<string, unknown>>;
  top_asins_by_returns: Array<Record<string, unknown>>;
  top_asins_by_return_rate: Array<Record<string, unknown>>;
}

export interface AdsVsOrganicResponse {
  summary: Record<string, unknown>;
  time_series: Array<Record<string, unknown>>;
  asin_breakdown?: Array<Record<string, unknown>> | null;
  group_by: string;
  asin?: string | null;
  attribution_notes: string[];
}

export type ScheduledReportFrequency = "weekly" | "monthly";
export type ScheduledReportFormat = "excel" | "pdf";
export type ScheduledReportType = "sales" | "inventory" | "advertising";

export interface ScheduledReport {
  id: string;
  name: string;
  report_types: ScheduledReportType[];
  frequency: ScheduledReportFrequency;
  format: ScheduledReportFormat;
  timezone: string;
  account_ids: string[];
  recipients: string[];
  parameters: Record<string, unknown>;
  schedule_config: Record<string, unknown>;
  is_enabled: boolean;
  last_run_at?: string | null;
  last_run_status?: string | null;
  next_run_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduledReportInput {
  name: string;
  report_types: ScheduledReportType[];
  frequency: ScheduledReportFrequency;
  format: ScheduledReportFormat;
  timezone?: string;
  account_ids?: string[];
  recipients: string[];
  parameters?: Record<string, unknown>;
  schedule_config?: Record<string, unknown>;
  is_enabled?: boolean;
}

export interface ScheduledReportRun {
  id: string;
  scheduled_report_id: string;
  status: string;
  generation_status?: string | null;
  delivery_status?: string | null;
  progress_step?: string | null;
  error_message?: string | null;
  triggered_at: string;
  period_start: string;
  period_end: string;
  completed_at?: string | null;
  artifact_filename?: string | null;
  download_ready: boolean;
  recipients: string[];
}

export interface MarketResearchListItem {
  id: string;
  title?: string | null;
  source_asin?: string | null;
  status: string;
  language: string;
  created_at: string;
  competitor_count: number;
}

export interface MarketResearchReport {
  id: string;
  organization_id: string;
  account_id: string;
  source_asin?: string | null;
  marketplace?: string | null;
  language: string;
  title?: string | null;
  status: string;
  progress_step?: string | null;
  progress_pct: number;
  error_message?: string | null;
  product_snapshot?: Record<string, unknown> | null;
  competitor_data?: Array<Record<string, unknown>> | null;
  ai_analysis?: Record<string, unknown> | null;
  created_at: string;
  completed_at?: string | null;
  last_refreshed_at?: string | null;
}

export interface MarketResearchInput {
  account_id: string;
  source_asin?: string;
  language?: "en" | "it";
  extra_competitor_asins?: string[];
  market_competitor_asins?: string[];
  search_query?: string;
  search_type?: "keyword" | "brand" | "asin";
}

export interface ComparisonMatrixResponse {
  dimensions: Array<Record<string, unknown>>;
  overall_score: number;
  opportunities: Array<"price" | "bsr" | "reviews" | "rating">;
}

export interface MarketSearchInput {
  account_id: string;
  search_type: "keyword" | "brand" | "asin";
  query: string;
  language?: "en" | "it";
}

export interface MarketSearchResponse {
  results: Array<Record<string, unknown>>;
  total_found: number;
  query: string;
  search_type: string;
}

export interface StrategicRecommendation {
  id: string;
  organization_id: string;
  account_id?: string | null;
  category: "pricing" | "advertising" | "inventory" | "content";
  priority: "high" | "medium" | "low";
  priority_score: number;
  title: string;
  rationale: string;
  expected_impact?: string | null;
  context?: Record<string, unknown> | null;
  status: "pending" | "implemented" | "dismissed";
  implemented_at?: string | null;
  dismissed_at?: string | null;
  outcome_notes?: string | null;
  generated_by: string;
  generated_at: string;
  created_at: string;
  updated_at: string;
}

export interface ForecastExportJob {
  id: string;
  forecast_id: string;
  status: string;
  progress_step?: string | null;
  progress_pct: number;
  error_message?: string | null;
  include_insights: boolean;
  template: string;
  language: string;
  download_ready: boolean;
  created_at: string;
  completed_at?: string | null;
}

export interface HealthResponse {
  status: string;
  version: string;
  environment: string;
}

export interface LocalState {
  backendUrl: string;
  accessToken?: string;
  refreshToken?: string;
  user?: UserProfile;
  organization?: OrganizationProfile;
  lastLoginAt?: string;
  selectedAccountIds?: string[];
  exportsDir?: string;
}

export interface QueryFilters {
  startDate?: string;
  endDate?: string;
  accountIds?: string[];
}

export interface BinaryDownload {
  filename: string;
  contentType: string;
  bytes: Uint8Array;
}
