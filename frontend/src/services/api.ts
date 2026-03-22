import axios from 'axios'
import type {
  User, AuthTokens, Organization,
  AmazonAccount, AccountSummary,
  DashboardKPIs, TrendData, SalesAggregated,
  CategorySalesData, HourlyOrdersData,
  Forecast, Product,
  InventoryReportItem, AdvertisingMetricsItem,
  ApiKeysUpdate, ApiKeysResponse,
  MarketResearchReport, MarketResearchListItem, CompetitorSuggestion,
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
        }
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

  getTopPerformers: async (params: {
    start_date: string
    end_date: string
    limit?: number
    account_ids?: string[]
  }): Promise<{
    by_revenue?: Array<{ asin: string; total_revenue: number; total_units: number }>
    by_units?: Array<{ asin: string; total_revenue: number; total_units: number }>
  }> => {
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
}

// Forecasts API
export const forecastsApi = {
  list: async (): Promise<Forecast[]> => {
    const response = await api.get('/forecasts')
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
  }): Promise<Product[]> => {
    const response = await api.get('/catalog/products', { params })
    return response.data
  },

  getProduct: async (asin: string): Promise<Product> => {
    const response = await api.get(`/catalog/products/${asin}`)
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
}

// Market Research API
export const marketResearchApi = {
  generate: async (params: {
    source_asin: string
    account_id: string
    language: string
    extra_competitor_asins?: string[]
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
}

export default api
