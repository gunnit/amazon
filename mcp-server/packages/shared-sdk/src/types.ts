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
  is_active: boolean;
  last_sync_at?: string | null;
  sync_status: SyncStatus;
  sync_error_message?: string | null;
  has_refresh_token: boolean;
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

export interface CreateAmazonAccountInput {
  account_name: string;
  account_type: AccountType;
  marketplace_id: string;
  marketplace_country: string;
  refresh_token?: string;
  login_email?: string;
  login_password?: string;
}

export interface MetricValue {
  value: number;
  previous_value?: number | null;
  change_percent?: number | null;
  trend: string;
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
  mape?: number | null;
  rmse?: number | null;
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
}

export interface QueryFilters {
  startDate?: string;
  endDate?: string;
  accountIds?: string[];
}
