import type {
  DashboardKPIs,
  TrendData,
  TrendDataPoint,
  AccountSummary,
  AccountStatus,
  AmazonAccount,
  SalesAggregated,
  Forecast,
  ForecastPrediction,
  Product,
} from '@/types'
import {
  startOfWeek,
  startOfMonth,
  format as fnsFormat,
} from 'date-fns'

const DAY_MS = 24 * 60 * 60 * 1000

const parseDate = (value: string): Date => new Date(`${value}T00:00:00Z`)
const formatDate = (date: Date): string => date.toISOString().split('T')[0]
const addDays = (date: Date, days: number): Date => new Date(date.getTime() + days * DAY_MS)

const buildDateSeries = (start: string, end: string): string[] => {
  const startDate = parseDate(start)
  const endDate = parseDate(end)
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    const today = new Date()
    return [formatDate(today)]
  }

  const dates: string[] = []
  let current = startDate
  let guard = 0
  while (current <= endDate && guard < 400) {
    dates.push(formatDate(current))
    current = addDays(current, 1)
    guard += 1
  }
  return dates.length ? dates : [formatDate(new Date())]
}

const buildTrend = (
  metricName: string,
  start: string,
  end: string,
  base: number,
  growth: number,
  volatility: number
): TrendData => {
  const dates = buildDateSeries(start, end)
  const data_points: TrendDataPoint[] = dates.map((date, index) => {
    const wave = Math.sin(index / 3) * volatility
    const drift = index * growth
    const value = Math.max(0, Math.round(base + drift + wave))
    return { date, value }
  })

  const values = data_points.map((point) => point.value)
  const total = values.reduce((sum, value) => sum + value, 0)
  const average = values.length ? total / values.length : 0
  const min_value = values.length ? Math.min(...values) : 0
  const max_value = values.length ? Math.max(...values) : 0

  return {
    metric_name: metricName,
    data_points,
    total,
    average,
    min_value,
    max_value,
  }
}

const buildMetric = (value: number, previous: number | null) => {
  const change = previous ? ((value - previous) / previous) * 100 : null
  const trend: 'up' | 'down' | 'stable' = change === null ? 'stable' : change > 0 ? 'up' : change < 0 ? 'down' : 'stable'
  return {
    value,
    previous_value: previous,
    change_percent: change,
    trend,
  }
}

let mockAccounts: AmazonAccount[] = [
  {
    id: 'demo-account-1',
    organization_id: 'demo-org',
    account_name: 'Northwind US',
    account_type: 'seller',
    marketplace_id: 'ATVPDKIKX0DER',
    marketplace_country: 'US',
    is_active: true,
    last_sync_at: new Date(Date.now() - DAY_MS).toISOString(),
    sync_status: 'success',
    sync_error_message: null,
    created_at: new Date(Date.now() - DAY_MS * 60).toISOString(),
    updated_at: new Date(Date.now() - DAY_MS).toISOString(),
  },
  {
    id: 'demo-account-2',
    organization_id: 'demo-org',
    account_name: 'Berlin Retail',
    account_type: 'vendor',
    marketplace_id: 'A1PA6795UKMFR9',
    marketplace_country: 'DE',
    is_active: true,
    last_sync_at: new Date(Date.now() - DAY_MS * 2).toISOString(),
    sync_status: 'syncing',
    sync_error_message: null,
    created_at: new Date(Date.now() - DAY_MS * 90).toISOString(),
    updated_at: new Date(Date.now() - DAY_MS * 2).toISOString(),
  },
  {
    id: 'demo-account-3',
    organization_id: 'demo-org',
    account_name: 'Milan Supplies',
    account_type: 'seller',
    marketplace_id: 'APJ6JRA9NG5V4',
    marketplace_country: 'IT',
    is_active: true,
    last_sync_at: new Date(Date.now() - DAY_MS * 3).toISOString(),
    sync_status: 'error',
    sync_error_message: 'Authentication required',
    created_at: new Date(Date.now() - DAY_MS * 120).toISOString(),
    updated_at: new Date(Date.now() - DAY_MS * 3).toISOString(),
  },
]

let mockAccountStatuses: AccountStatus[] = [
  {
    id: 'demo-account-1',
    account_name: 'Northwind US',
    marketplace_country: 'US',
    sync_status: 'success',
    last_sync_at: new Date(Date.now() - DAY_MS).toISOString(),
    sync_error_message: null,
    total_sales_30d: 124500,
    total_units_30d: 8320,
    active_asins: 245,
  },
  {
    id: 'demo-account-2',
    account_name: 'Berlin Retail',
    marketplace_country: 'DE',
    sync_status: 'syncing',
    last_sync_at: new Date(Date.now() - DAY_MS * 2).toISOString(),
    sync_error_message: null,
    total_sales_30d: 78300,
    total_units_30d: 5120,
    active_asins: 188,
  },
  {
    id: 'demo-account-3',
    account_name: 'Milan Supplies',
    marketplace_country: 'IT',
    sync_status: 'error',
    last_sync_at: new Date(Date.now() - DAY_MS * 3).toISOString(),
    sync_error_message: 'Authentication required',
    total_sales_30d: 45200,
    total_units_30d: 2940,
    active_asins: 126,
  },
]

let mockForecasts: Forecast[] = []

const buildForecast = (accountId: string, horizonDays: number): Forecast => {
  const start = new Date()
  const predictions: ForecastPrediction[] = Array.from({ length: horizonDays }, (_, index) => {
    const date = addDays(start, index)
    const base = 42000 + index * 320
    const variance = Math.sin(index / 4) * 1500
    const predicted_value = Math.round(base + variance)
    return {
      date: date.toISOString(),
      predicted_value,
      lower_bound: Math.round(predicted_value * 0.9),
      upper_bound: Math.round(predicted_value * 1.1),
    }
  })

  return {
    id: `demo-forecast-${Date.now()}`,
    account_id: accountId,
    asin: null,
    forecast_type: 'sales',
    generated_at: new Date().toISOString(),
    horizon_days: horizonDays,
    model_used: 'LSTM Ensemble',
    confidence_interval: 0.8,
    predictions,
    mape: 6.3,
    rmse: 1240,
  }
}

const ensureForecasts = () => {
  if (mockForecasts.length === 0) {
    mockForecasts = [buildForecast('demo-account-1', 30)]
  }
}

const mockProducts: Product[] = [
  {
    id: 'prod-1',
    account_id: 'demo-account-1',
    asin: 'B0B8R12XK1',
    sku: 'NW-1001',
    title: 'Wireless Ergonomic Mouse',
    brand: 'Northwind',
    category: 'Electronics',
    current_price: 29.99,
    current_bsr: 1450,
    review_count: 1240,
    rating: 4.5,
    is_active: true,
  },
  {
    id: 'prod-2',
    account_id: 'demo-account-1',
    asin: 'B0C3M55GZ2',
    sku: 'NW-1002',
    title: 'Smart Home Plug (4-pack)',
    brand: 'Northwind',
    category: 'Home & Kitchen',
    current_price: 34.5,
    current_bsr: 980,
    review_count: 860,
    rating: 4.3,
    is_active: true,
  },
  {
    id: 'prod-3',
    account_id: 'demo-account-2',
    asin: 'B09XZ22LV9',
    sku: 'BR-2001',
    title: 'Premium Yoga Mat',
    brand: 'Berlin Retail',
    category: 'Sports',
    current_price: 44.0,
    current_bsr: 2300,
    review_count: 530,
    rating: 4.6,
    is_active: true,
  },
  {
    id: 'prod-4',
    account_id: 'demo-account-3',
    asin: 'B0A8U77PL4',
    sku: 'MS-3001',
    title: 'Stainless Steel Cookware Set',
    brand: 'Milan Supplies',
    category: 'Home & Kitchen',
    current_price: 129.0,
    current_bsr: 760,
    review_count: 320,
    rating: 4.2,
    is_active: true,
  },
]

export const mockCategoryData = [
  { name: 'Electronics', value: 35 },
  { name: 'Sports', value: 25 },
  { name: 'Home & Kitchen', value: 20 },
  { name: 'Grocery', value: 12 },
  { name: 'Other', value: 8 },
]

export const mockHourlyOrders = Array.from({ length: 24 }, (_, index) => ({
  hour: `${index}:00`,
  orders: Math.floor(18 + Math.sin(index / 3) * 8 + (index % 4) * 3),
}))

export const getMockAccountSummary = (): AccountSummary => {
  const total_accounts = mockAccounts.length
  const active_accounts = mockAccounts.filter((account) => account.is_active).length
  const syncing_accounts = mockAccounts.filter((account) => account.sync_status === 'syncing').length
  const error_accounts = mockAccounts.filter((account) => account.sync_status === 'error').length

  return {
    total_accounts,
    active_accounts,
    syncing_accounts,
    error_accounts,
    accounts: mockAccountStatuses,
  }
}

export const getMockAccounts = (): AmazonAccount[] => mockAccounts

export const createMockAccount = (data: Partial<AmazonAccount>): AmazonAccount => {
  const account: AmazonAccount = {
    id: `demo-account-${Date.now()}`,
    organization_id: 'demo-org',
    account_name: data.account_name || 'Demo Account',
    account_type: data.account_type || 'seller',
    marketplace_id: data.marketplace_id || 'ATVPDKIKX0DER',
    marketplace_country: data.marketplace_country || 'US',
    is_active: true,
    last_sync_at: null,
    sync_status: 'pending',
    sync_error_message: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }

  mockAccounts = [account, ...mockAccounts]
  mockAccountStatuses = [
    {
      id: account.id,
      account_name: account.account_name,
      marketplace_country: account.marketplace_country,
      sync_status: account.sync_status,
      last_sync_at: account.last_sync_at,
      sync_error_message: null,
      total_sales_30d: 21500,
      total_units_30d: 1460,
      active_asins: 64,
    },
    ...mockAccountStatuses,
  ]

  return account
}

export const updateMockAccount = (id: string, data: Partial<AmazonAccount>): AmazonAccount => {
  const index = mockAccounts.findIndex((account) => account.id === id)
  if (index === -1) {
    return mockAccounts[0]
  }
  const updated = { ...mockAccounts[index], ...data, updated_at: new Date().toISOString() }
  mockAccounts = [
    ...mockAccounts.slice(0, index),
    updated,
    ...mockAccounts.slice(index + 1),
  ]
  mockAccountStatuses = mockAccountStatuses.map((status) =>
    status.id === id
      ? {
          ...status,
          account_name: updated.account_name,
          marketplace_country: updated.marketplace_country,
          sync_status: updated.sync_status,
          last_sync_at: updated.last_sync_at,
          sync_error_message: updated.sync_error_message,
        }
      : status
  )
  return updated
}

export const deleteMockAccount = (id: string): void => {
  mockAccounts = mockAccounts.filter((account) => account.id !== id)
  mockAccountStatuses = mockAccountStatuses.filter((status) => status.id !== id)
}

export const triggerMockSync = (id: string): void => {
  updateMockAccount(id, {
    sync_status: 'success',
    last_sync_at: new Date().toISOString(),
    sync_error_message: null,
  })
}

const accountScale = (accountIds?: string[]): number => {
  if (!accountIds || accountIds.length === 0) return 1
  const total = mockAccounts.length
  return total > 0 ? accountIds.length / total : 1
}

export const getMockDashboardKPIs = (params: {
  start_date: string
  end_date: string
  account_ids?: string[]
}): DashboardKPIs => {
  const scale = accountScale(params.account_ids)
  return {
    total_revenue: buildMetric(Math.round(182340 * scale), Math.round(165200 * scale)),
    total_units: buildMetric(Math.round(12840 * scale), Math.round(11910 * scale)),
    total_orders: buildMetric(Math.round(6420 * scale), Math.round(6005 * scale)),
    average_order_value: buildMetric(28.4, 27.5),
    return_rate: buildMetric(2.4, 2.7),
    roas: buildMetric(4.1, 3.8),
    acos: buildMetric(24.8, 26.2),
    ctr: buildMetric(1.6, 1.4),
    active_asins: Math.round(559 * scale),
    accounts_synced: mockAccounts.filter((account) => account.sync_status === 'success').length,
    period_start: params.start_date,
    period_end: params.end_date,
  }
}

export const getMockTrends = (params: {
  metrics: string[]
  start_date: string
  end_date: string
  account_ids?: string[]
}): TrendData[] => {
  const scale = accountScale(params.account_ids)
  return params.metrics.map((metric) => {
    if (metric === 'revenue') {
      return buildTrend('revenue', params.start_date, params.end_date, Math.round(4800 * scale), Math.round(60 * scale), Math.round(520 * scale))
    }
    if (metric === 'units') {
      return buildTrend('units', params.start_date, params.end_date, Math.round(320 * scale), Math.round(4 * scale), Math.round(28 * scale))
    }
    return buildTrend(metric, params.start_date, params.end_date, Math.round(200 * scale), Math.round(2 * scale), Math.round(15 * scale))
  })
}

export const getMockTopPerformers = (limit?: number): {
  by_revenue: Array<{ asin: string; total_revenue: number; total_units: number }>
  by_units: Array<{ asin: string; total_revenue: number; total_units: number }>
} => {
  const items = [
    { asin: 'B0B8R12XK1', total_revenue: 32450, total_units: 1210 },
    { asin: 'B0C3M55GZ2', total_revenue: 28700, total_units: 980 },
    { asin: 'B09XZ22LV9', total_revenue: 24510, total_units: 870 },
    { asin: 'B0A8U77PL4', total_revenue: 19800, total_units: 540 },
    { asin: 'B0D1H44TZ9', total_revenue: 17620, total_units: 510 },
    { asin: 'B0D4K11JR8', total_revenue: 16240, total_units: 470 },
    { asin: 'B0C8P32QL2', total_revenue: 14980, total_units: 430 },
    { asin: 'B0F2S19RM5', total_revenue: 13210, total_units: 410 },
    { asin: 'B0H7Y88CV3', total_revenue: 11890, total_units: 360 },
    { asin: 'B0J3V77BT2', total_revenue: 10200, total_units: 320 },
  ]

  const byRevenue = limit ? items.slice(0, limit) : items
  const byUnits = limit ? [...items].slice(0, limit) : [...items]

  return {
    by_revenue: byRevenue,
    by_units: byUnits.sort((a, b) => b.total_units - a.total_units),
  }
}

export const getMockSalesAggregated = (params: {
  start_date: string
  end_date: string
  account_ids?: string[]
  group_by?: string
}): SalesAggregated[] => {
  const scale = accountScale(params.account_ids)
  const dates = buildDateSeries(params.start_date, params.end_date)
  const daily: SalesAggregated[] = dates.map((date, index) => {
    const units = Math.round((340 + index * 4 + Math.sin(index / 2) * 20) * scale)
    const total_orders = Math.round(units * 0.78)
    const total_sales = Math.round(units * 28.5)
    return { date, total_units: units, total_sales, total_orders, currency: 'USD' }
  })

  if (!params.group_by || params.group_by === 'day') return daily

  const grouped = new Map<string, SalesAggregated>()
  for (const row of daily) {
    const d = new Date(row.date + 'T00:00:00')
    const key =
      params.group_by === 'week'
        ? fnsFormat(startOfWeek(d, { weekStartsOn: 1 }), 'yyyy-MM-dd')
        : fnsFormat(startOfMonth(d), 'yyyy-MM-dd')

    const existing = grouped.get(key)
    if (existing) {
      existing.total_units += row.total_units
      existing.total_sales += row.total_sales
      existing.total_orders += row.total_orders
    } else {
      grouped.set(key, { ...row, date: key })
    }
  }
  return Array.from(grouped.values())
}

export const getMockForecasts = (): Forecast[] => {
  ensureForecasts()
  return mockForecasts
}

export const createMockForecast = (params: {
  account_id: string
  horizon_days?: number
}): { id: string; status: string } => {
  const forecast = buildForecast(params.account_id, params.horizon_days || 30)
  mockForecasts = [forecast, ...mockForecasts]
  return { id: forecast.id, status: 'completed' }
}

export const getMockForecast = (id: string): Forecast => {
  ensureForecasts()
  return mockForecasts.find((forecast) => forecast.id === id) || mockForecasts[0]
}

export const getMockProducts = (params?: {
  search?: string
  category?: string
  active_only?: boolean
  limit?: number
}): Product[] => {
  let products = mockProducts
  if (params?.search) {
    const term = params.search.toLowerCase()
    products = products.filter(
      (product) =>
        product.title?.toLowerCase().includes(term) ||
        product.asin.toLowerCase().includes(term) ||
        product.brand?.toLowerCase().includes(term)
    )
  }
  if (params?.category) {
    products = products.filter((product) => product.category === params.category)
  }
  if (params?.active_only) {
    products = products.filter((product) => product.is_active)
  }
  if (params?.limit) {
    products = products.slice(0, params.limit)
  }
  return products
}

export const getMockProduct = (asin: string): Product => {
  return mockProducts.find((product) => product.asin === asin) || mockProducts[0]
}

export const getMockInventory = (params?: {
  account_ids?: string[]
  low_stock_only?: boolean
}): unknown[] => {
  const items = [
    { asin: 'B0B8R12XK1', sku: 'NW-1001', on_hand: 320, inbound: 85, account_id: 'demo-account-1' },
    { asin: 'B0C3M55GZ2', sku: 'NW-1002', on_hand: 240, inbound: 60, account_id: 'demo-account-1' },
    { asin: 'B09XZ22LV9', sku: 'BR-2001', on_hand: 12, inbound: 0, account_id: 'demo-account-2' },
    { asin: 'B0A8U77PL4', sku: 'MS-3001', on_hand: 45, inbound: 20, account_id: 'demo-account-3' },
  ]
  let result = items
  if (params?.account_ids && params.account_ids.length > 0) {
    result = result.filter((item) => params.account_ids!.includes(item.account_id))
  }
  if (params?.low_stock_only) {
    result = result.filter((item) => item.on_hand < 50)
  }
  return result
}

export const getMockAdvertising = (): unknown[] => {
  return [
    { campaign: 'Brand Defense', spend: 1420, clicks: 940, acos: 0.24 },
    { campaign: 'Top Sellers', spend: 980, clicks: 610, acos: 0.27 },
  ]
}

export const getMockExport = (label: string): Blob => {
  const payload = {
    demo: true,
    generated_at: new Date().toISOString(),
    label,
  }
  return new Blob([JSON.stringify(payload, null, 2)], {
    type: 'application/json',
  })
}

// API Keys mock
let mockApiKeys = {
  sp_api_client_id: null as string | null,
  sp_api_aws_access_key: null as string | null,
  sp_api_role_arn: null as string | null,
  has_client_secret: false,
  has_aws_secret_key: false,
}

export const getMockApiKeys = () => ({ ...mockApiKeys })

export const updateMockApiKeys = (data: {
  sp_api_client_id?: string
  sp_api_client_secret?: string
  sp_api_aws_access_key?: string
  sp_api_aws_secret_key?: string
  sp_api_role_arn?: string
}) => {
  if (data.sp_api_client_id !== undefined) {
    const v = data.sp_api_client_id
    mockApiKeys.sp_api_client_id = v ? v.slice(0, 8) + '***' + v.slice(-3) : null
  }
  if (data.sp_api_client_secret !== undefined) {
    mockApiKeys.has_client_secret = Boolean(data.sp_api_client_secret)
  }
  if (data.sp_api_aws_access_key !== undefined) {
    const v = data.sp_api_aws_access_key
    mockApiKeys.sp_api_aws_access_key = v ? v.slice(0, 8) + '***' + v.slice(-3) : null
  }
  if (data.sp_api_aws_secret_key !== undefined) {
    mockApiKeys.has_aws_secret_key = Boolean(data.sp_api_aws_secret_key)
  }
  if (data.sp_api_role_arn !== undefined) {
    mockApiKeys.sp_api_role_arn = data.sp_api_role_arn || null
  }
  return { ...mockApiKeys }
}
