import axios from 'axios'
import type {
  User, AuthTokens, Organization,
  AmazonAccount, AccountSummary,
  DashboardKPIs, TrendData, SalesAggregated, ComparisonResponse,
  AdsVsOrganicResponse,
  CategorySalesData, HourlyOrdersData, ProductTrendsResponse, ReturnsAnalyticsResponse, TopPerformersResponse,
  Forecast, Product,
  ForecastExportJob,
  ForecastProductOption,
  InventoryReportItem, AdvertisingMetricsItem,
  ScheduledReport, ScheduledReportRun,
  GoogleSheetsConnection, GoogleSheetsSync, GoogleSheetsSyncRun,
  ApiKeysUpdate, ApiKeysResponse,
  MarketResearchReport, MarketResearchListItem, ComparisonMatrixResponse, MarketSearchResponse, CompetitorSuggestion,
  AlertRule, AlertBulkMutationResponse, AlertListResponse, AlertMutationResponse, AlertStatus, AlertSummary, AlertType,
} from '@/types'

const API_URL = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
  paramsSerializer: {
    // FastAPI expects repeated keys for arrays: ?account_ids=a&account_ids=b
    indexes: null,
  },
})

// Request interceptor to add auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor for token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // 403 from HTTPBearer means no/invalid Authorization header — redirect to login
    if (error.response?.status === 403 && !originalRequest._retry) {
      const token = localStorage.getItem('access_token')
      if (!token) {
        window.location.href = '/login'
        return new Promise(() => {})
      }
    }

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const response = await axios.post(`${API_URL}/api/v1/auth/refresh`, null, {
            params: { refresh_token: refreshToken },
          })
          const { access_token, refresh_token } = response.data

          localStorage.setItem('access_token', access_token)
          localStorage.setItem('refresh_token', refresh_token)

          originalRequest.headers.Authorization = `Bearer ${access_token}`
          return api(originalRequest)
        } catch (refreshError) {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
          return new Promise(() => {})
        }
      } else {
        localStorage.removeItem('access_token')
        window.location.href = '/login'
        return new Promise(() => {})
      }
    }

    return Promise.reject(error)
  }
)

// Auth API
export const authApi = {
  login: async (email: string, password: string): Promise<AuthTokens> => {
    const response = await api.post('/auth/login', { email, password })
    return response.data
  },

  register: async (email: string, password: string, full_name?: string): Promise<User> => {
    const response = await api.post('/auth/register', { email, password, full_name })
    return response.data
  },

  getCurrentUser: async (): Promise<User> => {
    const response = await api.get('/auth/me')
    return response.data
  },

  updateProfile: async (data: { email?: string; full_name?: string }): Promise<User> => {
    const response = await api.put('/auth/me', data)
    return response.data
  },

  changePassword: async (currentPassword: string, newPassword: string): Promise<void> => {
    await api.put('/auth/me/password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
  },

  getNotificationPreferences: async (): Promise<{
    daily_digest: boolean
    alert_emails: boolean
    sync_notifications: boolean
  }> => {
    const response = await api.get('/auth/me/notifications')
    return response.data
  },

  updateNotificationPreferences: async (data: {
    daily_digest: boolean
    alert_emails: boolean
    sync_notifications: boolean
  }): Promise<void> => {
    await api.put('/auth/me/notifications', data)
  },

  deleteAccount: async (): Promise<void> => {
    await api.delete('/auth/me')
  },

  getOrganization: async (): Promise<Organization> => {
    const response = await api.get('/auth/organization')
    return response.data
  },

  getApiKeys: async (): Promise<ApiKeysResponse> => {
    const response = await api.get('/auth/organization/api-keys')
    return response.data
  },

  updateApiKeys: async (data: ApiKeysUpdate): Promise<ApiKeysResponse> => {
    const response = await api.put('/auth/organization/api-keys', data)
    return response.data
  },

  deleteApiKeys: async (): Promise<ApiKeysResponse> => {
    const response = await api.delete('/auth/organization/api-keys')
    return response.data
  },
}

// Accounts API
export const accountsApi = {
  list: async (): Promise<AmazonAccount[]> => {
    const response = await api.get('/accounts')
    return response.data
  },

  getSummary: async (): Promise<AccountSummary> => {
    const response = await api.get('/accounts/summary')
    return response.data
  },

  create: async (data: Partial<AmazonAccount>): Promise<AmazonAccount> => {
    const response = await api.post('/accounts', data)
    return response.data
  },

  get: async (id: string): Promise<AmazonAccount> => {
    const response = await api.get(`/accounts/${id}`)
    return response.data
  },

  update: async (id: string, data: Partial<AmazonAccount>): Promise<AmazonAccount> => {
    const response = await api.put(`/accounts/${id}`, data)
    return response.data
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/accounts/${id}`)
  },

  triggerSync: async (id: string): Promise<void> => {
    await api.post(`/accounts/${id}/sync`)
  },
}

// Reports API
export const reportsApi = {
  getSalesAggregated: async (params: {
    start_date: string
    end_date: string
    account_ids?: string[]
    group_by?: string
  }): Promise<SalesAggregated[]> => {
    const response = await api.get('/reports/sales/aggregated', { params })
    return response.data
  },

  getInventory: async (params?: {
    snapshot_date?: string
    account_ids?: string[]
    low_stock_only?: boolean
  }): Promise<InventoryReportItem[]> => {
    const response = await api.get('/reports/inventory', { params })
    return response.data
  },

  getAdvertising: async (params: {
    start_date: string
    end_date: string
    account_ids?: string[]
  }): Promise<AdvertisingMetricsItem[]> => {
    const response = await api.get('/reports/advertising', { params })
    return response.data
  },

  listSchedules: async (): Promise<ScheduledReport[]> => {
    const response = await api.get('/reports/schedules')
    return response.data
  },

  createSchedule: async (data: {
    name: string
    report_types: string[]
    frequency: 'weekly' | 'monthly'
    format: 'excel' | 'pdf'
    timezone: string
    account_ids: string[]
    recipients: string[]
    parameters: {
      group_by: 'day' | 'week' | 'month'
      low_stock_only: boolean
      language: 'en' | 'it'
      include_comparison: boolean
    }
    schedule_config: Record<string, unknown>
    is_enabled: boolean
  }): Promise<ScheduledReport> => {
    const response = await api.post('/reports/schedules', data)
    return response.data
  },

  updateSchedule: async (scheduleId: string, data: Partial<{
    name: string
    report_types: string[]
    frequency: 'weekly' | 'monthly'
    format: 'excel' | 'pdf'
    timezone: string
    account_ids: string[]
    recipients: string[]
    parameters: {
      group_by: 'day' | 'week' | 'month'
      low_stock_only: boolean
      language: 'en' | 'it'
      include_comparison: boolean
    }
    schedule_config: Record<string, unknown>
    is_enabled: boolean
  }>): Promise<ScheduledReport> => {
    const response = await api.put(`/reports/schedules/${scheduleId}`, data)
    return response.data
  },

  toggleSchedule: async (scheduleId: string, enabled: boolean): Promise<ScheduledReport> => {
    const response = await api.post(`/reports/schedules/${scheduleId}/toggle`, null, {
      params: { enabled },
    })
    return response.data
  },

  listScheduleRuns: async (scheduleId: string, limit = 20): Promise<ScheduledReportRun[]> => {
    const response = await api.get(`/reports/schedules/${scheduleId}/runs`, { params: { limit } })
    return response.data
  },

  runScheduleNow: async (scheduleId: string): Promise<ScheduledReportRun> => {
    const response = await api.post(`/reports/schedules/${scheduleId}/run-now`)
    return response.data
  },

  downloadScheduleRun: async (runId: string): Promise<Blob> => {
    const response = await api.get(`/reports/schedules/runs/${runId}/download`, {
      responseType: 'blob',
    })
    return response.data
  },
}

export const googleSheetsApi = {
  getAuthUrl: async (): Promise<string> => {
    const response = await api.get('/google-sheets/oauth/authorize')
    return response.data.auth_url
  },

  getConnection: async (): Promise<GoogleSheetsConnection | null> => {
    try {
      const response = await api.get('/google-sheets/connection')
      return response.data
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        return null
      }
      throw error
    }
  },

  disconnect: async (): Promise<void> => {
    await api.delete('/google-sheets/connection')
  },

  exportToSheets: async (data: {
    data_types: string[]
    start_date: string
    end_date: string
    account_ids?: string[]
    spreadsheet_id?: string
    name?: string
    language?: 'en' | 'it'
    group_by?: 'day' | 'week' | 'month'
    parameters?: Record<string, unknown>
  }): Promise<{
    spreadsheet_id: string
    spreadsheet_url: string
    sheets_created: string[]
  }> => {
    const response = await api.post('/google-sheets/export', data)
    return response.data
  },

  listSyncs: async (): Promise<GoogleSheetsSync[]> => {
    const response = await api.get('/google-sheets/syncs')
    return response.data
  },

  createSync: async (data: {
    name: string
    data_types: string[]
    frequency: 'daily' | 'weekly'
    sync_mode: 'overwrite' | 'append'
    account_ids: string[]
    parameters: Record<string, unknown>
    schedule_config: Record<string, unknown>
    timezone: string
  }): Promise<GoogleSheetsSync> => {
    const response = await api.post('/google-sheets/syncs', data)
    return response.data
  },

  updateSync: async (
    syncId: string,
    data: Partial<{
      name: string
      data_types: string[]
      frequency: 'daily' | 'weekly'
      sync_mode: 'overwrite' | 'append'
      account_ids: string[]
      parameters: Record<string, unknown>
      schedule_config: Record<string, unknown>
      timezone: string
      is_enabled: boolean
    }>
  ): Promise<GoogleSheetsSync> => {
    const response = await api.put(`/google-sheets/syncs/${syncId}`, data)
    return response.data
  },

  toggleSync: async (syncId: string, enabled: boolean): Promise<GoogleSheetsSync> => {
    const response = await api.post(`/google-sheets/syncs/${syncId}/toggle`, null, {
      params: { enabled },
    })
    return response.data
  },

  deleteSync: async (syncId: string): Promise<void> => {
    await api.delete(`/google-sheets/syncs/${syncId}`)
  },

  runSyncNow: async (syncId: string): Promise<GoogleSheetsSyncRun> => {
    const response = await api.post(`/google-sheets/syncs/${syncId}/run-now`)
    return response.data
  },

  listSyncRuns: async (syncId: string, limit = 20): Promise<GoogleSheetsSyncRun[]> => {
    const response = await api.get(`/google-sheets/syncs/${syncId}/runs`, {
      params: { limit },
    })
    return response.data
  },
}

// Analytics API
export const analyticsApi = {
  getDashboard: async (params: {
    start_date: string
    end_date: string
    account_ids?: string[]
  }): Promise<DashboardKPIs> => {
    const response = await api.get('/analytics/dashboard', { params })
    return response.data
  },

  getTrends: async (params: {
    metrics: string[]
    start_date: string
    end_date: string
    account_ids?: string[]
  }): Promise<TrendData[]> => {
    const response = await api.get('/analytics/trends', { params })
    return response.data
  },

  getComparison: async (params: {
    period1_start: string
    period1_end: string
    period2_start: string
    period2_end: string
    preset?: 'mom' | 'qoq' | 'yoy'
    category?: string
    account_ids?: string[]
  }): Promise<ComparisonResponse> => {
    const response = await api.get('/analytics/comparison', { params })
    return response.data
  },

  getAdsVsOrganic: async (params: {
    date_from: string
    date_to: string
    group_by?: 'day' | 'week' | 'month'
    account_id?: string
    account_ids?: string[]
    asin?: string
  }): Promise<AdsVsOrganicResponse> => {
    const response = await api.get('/analytics/ads-vs-organic', { params })
    return response.data
  },

  getTopPerformers: async (params: {
    start_date: string
    end_date: string
    limit?: number
    account_ids?: string[]
  }): Promise<TopPerformersResponse> => {
    const response = await api.get('/analytics/top-performers', { params })
    return response.data
  },

  getSalesByCategory: async (params: {
    start_date: string
    end_date: string
    account_ids?: string[]
    category?: string
    limit?: number
  }): Promise<CategorySalesData[]> => {
    const response = await api.get('/analytics/sales-by-category', { params })
    return response.data
  },

  getOrdersByHour: async (params: {
    start_date: string
    end_date: string
    account_ids?: string[]
  }): Promise<HourlyOrdersData[]> => {
    const response = await api.get('/analytics/orders-by-hour', { params })
    return response.data
  },

  getProductTrends: async (params: {
    start_date: string
    end_date: string
    account_id?: string
    account_ids?: string[]
    asin?: string
    trend_class?: 'rising_fast' | 'rising' | 'stable' | 'declining' | 'declining_fast'
    language?: 'en' | 'it'
    limit?: number
  }): Promise<ProductTrendsResponse> => {
    const response = await api.get('/analytics/product-trends', { params })
    return response.data
  },

  getReturnsAnalysis: async (params: {
    account_id?: string
    account_ids?: string[]
    date_from?: string
    date_to?: string
    asin?: string
    limit?: number
  }): Promise<ReturnsAnalyticsResponse> => {
    const response = await api.get('/analytics/returns', { params })
    return response.data
  },
}

// Forecasts API
export const forecastsApi = {
  list: async (): Promise<Forecast[]> => {
    const response = await api.get('/forecasts')
    return response.data
  },

  getAvailableProducts: async (account_id: string): Promise<ForecastProductOption[]> => {
    const response = await api.get('/forecasts/available-products', {
      params: { account_id },
    })
    return response.data
  },

  generate: async (params: {
    account_id: string
    forecast_type?: string
    horizon_days?: number
    asin?: string
  }): Promise<{ id: string; status: string }> => {
    const response = await api.post('/forecasts/generate', null, { params })
    return response.data
  },

  get: async (id: string): Promise<Forecast> => {
    const response = await api.get(`/forecasts/${id}`)
    return response.data
  },
}

// Catalog API
export const catalogApi = {
  getProducts: async (params?: {
    search?: string
    category?: string
    active_only?: boolean
    limit?: number
    account_ids?: string[]
  }): Promise<Product[]> => {
    const response = await api.get('/catalog/products', { params })
    return response.data
  },

  getProduct: async (asin: string): Promise<Product> => {
    const response = await api.get(`/catalog/products/${asin}`)
    return response.data
  },

  updateProduct: async (
    asin: string,
    params: {
      title?: string
      brand?: string
      category?: string
      is_active?: boolean
    },
  ): Promise<Product> => {
    const response = await api.put(`/catalog/products/${asin}`, null, { params })
    return response.data
  },

  downloadBulkTemplate: async (): Promise<Blob> => {
    const response = await api.get('/catalog/bulk-update/template', { responseType: 'blob' })
    return response.data
  },

  bulkUpdate: async (params: {
    account_id: string
    product_type?: string
    file: File
  }): Promise<Record<string, unknown>> => {
    const form = new FormData()
    form.append('file', params.file)
    const response = await api.post('/catalog/bulk-update', form, {
      params: {
        account_id: params.account_id,
        product_type: params.product_type ?? 'PRODUCT',
      },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },

  updatePrices: async (payload: {
    account_id: string
    product_type?: string
    updates: Array<{ asin?: string; sku?: string; price: number }>
  }): Promise<Record<string, unknown>> => {
    const response = await api.post('/catalog/prices', {
      account_id: payload.account_id,
      product_type: payload.product_type ?? 'PRODUCT',
      updates: payload.updates,
    })
    return response.data
  },

  updateAvailability: async (
    asin: string,
    payload: {
      account_id: string
      is_available: boolean
      quantity?: number
      product_type?: string
    },
  ): Promise<Record<string, unknown>> => {
    const response = await api.patch(`/catalog/products/${asin}/availability`, {
      account_id: payload.account_id,
      is_available: payload.is_available,
      quantity: payload.quantity,
      product_type: payload.product_type ?? 'PRODUCT',
    })
    return response.data
  },
}

// Catalog Images API
export interface ProductImage {
  key: string
  url: string
  filename: string
  is_main?: boolean
}

export interface UploadImagesResponse {
  account_id: string
  asin: string
  uploaded: ProductImage[]
  main_image_url: string | null
  other_image_urls: string[]
  sp_api_result: Record<string, unknown> | null
  sp_api_error: string | null
}

export const imagesApi = {
  list: async (asin: string, accountId: string): Promise<{ asin: string; account_id: string; images: ProductImage[] }> => {
    const response = await api.get(`/catalog/products/${asin}/images`, {
      params: { account_id: accountId },
    })
    return response.data
  },

  upload: async (params: {
    asin: string
    account_id: string
    files: File[]
    main_index?: number
    push_to_amazon?: boolean
    product_type?: string
  }): Promise<UploadImagesResponse> => {
    const form = new FormData()
    form.append('account_id', params.account_id)
    form.append('product_type', params.product_type ?? 'PRODUCT')
    form.append('push_to_amazon', String(params.push_to_amazon ?? true))
    if (params.main_index !== undefined) {
      form.append('main_index', String(params.main_index))
    }
    for (const file of params.files) {
      form.append('files', file)
    }
    const response = await api.post(`/catalog/products/${params.asin}/images`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },

  remove: async (asin: string, accountId: string, key: string): Promise<{ deleted: string }> => {
    const response = await api.delete(`/catalog/products/${asin}/images`, {
      params: { account_id: accountId, key },
    })
    return response.data
  },
}

// Strategic Recommendations API
export interface StrategicRecommendation {
  id: string
  organization_id: string
  account_id: string | null
  created_by_id: string | null
  category: 'pricing' | 'advertising' | 'inventory' | 'content'
  priority: 'high' | 'medium' | 'low'
  priority_score: number
  title: string
  rationale: string
  expected_impact: string | null
  context: Record<string, unknown> | null
  status: 'pending' | 'implemented' | 'dismissed'
  implemented_at: string | null
  dismissed_at: string | null
  outcome_notes: string | null
  generated_by: string
  generated_at: string
  created_at: string
  updated_at: string
}

export const recommendationsApi = {
  list: async (params?: {
    status?: 'pending' | 'implemented' | 'dismissed'
    category?: 'pricing' | 'advertising' | 'inventory' | 'content'
    account_id?: string
    limit?: number
    offset?: number
  }): Promise<StrategicRecommendation[]> => {
    const response = await api.get('/recommendations', { params })
    return response.data
  },

  get: async (id: string): Promise<StrategicRecommendation> => {
    const response = await api.get(`/recommendations/${id}`)
    return response.data
  },

  updateStatus: async (
    id: string,
    payload: {
      status: 'pending' | 'implemented' | 'dismissed'
      outcome_notes?: string
    },
  ): Promise<StrategicRecommendation> => {
    const response = await api.patch(`/recommendations/${id}`, payload)
    return response.data
  },

  generate: async (payload?: {
    lookback_days?: number
    language?: 'en' | 'it'
    account_id?: string
    asin?: string
  }): Promise<{ created_count: number; recommendations: StrategicRecommendation[] }> => {
    const response = await api.post('/recommendations/generate', payload ?? {})
    return response.data
  },
}

// Exports API
export const exportsApi = {
  exportExcel: async (params: {
    start_date: string
    end_date: string
    include_sales?: boolean
    include_advertising?: boolean
    account_ids?: string[]
  }): Promise<Blob> => {
    const response = await api.post('/exports/excel', null, {
      params,
      responseType: 'blob',
    })
    return response.data
  },

  exportPowerPoint: async (params: {
    start_date: string
    end_date: string
    account_ids?: string[]
  }): Promise<Blob> => {
    const response = await api.post('/exports/powerpoint', null, {
      params,
      responseType: 'blob',
    })
    return response.data
  },

  exportBundle: async (params: {
    report_types: string[]
    start_date: string
    end_date: string
    account_ids?: string[]
    group_by?: string
    low_stock_only?: boolean
    language?: 'en' | 'it'
    include_comparison?: boolean
  }): Promise<Blob> => {
    const response = await api.post('/exports/bundle', null, {
      params,
      responseType: 'blob',
    })
    return response.data
  },

  exportExcelBundle: async (params: {
    report_types: string[]
    start_date: string
    end_date: string
    account_ids?: string[]
    group_by?: string
    low_stock_only?: boolean
    language?: 'en' | 'it'
    include_comparison?: boolean
    template?: 'clean' | 'corporate' | 'executive'
  }): Promise<Blob> => {
    const response = await api.post('/exports/excel-bundle', null, {
      params,
      responseType: 'blob',
    })
    return response.data
  },

  exportCsvPackage: async (params: {
    report_type: 'sales' | 'inventory' | 'advertising'
    start_date: string
    end_date: string
    account_ids?: string[]
    group_by?: string
    low_stock_only?: boolean
    language?: 'en' | 'it'
    include_comparison?: boolean
  }): Promise<Blob> => {
    const response = await api.post('/exports/csv', null, {
      params,
      responseType: 'blob',
    })
    return response.data
  },

  exportForecastExcel: async (params: {
    forecast_id: string
    template?: 'clean' | 'corporate' | 'executive'
    language?: 'en' | 'it'
  }): Promise<Blob> => {
    const response = await api.post('/exports/forecast-excel', null, {
      params,
      responseType: 'blob',
    })
    return response.data
  },

  createForecastPackage: async (params: {
    forecast_id: string
    template?: 'clean' | 'corporate' | 'executive'
    language?: 'en' | 'it'
    include_insights: boolean
  }): Promise<ForecastExportJob> => {
    const response = await api.post('/exports/forecast-package', params)
    return response.data
  },

  getForecastPackage: async (jobId: string): Promise<ForecastExportJob> => {
    const response = await api.get(`/exports/forecast-package/${jobId}`)
    return response.data
  },

  downloadForecastPackage: async (jobId: string): Promise<Blob> => {
    const response = await api.get(`/exports/forecast-package/${jobId}/download`, {
      responseType: 'blob',
    })
    return response.data
  },

  exportMarketResearchPdf: async (params: {
    report_id: string
    language: string
    chart_images?: Record<string, string>
  }): Promise<Blob> => {
    const response = await api.post('/exports/market-research-pdf', params, {
      responseType: 'blob',
    })
    return response.data
  },
}

// Market Research API
export const marketResearchApi = {
  generate: async (params: {
    source_asin?: string
    account_id: string
    language: string
    extra_competitor_asins?: string[]
    market_competitor_asins?: string[]
    search_query?: string
    search_type?: string
  }): Promise<MarketResearchReport> => {
    const response = await api.post('/market-research/generate', params)
    return response.data
  },

  list: async (params?: { limit?: number; offset?: number }): Promise<MarketResearchListItem[]> => {
    const response = await api.get('/market-research', { params })
    return response.data
  },

  get: async (id: string): Promise<MarketResearchReport> => {
    const response = await api.get(`/market-research/${id}`)
    return response.data
  },

  getComparisonMatrix: async (id: string): Promise<ComparisonMatrixResponse> => {
    const response = await api.get(`/market-research/${id}/comparison-matrix`)
    return response.data
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/market-research/${id}`)
  },

  suggestCompetitors: async (params: {
    category?: string
    marketplace?: string
  }): Promise<CompetitorSuggestion[]> => {
    const response = await api.get('/market-research/competitors/suggest', { params })
    return response.data
  },

  marketSearch: async (params: {
    account_id: string
    search_type: string
    query: string
    language?: string
  }): Promise<MarketSearchResponse> => {
    const response = await api.post('/market-research/market-search', params)
    return response.data
  },
}

export const alertsApi = {
  getSummary: async (): Promise<AlertSummary> => {
    const response = await api.get('/alerts/summary')
    return response.data
  },

  listRules: async (): Promise<AlertRule[]> => {
    const response = await api.get('/alerts/rules')
    return response.data
  },

  createRule: async (data: {
    name: string
    alert_type: AlertType
    conditions: Record<string, unknown>
    applies_to_accounts?: string[] | null
    applies_to_asins?: string[] | null
    notification_channels?: string[]
    notification_emails?: string[] | null
    webhook_url?: string | null
  }): Promise<AlertRule> => {
    const response = await api.post('/alerts/rules', data)
    return response.data
  },

  updateRule: async (id: string, data: Partial<AlertRule>): Promise<AlertRule> => {
    const response = await api.put(`/alerts/rules/${id}`, data)
    return response.data
  },

  deleteRule: async (id: string): Promise<void> => {
    await api.delete(`/alerts/rules/${id}`)
  },

  getAlerts: async (params?: {
    severity?: string
    status?: AlertStatus
    type?: AlertType
    account_id?: string
    asin?: string
    limit?: number
    offset?: number
  }): Promise<AlertListResponse> => {
    const response = await api.get('/alerts', { params })
    return response.data
  },

  getHistory: async (params?: {
    severity?: string
    status?: AlertStatus
    type?: AlertType
    account_id?: string
    asin?: string
    limit?: number
    offset?: number
  }): Promise<AlertListResponse> => {
    return alertsApi.getAlerts(params)
  },

  updateAlertReadState: async (id: string, read = true): Promise<AlertMutationResponse> => {
    const response = await api.patch(`/alerts/${id}`, { read })
    return response.data
  },

  markAsRead: async (id: string): Promise<AlertMutationResponse> => {
    return alertsApi.updateAlertReadState(id, true)
  },

  markAllAsRead: async (): Promise<AlertBulkMutationResponse> => {
    const response = await api.patch('/alerts', { read: true, scope: 'all' })
    return response.data
  },

  getUnreadCount: async (): Promise<{ count: number }> => {
    const response = await api.get('/alerts/unread-count')
    return response.data
  },
}

export default api
