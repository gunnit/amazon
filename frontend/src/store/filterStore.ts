import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export type DatePreset = '7' | '14' | '30' | '60' | '90' | 'custom'
export type GroupBy = 'day' | 'week' | 'month'
export type ComparisonMode = 'preset' | 'custom'
export type ComparisonPreset = 'mom' | 'qoq' | 'yoy'

interface ComparisonRange {
  start: string
  end: string
}

interface ComparisonPeriods {
  preset: ComparisonPreset | null
  period1: ComparisonRange
  period2: ComparisonRange
}

interface FilterState {
  // Shared filters
  datePreset: DatePreset
  customStartDate: string | null
  customEndDate: string | null
  accountIds: string[]
  comparisonMode: ComparisonMode
  comparisonPreset: ComparisonPreset
  comparisonPeriod1Start: string | null
  comparisonPeriod1End: string | null
  comparisonPeriod2Start: string | null
  comparisonPeriod2End: string | null

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
  setComparisonMode: (mode: ComparisonMode) => void
  setComparisonPreset: (preset: ComparisonPreset) => void
  setComparisonPeriod1Range: (start: string, end: string) => void
  setComparisonPeriod2Range: (start: string, end: string) => void

  setAnalyticsGroupBy: (groupBy: GroupBy) => void
  setAnalyticsCategory: (category: string) => void

  setReportsGroupBy: (groupBy: GroupBy) => void
  setReportsLowStockOnly: (value: boolean) => void

  resetAll: () => void
  resetDashboard: () => void
  resetAnalytics: () => void
  resetReports: () => void
  resetComparison: () => void
}

const defaultState = {
  datePreset: '30' as DatePreset,
  customStartDate: null as string | null,
  customEndDate: null as string | null,
  accountIds: [] as string[],
  comparisonMode: 'preset' as ComparisonMode,
  comparisonPreset: 'mom' as ComparisonPreset,
  comparisonPeriod1Start: null as string | null,
  comparisonPeriod1End: null as string | null,
  comparisonPeriod2Start: null as string | null,
  comparisonPeriod2End: null as string | null,
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

      setComparisonMode: (mode) => set({ comparisonMode: mode }),
      setComparisonPreset: (preset) => set({ comparisonMode: 'preset', comparisonPreset: preset }),
      setComparisonPeriod1Range: (start, end) => set({
        comparisonMode: 'custom',
        comparisonPeriod1Start: start,
        comparisonPeriod1End: end,
      }),
      setComparisonPeriod2Range: (start, end) => set({
        comparisonMode: 'custom',
        comparisonPeriod2Start: start,
        comparisonPeriod2End: end,
      }),

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
      resetComparison: () => set({
        comparisonMode: 'preset',
        comparisonPreset: 'mom',
        comparisonPeriod1Start: null,
        comparisonPeriod1End: null,
        comparisonPeriod2Start: null,
        comparisonPeriod2End: null,
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

function parseDate(dateValue: string): Date {
  return new Date(dateValue + 'T00:00:00')
}

function formatDate(dateValue: Date): string {
  return `${dateValue.getFullYear()}-${String(dateValue.getMonth() + 1).padStart(2, '0')}-${String(dateValue.getDate()).padStart(2, '0')}`
}

function shiftDate(dateValue: Date, preset: ComparisonPreset): Date {
  const shifted = new Date(dateValue)
  if (preset === 'mom') {
    shifted.setMonth(shifted.getMonth() - 1)
  } else if (preset === 'qoq') {
    shifted.setMonth(shifted.getMonth() - 3)
  } else {
    shifted.setFullYear(shifted.getFullYear() - 1)
  }
  return shifted
}

/** Resolve the two date ranges used by the period comparison feature. */
export function getComparisonPeriods(
  state: Pick<
    FilterState,
    | 'datePreset'
    | 'customStartDate'
    | 'customEndDate'
    | 'comparisonMode'
    | 'comparisonPreset'
    | 'comparisonPeriod1Start'
    | 'comparisonPeriod1End'
    | 'comparisonPeriod2Start'
    | 'comparisonPeriod2End'
  >
): ComparisonPeriods {
  if (
    state.comparisonMode === 'custom' &&
    state.comparisonPeriod1Start &&
    state.comparisonPeriod1End &&
    state.comparisonPeriod2Start &&
    state.comparisonPeriod2End
  ) {
    return {
      preset: null,
      period1: {
        start: state.comparisonPeriod1Start,
        end: state.comparisonPeriod1End,
      },
      period2: {
        start: state.comparisonPeriod2Start,
        end: state.comparisonPeriod2End,
      },
    }
  }

  const baseRange = getFilterDateRange(state)
  const currentStart = parseDate(baseRange.start)
  const currentEnd = parseDate(baseRange.end)

  return {
    preset: state.comparisonPreset,
    period1: baseRange,
    period2: {
      start: formatDate(shiftDate(currentStart, state.comparisonPreset)),
      end: formatDate(shiftDate(currentEnd, state.comparisonPreset)),
    },
  }
}
