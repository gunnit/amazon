import axios from 'axios'
import type {
  User, AuthTokens, Organization,
  AmazonAccount, AccountSummary,
  DashboardKPIs, TrendData, SalesAggregated,
  Forecast, Product,
  ApiKeysUpdate, ApiKeysResponse,
} from '@/types'
import {
  createMockAccount,
  createMockForecast,
  deleteMockAccount,
  getMockAccountSummary,
  getMockAccounts,
  getMockAdvertising,
  getMockApiKeys,
  getMockDashboardKPIs,
  getMockExport,
  getMockForecast,
  getMockForecasts,
  getMockInventory,
  getMockProduct,
  getMockProducts,
  getMockSalesAggregated,
  getMockTopPerformers,
  getMockTrends,
  triggerMockSync,
  updateMockAccount,
  updateMockApiKeys,
} from '@/mocks/mockData'
import { isMockDataEnabled } from '@/store/demoStore'

const API_URL = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
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

  getOrganization: async (): Promise<Organization> => {
    const response = await api.get('/auth/organization')
    return response.data
  },

  getApiKeys: async (): Promise<ApiKeysResponse> => {
    if (isMockDataEnabled()) return getMockApiKeys()
    const response = await api.get('/auth/organization/api-keys')
    return response.data
  },

  updateApiKeys: async (data: ApiKeysUpdate): Promise<ApiKeysResponse> => {
    if (isMockDataEnabled()) return updateMockApiKeys(data)
    const response = await api.put('/auth/organization/api-keys', data)
    return response.data
  },
}

// Accounts API
export const accountsApi = {
  list: async (): Promise<AmazonAccount[]> => {
    if (isMockDataEnabled()) return getMockAccounts()
    const response = await api.get('/accounts')
    return response.data
  },

  getSummary: async (): Promise<AccountSummary> => {
    if (isMockDataEnabled()) return getMockAccountSummary()
    const response = await api.get('/accounts/summary')
    return response.data
  },

  create: async (data: Partial<AmazonAccount>): Promise<AmazonAccount> => {
    if (isMockDataEnabled()) return createMockAccount(data)
    const response = await api.post('/accounts', data)
    return response.data
  },

  get: async (id: string): Promise<AmazonAccount> => {
    if (isMockDataEnabled()) {
      const account = getMockAccounts().find((item) => item.id === id)
      return account || getMockAccounts()[0]
    }
    const response = await api.get(`/accounts/${id}`)
    return response.data
  },

  update: async (id: string, data: Partial<AmazonAccount>): Promise<AmazonAccount> => {
    if (isMockDataEnabled()) return updateMockAccount(id, data)
    const response = await api.put(`/accounts/${id}`, data)
    return response.data
  },

  delete: async (id: string): Promise<void> => {
    if (isMockDataEnabled()) return deleteMockAccount(id)
    await api.delete(`/accounts/${id}`)
  },

  triggerSync: async (id: string): Promise<void> => {
    if (isMockDataEnabled()) return triggerMockSync(id)
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
    if (isMockDataEnabled()) return getMockSalesAggregated(params)
    const response = await api.get('/reports/sales/aggregated', { params })
    return response.data
  },

  getInventory: async (params?: {
    snapshot_date?: string
    account_ids?: string[]
    low_stock_only?: boolean
  }): Promise<unknown[]> => {
    if (isMockDataEnabled()) return getMockInventory(params)
    const response = await api.get('/reports/inventory', { params })
    return response.data
  },

  getAdvertising: async (params: {
    start_date: string
    end_date: string
    account_ids?: string[]
  }): Promise<unknown[]> => {
    if (isMockDataEnabled()) return getMockAdvertising()
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
    if (isMockDataEnabled()) return getMockDashboardKPIs(params)
    const response = await api.get('/analytics/dashboard', { params })
    return response.data
  },

  getTrends: async (params: {
    metrics: string[]
    start_date: string
    end_date: string
    account_ids?: string[]
  }): Promise<TrendData[]> => {
    if (isMockDataEnabled()) return getMockTrends(params)
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
    if (isMockDataEnabled()) return getMockTopPerformers(params.limit)
    const response = await api.get('/analytics/top-performers', { params })
    return response.data
  },
}

// Forecasts API
export const forecastsApi = {
  list: async (): Promise<Forecast[]> => {
    if (isMockDataEnabled()) return getMockForecasts()
    const response = await api.get('/forecasts')
    return response.data
  },

  generate: async (params: {
    account_id: string
    forecast_type?: string
    horizon_days?: number
    asin?: string
  }): Promise<{ id: string; status: string }> => {
    if (isMockDataEnabled()) return createMockForecast(params)
    const response = await api.post('/forecasts/generate', null, { params })
    return response.data
  },

  get: async (id: string): Promise<Forecast> => {
    if (isMockDataEnabled()) return getMockForecast(id)
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
    if (isMockDataEnabled()) return getMockProducts(params)
    const response = await api.get('/catalog/products', { params })
    return response.data
  },

  getProduct: async (asin: string): Promise<Product> => {
    if (isMockDataEnabled()) return getMockProduct(asin)
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
  }): Promise<Blob> => {
    if (isMockDataEnabled()) return getMockExport('excel')
    const response = await api.post('/exports/excel', null, {
      params,
      responseType: 'blob',
    })
    return response.data
  },

  exportPowerPoint: async (params: {
    start_date: string
    end_date: string
  }): Promise<Blob> => {
    if (isMockDataEnabled()) return getMockExport('powerpoint')
    const response = await api.post('/exports/powerpoint', null, {
      params,
      responseType: 'blob',
    })
    return response.data
  },
}

export default api
