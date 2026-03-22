import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export type DatePreset = '7' | '14' | '30' | '60' | '90' | 'custom'
export type GroupBy = 'day' | 'week' | 'month'

interface FilterState {
  // Shared filters
  datePreset: DatePreset
  customStartDate: string | null
  customEndDate: string | null
  accountIds: string[]

  // Analytics-specific
  analyticsGroupBy: GroupBy
  analyticsCategory: string

  // Reports-specific
  reportsGroupBy: GroupBy
  reportsLowStockOnly: boolean

  // Actions
  setDatePreset: (preset: DatePreset) => void
  setCustomDateRange: (start: string, end: string) => void
  setAccountIds: (ids: string[]) => void
  toggleAccountId: (id: string) => void

  setAnalyticsGroupBy: (groupBy: GroupBy) => void
  setAnalyticsCategory: (category: string) => void

  setReportsGroupBy: (groupBy: GroupBy) => void
  setReportsLowStockOnly: (value: boolean) => void

  resetAll: () => void
  resetDashboard: () => void
  resetAnalytics: () => void
  resetReports: () => void
}

const defaultState = {
  datePreset: '30' as DatePreset,
  customStartDate: null as string | null,
  customEndDate: null as string | null,
  accountIds: [] as string[],
  analyticsGroupBy: 'day' as GroupBy,
  analyticsCategory: '',
  reportsGroupBy: 'day' as GroupBy,
  reportsLowStockOnly: false,
}

export const useFilterStore = create<FilterState>()(
  persist(
    (set) => ({
      ...defaultState,

      setDatePreset: (preset) => set({
        datePreset: preset,
        ...(preset !== 'custom' ? { customStartDate: null, customEndDate: null } : {}),
      }),

      setCustomDateRange: (start, end) => set({
        datePreset: 'custom',
        customStartDate: start,
        customEndDate: end,
      }),

      setAccountIds: (ids) => set({ accountIds: ids }),

      toggleAccountId: (id) => set((state) => ({
        accountIds: state.accountIds.includes(id)
          ? state.accountIds.filter((aid) => aid !== id)
          : [...state.accountIds, id],
      })),

      setAnalyticsGroupBy: (groupBy) => set({ analyticsGroupBy: groupBy }),
      setAnalyticsCategory: (category) => set({ analyticsCategory: category }),

      setReportsGroupBy: (groupBy) => set({ reportsGroupBy: groupBy }),
      setReportsLowStockOnly: (value) => set({ reportsLowStockOnly: value }),

      resetAll: () => set(defaultState),
      resetDashboard: () => set({
        datePreset: '30',
        customStartDate: null,
        customEndDate: null,
        accountIds: [],
      }),
      resetAnalytics: () => set({
        analyticsGroupBy: 'day',
        analyticsCategory: '',
      }),
      resetReports: () => set({
        reportsGroupBy: 'day',
        reportsLowStockOnly: false,
      }),
    }),
    {
      name: 'inthezon-filters',
      storage: createJSONStorage(() => sessionStorage),
    }
  )
)

/** Compute start/end date strings from the current filter state */
export function getFilterDateRange(state: Pick<FilterState, 'datePreset' | 'customStartDate' | 'customEndDate'>): {
  start: string
  end: string
} {
  if (state.datePreset === 'custom' && state.customStartDate && state.customEndDate) {
    return { start: state.customStartDate, end: state.customEndDate }
  }

  const days = parseInt(state.datePreset) || 30
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - days)

  const fmt = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

  return {
    start: fmt(start),
    end: fmt(end),
  }
}
