import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value: number, currency: string = 'EUR'): string {
  return new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency,
    useGrouping: true,
  }).format(value)
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('it-IT', { useGrouping: true }).format(value)
}

export function formatRatio(value: number): string {
  return `${new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)}x`
}

function decimalFormat(digits: number): Intl.NumberFormat {
  return new Intl.NumberFormat('it-IT', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    useGrouping: true,
  })
}

export function formatDecimal(value: number, digits: number = 2): string {
  return decimalFormat(digits).format(value)
}

export function formatPercent(value: number, digits: number = 1): string {
  return `${value >= 0 ? '+' : ''}${decimalFormat(digits).format(value)}%`
}

/** Signed percent change, empty string when the value is missing. */
export function formatChangePercent(value: number | null | undefined): string {
  if (value == null) {
    return ''
  }

  return `${value > 0 ? '+' : ''}${decimalFormat(1).format(value)}%`
}

/** Signed percent capped at ±999%: near-zero baselines make ratios meaningless. */
export function formatTrendPercent(value: number | null | undefined): string {
  if (value == null) {
    return ''
  }
  if (value > 999) {
    return '>999%'
  }
  if (value < -999) {
    return '<-999%'
  }
  return formatChangePercent(value)
}

export function formatDate(date: string | Date): string {
  // Parse date-only strings as local time to avoid timezone shift
  const d = typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date)
    ? new Date(date + 'T00:00:00')
    : new Date(date)
  return d.toLocaleDateString('it-IT', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function formatLocalizedDate(date: string, language: string): string {
  return new Date(date + 'T00:00:00').toLocaleDateString(language === 'it' ? 'it-IT' : 'en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  window.URL.revokeObjectURL(url)
  document.body.removeChild(anchor)
}

export function getDateRange(days: number): { start: string; end: string } {
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
