import { Check, HelpCircle, Minus, X, type LucideIcon } from 'lucide-react'
import type { QualityState } from '@/types'

export const STATE_STYLE: Record<
  QualityState,
  { icon: LucideIcon; circle: string; text: string; bar: string }
> = {
  green: {
    icon: Check,
    circle: 'bg-green-600 text-white dark:bg-green-500 dark:text-green-950',
    text: 'text-green-700 dark:text-green-400',
    bar: 'bg-green-600 dark:bg-green-500',
  },
  yellow: {
    icon: Minus,
    circle: 'bg-amber-500 text-white dark:bg-amber-400 dark:text-amber-950',
    text: 'text-amber-700 dark:text-amber-400',
    bar: 'bg-amber-500 dark:bg-amber-400',
  },
  red: {
    icon: X,
    circle: 'bg-red-600 text-white dark:bg-red-500 dark:text-red-950',
    text: 'text-red-700 dark:text-red-400',
    bar: 'bg-red-600 dark:bg-red-500',
  },
  grey: {
    icon: HelpCircle,
    circle: 'bg-slate-400 text-white dark:bg-slate-500 dark:text-slate-950',
    text: 'text-slate-600 dark:text-slate-400',
    bar: 'bg-slate-400 dark:bg-slate-500',
  },
}
