import { RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface FilterBarProps {
  children: React.ReactNode
  onReset?: () => void
  showReset?: boolean
}

export function FilterBar({ children, onReset, showReset = true }: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {children}
      {showReset && onReset && (
        <Button variant="ghost" size="sm" onClick={onReset} className="h-9 text-xs text-muted-foreground">
          <RotateCcw className="mr-1.5 h-3 w-3" />
          Reset
        </Button>
      )}
    </div>
  )
}
