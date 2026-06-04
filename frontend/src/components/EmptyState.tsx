import type { LucideIcon } from 'lucide-react'
import { Inbox } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card, CardContent } from '@/components/ui/card'

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  /** Optional next-step hint shown below the description (e.g. what to do next). */
  nextStep?: string
  action?: React.ReactNode
  className?: string
}

/**
 * Honest empty/blocked state: icon + title + description + optional next step.
 * Used when a feature has no data or is blocked by an external dependency,
 * instead of leaving the surface looking broken or dumping a raw error.
 */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  nextStep,
  action,
  className,
}: EmptyStateProps) {
  return (
    <Card className={className}>
      <CardContent className="flex flex-col items-center py-12 text-center">
        <Icon className="mb-4 h-12 w-12 text-muted-foreground" />
        <p className="font-medium">{title}</p>
        {description && (
          <p className={cn('mt-1 max-w-md text-sm text-muted-foreground')}>{description}</p>
        )}
        {nextStep && (
          <p className="mt-2 max-w-md text-xs text-muted-foreground">{nextStep}</p>
        )}
        {action && <div className="mt-4">{action}</div>}
      </CardContent>
    </Card>
  )
}

export default EmptyState
