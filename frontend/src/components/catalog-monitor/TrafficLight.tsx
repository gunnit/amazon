import { cn } from '@/lib/utils'
import type { QualityState } from '@/types'
import { STATE_STYLE } from './stateStyle'

interface TrafficLightProps {
  state: QualityState
  /** Accessible name, e.g. "Titolo: Conforme e ottimizzato". */
  label: string
  /** Native tooltip; defaults to the label. */
  title?: string
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const SIZES = {
  sm: { box: 'h-5 w-5', icon: 'h-3 w-3' },
  md: { box: 'h-6 w-6', icon: 'h-3.5 w-3.5' },
  lg: { box: 'h-8 w-8', icon: 'h-5 w-5' },
}

/** Filled circle with an icon, so the state never depends on colour alone. */
export function TrafficLight({ state, label, title, size = 'md', className }: TrafficLightProps) {
  const { icon: Icon, circle } = STATE_STYLE[state]
  const s = SIZES[size]
  return (
    <span
      role="img"
      aria-label={label}
      title={title ?? label}
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full',
        s.box,
        circle,
        className,
      )}
    >
      <Icon className={s.icon} strokeWidth={3} aria-hidden="true" />
    </span>
  )
}
