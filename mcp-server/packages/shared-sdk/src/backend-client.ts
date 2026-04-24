import { buildUrl, HttpError, toIsoDate, type QueryValue } from "./http.js";
import type {
  AccountSummary,
  AdsVsOrganicResponse,
  AdvertisingInsights,
  AdvertisingMetricsRecord,
  AlertListResponse,
  AlertRecord,
  AlertRule,
  AlertRuleInput,
  AlertSummaryResponse,
  AmazonAccount,
  AmazonAccountStatus,
  BinaryDownload,
  CategorySalesData,
  ComparisonMatrixResponse,
  ComparisonResponse,
  CreateAmazonAccountInput,
  DashboardKpis,
  ForecastExportJob,
  ForecastProductOption,
  ForecastRecord,
  HealthResponse,
  HourlyOrdersData,
  InventoryRecord,
  MarketResearchInput,
  MarketResearchListItem,
  MarketResearchReport,
  MarketSearchInput,
  MarketSearchResponse,
  OrderListResponse,
  OrganizationApiKeysResponse,
  OrganizationApiKeysUpdate,
  OrganizationProfile,
  ProductRecord,
  ProductTrendsResponse,
  QueryFilters,
  ReturnsAnalyticsResponse,
  SalesAggregate,
  SalesRecord,
  ScheduledReport,
  ScheduledReportInput,
  ScheduledReportRun,
  StrategicRecommendation,
  TokenResponse,
  TopPerformers,
  TrendSeries,
  UpdateAmazonAccountInput,
  UserProfile,
} from "./types.js";

interface ClientOptions {
  backendUrl: string;
  accessToken?: string;
  refreshToken?: string;
  onSessionUpdate?: (tokens: TokenResponse) => void;
}

interface RequestOptions {
  method?: string;
  query?: Record<string, QueryValue>;
  body?: unknown;
  headers?: Record<string, string>;
}

function filenameFromContentDisposition(value: string | null): string | undefined {
  if (!value) return undefined;
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(value);
  return match ? decodeURIComponent(match[1]) : undefined;
}

export class BackendClient {
  private readonly backendUrl: string;
  private accessToken?: string;
  private refreshToken?: string;
  private readonly onSessionUpdate?: (tokens: TokenResponse) => void;

  constructor(options: ClientOptions) {
    this.backendUrl = options.backendUrl;
    this.accessToken = options.accessToken;
    this.refreshToken = options.refreshToken;
    this.onSessionUpdate = options.onSessionUpdate;
  }

  getBaseUrl(): string {
    return this.backendUrl;
  }

  getTokens(): Pick<TokenResponse, "access_token" | "refresh_token"> {
    return {
      access_token: this.accessToken || "",
      refresh_token: this.refreshToken || "",
    };
  }

  // ---------------------------------------------------------------------------
  // Auth & org
  // ---------------------------------------------------------------------------

  async health(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/health", {}, false);
  }

  async register(input: { email: string; password: string; full_name?: string }): Promise<UserProfile> {
    return this.request<UserProfile>(
      "/api/v1/auth/register",
      { method: "POST", body: input },
      false,
    );
  }

  async login(input: { email: string; password: string }): Promise<TokenResponse> {
    const tokens = await this.request<TokenResponse>(
      "/api/v1/auth/login",
      { method: "POST", body: input },
      false,
    );
    this.updateTokens(tokens);
    return tokens;
  }

  async refreshSession(): Promise<TokenResponse> {
    if (!this.refreshToken) {
      throw new HttpError("No refresh token available. Run login again.", 401);
    }
    const tokens = await this.request<TokenResponse>(
      "/api/v1/auth/refresh",
      {
        method: "POST",
        query: { refresh_token: this.refreshToken },
      },
      false,
    );
    this.updateTokens(tokens);
    return tokens;
  }

  async getMe(): Promise<UserProfile> {
    return this.request<UserProfile>("/api/v1/auth/me");
  }

  async getOrganization(): Promise<OrganizationProfile> {
    return this.request<OrganizationProfile>("/api/v1/auth/organization");
  }

  async getOrganizationApiKeys(): Promise<OrganizationApiKeysResponse> {
    return this.request<OrganizationApiKeysResponse>("/api/v1/auth/organization/api-keys");
  }

  async updateOrganizationApiKeys(input: OrganizationApiKeysUpdate): Promise<OrganizationApiKeysResponse> {
    return this.request<OrganizationApiKeysResponse>("/api/v1/auth/organization/api-keys", {
      method: "PUT",
      body: input,
    });
  }

  // ---------------------------------------------------------------------------
  // Accounts
  // ---------------------------------------------------------------------------

  async listAccounts(): Promise<AmazonAccount[]> {
    return this.request<AmazonAccount[]>("/api/v1/accounts");
  }

  async getAccountsSummary(): Promise<AccountSummary> {
    return this.request<AccountSummary>("/api/v1/accounts/summary");
  }

  async getAccount(accountId: string): Promise<AmazonAccount> {
    return this.request<AmazonAccount>(`/api/v1/accounts/${accountId}`);
  }

  async createAccount(input: CreateAmazonAccountInput): Promise<AmazonAccount> {
    return this.request<AmazonAccount>("/api/v1/accounts", {
      method: "POST",
      body: input,
    });
  }

  async updateAccount(accountId: string, input: UpdateAmazonAccountInput): Promise<AmazonAccount> {
    return this.request<AmazonAccount>(`/api/v1/accounts/${accountId}`, {
      method: "PUT",
      body: input,
    });
  }

  async deleteAccount(accountId: string): Promise<void> {
    return this.request<void>(`/api/v1/accounts/${accountId}`, { method: "DELETE" });
  }

  async getAccountStatus(accountId: string): Promise<AmazonAccountStatus> {
    return this.request<AmazonAccountStatus>(`/api/v1/accounts/${accountId}/status`);
  }

  async testAccountConnection(accountId: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(`/api/v1/accounts/${accountId}/test-connection`, {
      method: "POST",
    });
  }

  async triggerAccountSync(accountId: string): Promise<AmazonAccountStatus> {
    return this.request<AmazonAccountStatus>(`/api/v1/accounts/${accountId}/sync`, {
      method: "POST",
    });
  }

  async syncAllAccounts(): Promise<AmazonAccountStatus[]> {
    return this.request<AmazonAccountStatus[]>("/api/v1/accounts/sync-all", { method: "POST" });
  }

  // ---------------------------------------------------------------------------
  // Reports
  // ---------------------------------------------------------------------------

  async getSales(filters: QueryFilters & { asins?: string[]; limit?: number; offset?: number }): Promise<SalesRecord[]> {
    return this.request<SalesRecord[]>("/api/v1/reports/sales", {
      query: {
        start_date: toIsoDate(filters.startDate),
        end_date: toIsoDate(filters.endDate),
        account_ids: filters.accountIds,
        asins: filters.asins,
        limit: filters.limit,
        offset: filters.offset,
      },
    });
  }

  async getSalesAggregated(filters: QueryFilters & { groupBy?: "day" | "week" | "month" }): Promise<SalesAggregate[]> {
    return this.request<SalesAggregate[]>("/api/v1/reports/sales/aggregated", {
      query: {
        start_date: toIsoDate(filters.startDate),
        end_date: toIsoDate(filters.endDate),
        account_ids: filters.accountIds,
        group_by: filters.groupBy,
      },
    });
  }

  async getOrders(filters: QueryFilters & {
    accountId?: string;
    orderStatus?: string;
    asin?: string;
    limit?: number;
    offset?: number;
  }): Promise<OrderListResponse> {
    return this.request<OrderListResponse>("/api/v1/reports/orders", {
      query: {
        start_date: toIsoDate(filters.startDate),
        end_date: toIsoDate(filters.endDate),
        account_id: filters.accountId,
        order_status: filters.orderStatus,
        asin: filters.asin,
        limit: filters.limit,
        offset: filters.offset,
      },
    });
  }

  async getInventory(filters: {
    snapshotDate?: string;
    startDate?: string;
    endDate?: string;
    accountIds?: string[];
    asins?: string[];
    lowStockOnly?: boolean;
    limit?: number;
  }): Promise<InventoryRecord[]> {
    return this.request<InventoryRecord[]>("/api/v1/reports/inventory", {
      query: {
        snapshot_date: toIsoDate(filters.snapshotDate),
        start_date: toIsoDate(filters.startDate),
        end_date: toIsoDate(filters.endDate),
        account_ids: filters.accountIds,
        asins: filters.asins,
        low_stock_only: filters.lowStockOnly,
        limit: filters.limit,
      },
    });
  }

  async getAdvertisingMetrics(filters: QueryFilters & {
    campaignTypes?: string[];
    limit?: number;
    offset?: number;
  }): Promise<AdvertisingMetricsRecord[]> {
    return this.request<AdvertisingMetricsRecord[]>("/api/v1/reports/advertising", {
      query: {
        start_date: toIsoDate(filters.startDate),
        end_date: toIsoDate(filters.endDate),
        account_ids: filters.accountIds,
        campaign_types: filters.campaignTypes,
        limit: filters.limit,
        offset: filters.offset,
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Scheduled reports
  // ---------------------------------------------------------------------------

  async listScheduledReports(): Promise<ScheduledReport[]> {
    return this.request<ScheduledReport[]>("/api/v1/reports/schedules");
  }

  async createScheduledReport(input: ScheduledReportInput): Promise<ScheduledReport> {
    return this.request<ScheduledReport>("/api/v1/reports/schedules", {
      method: "POST",
      body: input,
    });
  }

  async getScheduledReport(scheduleId: string): Promise<ScheduledReport> {
    return this.request<ScheduledReport>(`/api/v1/reports/schedules/${scheduleId}`);
  }

  async updateScheduledReport(scheduleId: string, input: Partial<ScheduledReportInput>): Promise<ScheduledReport> {
    return this.request<ScheduledReport>(`/api/v1/reports/schedules/${scheduleId}`, {
      method: "PUT",
      body: input,
    });
  }

  async toggleScheduledReport(scheduleId: string, enabled: boolean): Promise<ScheduledReport> {
    return this.request<ScheduledReport>(`/api/v1/reports/schedules/${scheduleId}/toggle`, {
      method: "POST",
      query: { enabled },
    });
  }

  async listScheduledReportRuns(scheduleId: string, limit = 20): Promise<ScheduledReportRun[]> {
    return this.request<ScheduledReportRun[]>(`/api/v1/reports/schedules/${scheduleId}/runs`, {
      query: { limit },
    });
  }

  async runScheduledReportNow(scheduleId: string): Promise<ScheduledReportRun> {
    return this.request<ScheduledReportRun>(`/api/v1/reports/schedules/${scheduleId}/run-now`, {
      method: "POST",
    });
  }

  async downloadScheduledRunArtifact(runId: string): Promise<BinaryDownload> {
    return this.requestBinary(`/api/v1/reports/schedules/runs/${runId}/download`);
  }

  // ---------------------------------------------------------------------------
  // Analytics
  // ---------------------------------------------------------------------------

  async getDashboard(filters: QueryFilters): Promise<DashboardKpis> {
    return this.request<DashboardKpis>("/api/v1/analytics/dashboard", {
      query: {
        start_date: toIsoDate(filters.startDate),
        end_date: toIsoDate(filters.endDate),
        account_ids: filters.accountIds,
      },
    });
  }

  async getTrends(filters: QueryFilters & { metrics: string[] }): Promise<TrendSeries[]> {
    return this.request<TrendSeries[]>("/api/v1/analytics/trends", {
      query: {
        start_date: toIsoDate(filters.startDate),
        end_date: toIsoDate(filters.endDate),
        account_ids: filters.accountIds,
        metrics: filters.metrics,
      },
    });
  }

  async getTopPerformers(filters: QueryFilters & { limit?: number }): Promise<TopPerformers> {
    return this.request<TopPerformers>("/api/v1/analytics/top-performers", {
      query: {
        start_date: toIsoDate(filters.startDate),
        end_date: toIsoDate(filters.endDate),
        account_ids: filters.accountIds,
        limit: filters.limit,
      },
    });
  }

  async getComparison(filters: {
    period1Start: string;
    period1End: string;
    period2Start: string;
    period2End: string;
    accountIds?: string[];
    category?: string;
    preset?: string;
  }): Promise<ComparisonResponse> {
    return this.request<ComparisonResponse>("/api/v1/analytics/comparison", {
      query: {
        period1_start: toIsoDate(filters.period1Start),
        period1_end: toIsoDate(filters.period1End),
        period2_start: toIsoDate(filters.period2Start),
        period2_end: toIsoDate(filters.period2End),
        account_ids: filters.accountIds,
        category: filters.category,
        preset: filters.preset,
      },
    });
  }

  async getProductTrends(filters: QueryFilters & {
    accountId?: string;
    asin?: string;
    trendClass?: string;
    language?: "en" | "it";
    limit?: number;
  }): Promise<ProductTrendsResponse> {
    return this.request<ProductTrendsResponse>("/api/v1/analytics/product-trends", {
      query: {
        start_date: toIsoDate(filters.startDate),
        end_date: toIsoDate(filters.endDate),
        account_id: filters.accountId,
        account_ids: filters.accountIds,
        asin: filters.asin,
        trend_class: filters.trendClass,
        language: filters.language,
        limit: filters.limit,
      },
    });
  }

  async getSalesByCategory(filters: QueryFilters & { category?: string; limit?: number }): Promise<CategorySalesData[]> {
    return this.request<CategorySalesData[]>("/api/v1/analytics/sales-by-category", {
      query: {
        start_date: toIsoDate(filters.startDate),
        end_date: toIsoDate(filters.endDate),
        account_ids: filters.accountIds,
        category: filters.category,
        limit: filters.limit,
      },
    });
  }

  async getOrdersByHour(filters: QueryFilters & { maxPagesPerAccount?: number }): Promise<HourlyOrdersData[]> {
    return this.request<HourlyOrdersData[]>("/api/v1/analytics/orders-by-hour", {
      query: {
        start_date: toIsoDate(filters.startDate),
        end_date: toIsoDate(filters.endDate),
        account_ids: filters.accountIds,
        max_pages_per_account: filters.maxPagesPerAccount,
      },
    });
  }

  async getAdvertisingInsights(filters: { startDate: string; endDate: string }): Promise<AdvertisingInsights> {
    return this.request<AdvertisingInsights>("/api/v1/analytics/advertising", {
      query: {
        start_date: toIsoDate(filters.startDate),
        end_date: toIsoDate(filters.endDate),
      },
    });
  }

  async getReturnsAnalytics(filters: {
    accountId?: string;
    accountIds?: string[];
    startDate?: string;
    endDate?: string;
    asin?: string;
    limit?: number;
  }): Promise<ReturnsAnalyticsResponse> {
    return this.request<ReturnsAnalyticsResponse>("/api/v1/analytics/returns", {
      query: {
        account_id: filters.accountId,
        account_ids: filters.accountIds,
        date_from: toIsoDate(filters.startDate),
        date_to: toIsoDate(filters.endDate),
        asin: filters.asin,
        limit: filters.limit,
      },
    });
  }

  async getAdsVsOrganic(filters: {
    accountId?: string;
    accountIds?: string[];
    startDate: string;
    endDate: string;
    groupBy?: "day" | "week" | "month";
    asin?: string;
  }): Promise<AdsVsOrganicResponse> {
    return this.request<AdsVsOrganicResponse>("/api/v1/analytics/ads-vs-organic", {
      query: {
        account_id: filters.accountId,
        account_ids: filters.accountIds,
        date_from: toIsoDate(filters.startDate),
        date_to: toIsoDate(filters.endDate),
        group_by: filters.groupBy,
        asin: filters.asin,
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Catalog
  // ---------------------------------------------------------------------------

  async listProducts(filters: { accountIds?: string[]; search?: string; category?: string; activeOnly?: boolean; limit?: number; offset?: number }): Promise<ProductRecord[]> {
    return this.request<ProductRecord[]>("/api/v1/catalog/products", {
      query: {
        account_ids: filters.accountIds,
        search: filters.search,
        category: filters.category,
        active_only: filters.activeOnly ?? true,
        limit: filters.limit,
        offset: filters.offset,
      },
    });
  }

  async getProduct(asin: string): Promise<ProductRecord> {
    return this.request<ProductRecord>(`/api/v1/catalog/products/${asin}`);
  }

  async updateProduct(asin: string, fields: { title?: string; brand?: string; category?: string; isActive?: boolean }): Promise<ProductRecord> {
    return this.request<ProductRecord>(`/api/v1/catalog/products/${asin}`, {
      method: "PUT",
      query: {
        title: fields.title,
        brand: fields.brand,
        category: fields.category,
        is_active: fields.isActive,
      },
    });
  }

  async bulkUpdatePrices(input: {
    accountId: string;
    updates: Array<{ asin?: string; sku?: string; price: number }>;
    productType?: string;
  }): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("/api/v1/catalog/prices", {
      method: "POST",
      body: {
        account_id: input.accountId,
        updates: input.updates,
        product_type: input.productType ?? "PRODUCT",
      },
    });
  }

  async updateProductAvailability(input: {
    asin: string;
    accountId: string;
    isAvailable: boolean;
    quantity?: number;
    productType?: string;
  }): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(`/api/v1/catalog/products/${input.asin}/availability`, {
      method: "PATCH",
      body: {
        account_id: input.accountId,
        is_available: input.isAvailable,
        quantity: input.quantity,
        product_type: input.productType ?? "PRODUCT",
      },
    });
  }

  async listProductImages(asin: string, accountId: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(`/api/v1/catalog/products/${asin}/images`, {
      query: { account_id: accountId },
    });
  }

  async deleteProductImage(asin: string, accountId: string, key: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(`/api/v1/catalog/products/${asin}/images`, {
      method: "DELETE",
      query: { account_id: accountId, key },
    });
  }

  // ---------------------------------------------------------------------------
  // Forecasts
  // ---------------------------------------------------------------------------

  async listForecasts(filters: { accountIds?: string[]; forecastType?: string; limit?: number }): Promise<ForecastRecord[]> {
    return this.request<ForecastRecord[]>("/api/v1/forecasts", {
      query: {
        account_ids: filters.accountIds,
        forecast_type: filters.forecastType,
        limit: filters.limit,
      },
    });
  }

  async getForecast(forecastId: string): Promise<ForecastRecord> {
    return this.request<ForecastRecord>(`/api/v1/forecasts/${forecastId}`);
  }

  async getProductForecast(asin: string): Promise<ForecastRecord> {
    return this.request<ForecastRecord>(`/api/v1/forecasts/products/${asin}`);
  }

  async listForecastableProducts(input: {
    accountId: string;
    lookbackDays?: number;
    minHistoryDays?: number;
    limit?: number;
  }): Promise<ForecastProductOption[]> {
    return this.request<ForecastProductOption[]>("/api/v1/forecasts/available-products", {
      query: {
        account_id: input.accountId,
        lookback_days: input.lookbackDays,
        min_history_days: input.minHistoryDays,
        limit: input.limit,
      },
    });
  }

  async generateForecast(input: { accountId: string; forecastType?: string; horizonDays?: number; asin?: string }): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("/api/v1/forecasts/generate", {
      method: "POST",
      query: {
        account_id: input.accountId,
        forecast_type: input.forecastType ?? "sales",
        horizon_days: input.horizonDays ?? 30,
        asin: input.asin,
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Alerts
  // ---------------------------------------------------------------------------

  async listAlertRules(): Promise<AlertRule[]> {
    return this.request<AlertRule[]>("/api/v1/alerts/rules");
  }

  async createAlertRule(input: AlertRuleInput): Promise<AlertRule> {
    return this.request<AlertRule>("/api/v1/alerts/rules", { method: "POST", body: input });
  }

  async getAlertRule(ruleId: string): Promise<AlertRule> {
    return this.request<AlertRule>(`/api/v1/alerts/rules/${ruleId}`);
  }

  async updateAlertRule(ruleId: string, input: Partial<AlertRuleInput>): Promise<AlertRule> {
    return this.request<AlertRule>(`/api/v1/alerts/rules/${ruleId}`, { method: "PUT", body: input });
  }

  async deleteAlertRule(ruleId: string): Promise<void> {
    return this.request<void>(`/api/v1/alerts/rules/${ruleId}`, { method: "DELETE" });
  }

  async getAlertSummary(): Promise<AlertSummaryResponse> {
    return this.request<AlertSummaryResponse>("/api/v1/alerts/summary");
  }

  async listAlerts(filters: {
    severity?: string;
    status?: "unread" | "read" | "all";
    type?: string;
    accountId?: string;
    asin?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<AlertListResponse> {
    return this.request<AlertListResponse>("/api/v1/alerts", {
      query: {
        severity: filters.severity,
        status: filters.status,
        type: filters.type,
        account_id: filters.accountId,
        asin: filters.asin,
        limit: filters.limit,
        offset: filters.offset,
      },
    });
  }

  async getUnreadAlertCount(): Promise<{ count: number }> {
    return this.request<{ count: number }>("/api/v1/alerts/unread-count");
  }

  async markAlertRead(alertId: string, read: boolean): Promise<{ item: AlertRecord; unread_count: number }> {
    return this.request<{ item: AlertRecord; unread_count: number }>(`/api/v1/alerts/${alertId}`, {
      method: "PATCH",
      body: { read },
    });
  }

  async bulkMarkAlerts(read: boolean, scope: "all" = "all"): Promise<{ updated: number; unread_count: number }> {
    return this.request<{ updated: number; unread_count: number }>("/api/v1/alerts", {
      method: "PATCH",
      body: { read, scope },
    });
  }

  // ---------------------------------------------------------------------------
  // Market research
  // ---------------------------------------------------------------------------

  async listMarketResearch(limit = 20, offset = 0): Promise<MarketResearchListItem[]> {
    return this.request<MarketResearchListItem[]>("/api/v1/market-research", {
      query: { limit, offset },
    });
  }

  async getMarketResearch(reportId: string): Promise<MarketResearchReport> {
    return this.request<MarketResearchReport>(`/api/v1/market-research/${reportId}`);
  }

  async generateMarketResearch(input: MarketResearchInput): Promise<MarketResearchReport> {
    return this.request<MarketResearchReport>("/api/v1/market-research/generate", {
      method: "POST",
      body: input,
    });
  }

  async refreshMarketResearch(reportId: string): Promise<MarketResearchReport> {
    return this.request<MarketResearchReport>(`/api/v1/market-research/${reportId}/refresh`, {
      method: "POST",
    });
  }

  async getMarketResearchMatrix(reportId: string): Promise<ComparisonMatrixResponse> {
    return this.request<ComparisonMatrixResponse>(`/api/v1/market-research/${reportId}/comparison-matrix`);
  }

  async deleteMarketResearch(reportId: string): Promise<{ status: string }> {
    return this.request<{ status: string }>(`/api/v1/market-research/${reportId}`, { method: "DELETE" });
  }

  async marketSearch(input: MarketSearchInput): Promise<MarketSearchResponse> {
    return this.request<MarketSearchResponse>("/api/v1/market-research/market-search", {
      method: "POST",
      body: input,
    });
  }

  async suggestCompetitors(filters: { category?: string; marketplace?: string } = {}): Promise<Array<Record<string, unknown>>> {
    return this.request<Array<Record<string, unknown>>>("/api/v1/market-research/competitors/suggest", {
      query: { category: filters.category, marketplace: filters.marketplace },
    });
  }

  // ---------------------------------------------------------------------------
  // Recommendations
  // ---------------------------------------------------------------------------

  async listRecommendations(filters: {
    status?: "pending" | "implemented" | "dismissed";
    category?: "pricing" | "advertising" | "inventory" | "content";
    accountId?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<StrategicRecommendation[]> {
    return this.request<StrategicRecommendation[]>("/api/v1/recommendations", {
      query: {
        status: filters.status,
        category: filters.category,
        account_id: filters.accountId,
        limit: filters.limit,
        offset: filters.offset,
      },
    });
  }

  async getRecommendation(recId: string): Promise<StrategicRecommendation> {
    return this.request<StrategicRecommendation>(`/api/v1/recommendations/${recId}`);
  }

  async updateRecommendationStatus(recId: string, input: {
    status: "pending" | "implemented" | "dismissed";
    outcomeNotes?: string;
  }): Promise<StrategicRecommendation> {
    return this.request<StrategicRecommendation>(`/api/v1/recommendations/${recId}`, {
      method: "PATCH",
      body: { status: input.status, outcome_notes: input.outcomeNotes },
    });
  }

  async generateRecommendations(input: {
    lookbackDays?: number;
    language?: "en" | "it";
    accountId?: string;
    asin?: string;
  } = {}): Promise<{ created_count: number; recommendations: StrategicRecommendation[] }> {
    return this.request<{ created_count: number; recommendations: StrategicRecommendation[] }>(
      "/api/v1/recommendations/generate",
      {
        method: "POST",
        body: {
          lookback_days: input.lookbackDays,
          language: input.language,
          account_id: input.accountId,
          asin: input.asin,
        },
      },
    );
  }

  // ---------------------------------------------------------------------------
  // Exports (binary)
  // ---------------------------------------------------------------------------

  async exportCsv(input: {
    reportType: "sales" | "inventory" | "advertising";
    startDate?: string;
    endDate?: string;
    accountIds?: string[];
    groupBy?: "day" | "week" | "month";
    lowStockOnly?: boolean;
    language?: "en" | "it";
    includeComparison?: boolean;
  }): Promise<BinaryDownload> {
    return this.requestBinary("/api/v1/exports/csv", {
      method: "POST",
      query: {
        report_type: input.reportType,
        start_date: toIsoDate(input.startDate),
        end_date: toIsoDate(input.endDate),
        account_ids: input.accountIds,
        group_by: input.groupBy,
        low_stock_only: input.lowStockOnly,
        language: input.language,
        include_comparison: input.includeComparison,
      },
    });
  }

  async exportBundle(input: {
    reportTypes: Array<"sales" | "inventory" | "advertising">;
    startDate?: string;
    endDate?: string;
    accountIds?: string[];
    groupBy?: "day" | "week" | "month";
    lowStockOnly?: boolean;
    language?: "en" | "it";
    includeComparison?: boolean;
  }): Promise<BinaryDownload> {
    return this.requestBinary("/api/v1/exports/bundle", {
      method: "POST",
      query: {
        report_types: input.reportTypes,
        start_date: toIsoDate(input.startDate),
        end_date: toIsoDate(input.endDate),
        account_ids: input.accountIds,
        group_by: input.groupBy,
        low_stock_only: input.lowStockOnly,
        language: input.language,
        include_comparison: input.includeComparison,
      },
    });
  }

  async exportExcelBundle(input: {
    reportTypes: Array<"sales" | "inventory" | "advertising">;
    startDate?: string;
    endDate?: string;
    accountIds?: string[];
    groupBy?: "day" | "week" | "month";
    lowStockOnly?: boolean;
    language?: "en" | "it";
    includeComparison?: boolean;
    template?: "clean" | "corporate" | "executive";
  }): Promise<BinaryDownload> {
    return this.requestBinary("/api/v1/exports/excel-bundle", {
      method: "POST",
      query: {
        report_types: input.reportTypes,
        start_date: toIsoDate(input.startDate),
        end_date: toIsoDate(input.endDate),
        account_ids: input.accountIds,
        group_by: input.groupBy,
        low_stock_only: input.lowStockOnly,
        language: input.language,
        include_comparison: input.includeComparison,
        template: input.template,
      },
    });
  }

  async exportExcel(input: {
    startDate?: string;
    endDate?: string;
    accountIds?: string[];
    includeSales?: boolean;
    includeAdvertising?: boolean;
  }): Promise<BinaryDownload> {
    return this.requestBinary("/api/v1/exports/excel", {
      method: "POST",
      query: {
        start_date: toIsoDate(input.startDate),
        end_date: toIsoDate(input.endDate),
        account_ids: input.accountIds,
        include_sales: input.includeSales,
        include_advertising: input.includeAdvertising,
      },
    });
  }

  async exportPowerPoint(input: {
    startDate?: string;
    endDate?: string;
    accountIds?: string[];
    template?: string;
  }): Promise<BinaryDownload> {
    return this.requestBinary("/api/v1/exports/powerpoint", {
      method: "POST",
      query: {
        start_date: toIsoDate(input.startDate),
        end_date: toIsoDate(input.endDate),
        account_ids: input.accountIds,
        template: input.template,
      },
    });
  }

  async exportForecastExcel(input: {
    forecastId: string;
    template?: "clean" | "corporate" | "executive";
    language?: "en" | "it";
  }): Promise<BinaryDownload> {
    return this.requestBinary("/api/v1/exports/forecast-excel", {
      method: "POST",
      query: {
        forecast_id: input.forecastId,
        template: input.template,
        language: input.language,
      },
    });
  }

  async createForecastPackageJob(input: {
    forecastId: string;
    template?: "clean" | "corporate" | "executive";
    language?: "en" | "it";
    includeInsights?: boolean;
  }): Promise<ForecastExportJob> {
    return this.request<ForecastExportJob>("/api/v1/exports/forecast-package", {
      method: "POST",
      body: {
        forecast_id: input.forecastId,
        template: input.template,
        language: input.language,
        include_insights: input.includeInsights,
      },
    });
  }

  async getForecastPackageJob(jobId: string): Promise<ForecastExportJob> {
    return this.request<ForecastExportJob>(`/api/v1/exports/forecast-package/${jobId}`);
  }

  async downloadForecastPackage(jobId: string): Promise<BinaryDownload> {
    return this.requestBinary(`/api/v1/exports/forecast-package/${jobId}/download`);
  }

  async exportMarketResearchPdf(input: {
    reportId: string;
    language?: "en" | "it";
    chartImages?: Record<string, string>;
  }): Promise<BinaryDownload> {
    return this.requestBinary("/api/v1/exports/market-research-pdf", {
      method: "POST",
      body: {
        report_id: input.reportId,
        language: input.language,
        chart_images: input.chartImages,
      },
    });
  }

  // ---------------------------------------------------------------------------
  // Internals
  // ---------------------------------------------------------------------------

  private updateTokens(tokens: TokenResponse): void {
    this.accessToken = tokens.access_token;
    this.refreshToken = tokens.refresh_token;
    this.onSessionUpdate?.(tokens);
  }

  private async request<T>(path: string, options: RequestOptions = {}, allowRefresh = true): Promise<T> {
    const headers = new Headers(options.headers);
    headers.set("accept", "application/json");

    let body: BodyInit | undefined;
    if (options.body !== undefined) {
      headers.set("content-type", "application/json");
      body = JSON.stringify(options.body);
    }

    if (this.accessToken) {
      headers.set("authorization", `Bearer ${this.accessToken}`);
    }

    const response = await fetch(buildUrl(this.backendUrl, path, options.query), {
      method: options.method ?? "GET",
      headers,
      body,
    });

    if (response.status === 401 && allowRefresh && this.refreshToken) {
      await this.refreshSession();
      return this.request<T>(path, options, false);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : await response.text();

    if (!response.ok) {
      const detail = typeof payload === "object" && payload !== null && "detail" in payload
        ? (payload as { detail?: unknown }).detail
        : payload;
      const message = typeof detail === "string" ? detail : `Request failed with status ${response.status}`;
      throw new HttpError(message, response.status, detail);
    }

    return payload as T;
  }

  private async requestBinary(path: string, options: RequestOptions = {}, allowRefresh = true): Promise<BinaryDownload> {
    const headers = new Headers(options.headers);
    headers.set("accept", "application/octet-stream, application/zip, application/pdf, */*");

    let body: BodyInit | undefined;
    if (options.body !== undefined) {
      headers.set("content-type", "application/json");
      body = JSON.stringify(options.body);
    }

    if (this.accessToken) {
      headers.set("authorization", `Bearer ${this.accessToken}`);
    }

    const response = await fetch(buildUrl(this.backendUrl, path, options.query), {
      method: options.method ?? "POST",
      headers,
      body,
    });

    if (response.status === 401 && allowRefresh && this.refreshToken) {
      await this.refreshSession();
      return this.requestBinary(path, options, false);
    }

    if (!response.ok) {
      const text = await response.text();
      let detail: unknown = text;
      try {
        detail = JSON.parse(text);
      } catch {
        // not json
      }
      const message = typeof detail === "object" && detail !== null && "detail" in detail
        ? String((detail as { detail?: unknown }).detail)
        : `Request failed with status ${response.status}`;
      throw new HttpError(message, response.status, detail);
    }

    const arrayBuffer = await response.arrayBuffer();
    const contentType = response.headers.get("content-type") || "application/octet-stream";
    const filename = filenameFromContentDisposition(response.headers.get("content-disposition"))
      || path.split("/").pop()
      || "download.bin";

    return {
      filename,
      contentType,
      bytes: new Uint8Array(arrayBuffer),
    };
  }
}
