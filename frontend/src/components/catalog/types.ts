// Shared TypeScript types for catalog management UI.
// Mirrors backend/app/schemas/catalog.py.

export type BulkErrorCode =
  | 'invalid_input'
  | 'product_not_found'
  | 'missing_sku'
  | 'sp_api_error'
  | 'unexpected_error'

export interface BulkRowError {
  row?: number | null
  asin?: string | null
  sku?: string | null
  error: string
  code: BulkErrorCode
}

export interface BulkResult<T> {
  account_id: string
  total: number
  succeeded: number
  failed: number
  skipped?: number
  successes: T[]
  errors: BulkRowError[]
}

export interface PriceUpdateResult {
  asin?: string | null
  sku?: string | null
  price: string
}

export interface BulkListingUpdateResult {
  sku: string
  fields: string[]
}

export interface AvailabilityResult {
  asin: string
  sku: string
  is_available: boolean
  pushed_quantity: number
}

export type CatalogChangeField =
  | 'price'
  | 'quantity'
  | 'availability'
  | 'image'
  | 'listing'

export type CatalogChangeStatus = 'success' | 'failed' | 'skipped'

export interface CatalogChangeLogEntry {
  id: string
  account_id: string
  user_id: string | null
  asin: string | null
  sku: string | null
  field: CatalogChangeField
  old_value: unknown
  new_value: unknown
  sp_api_status: CatalogChangeStatus
  sp_api_error: string | null
  created_at: string
}

export interface TabProps {
  accountId: string
  accounts: Array<{ id: string; account_name: string }>
  onAccountChange: (id: string) => void
  toast: (props: {
    title?: string
    description?: string
    variant?: 'default' | 'destructive'
  }) => void
  t: (key: string, vars?: Record<string, string | number>) => string
}
