import { buildUrl, HttpError, toIsoDate, type QueryValue } from "./http.js";
import type {
  AmazonAccount,
  AmazonAccountStatus,
  CreateAmazonAccountInput,
  DashboardKpis,
  ForecastRecord,
  HealthResponse,
  OrganizationApiKeysResponse,
  OrganizationApiKeysUpdate,
  OrganizationProfile,
  ProductRecord,
  QueryFilters,
  SalesAggregate,
  SalesRecord,
  TokenResponse,
  TopPerformers,
  TrendSeries,
  UserProfile,
  InventoryRecord,
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

  async listAccounts(): Promise<AmazonAccount[]> {
    return this.request<AmazonAccount[]>("/api/v1/accounts");
  }

  async createAccount(input: CreateAmazonAccountInput): Promise<AmazonAccount> {
    return this.request<AmazonAccount>("/api/v1/accounts", {
      method: "POST",
      body: input,
    });
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

  async getInventory(filters: { snapshotDate?: string; accountIds?: string[]; asins?: string[]; lowStockOnly?: boolean; limit?: number }): Promise<InventoryRecord[]> {
    return this.request<InventoryRecord[]>("/api/v1/reports/inventory", {
      query: {
        snapshot_date: toIsoDate(filters.snapshotDate),
        account_ids: filters.accountIds,
        asins: filters.asins,
        low_stock_only: filters.lowStockOnly,
        limit: filters.limit,
      },
    });
  }

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

  async listForecasts(filters: { accountIds?: string[]; forecastType?: string; limit?: number }): Promise<ForecastRecord[]> {
    return this.request<ForecastRecord[]>("/api/v1/forecasts", {
      query: {
        account_ids: filters.accountIds,
        forecast_type: filters.forecastType,
        limit: filters.limit,
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
}
