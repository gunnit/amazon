import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'

interface ToggleFilterProps {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  id?: string
}

export function ToggleFilter({ label, checked, onChange, id = 'toggle-filter' }: ToggleFilterProps) {
  return (
    <div className="flex items-center gap-2">
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
      <Label htmlFor={id} className="text-sm cursor-pointer">
        {label}
      </Label>
    </div>
  )
}
