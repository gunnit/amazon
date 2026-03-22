import { useState } from 'react'
import { X, Plus } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useTranslation } from '@/i18n'

interface AsinInputProps {
  asins: string[]
  onChange: (asins: string[]) => void
  max?: number
}

export default function AsinInput({ asins, onChange, max = 5 }: AsinInputProps) {
  const [value, setValue] = useState('')
  const { t } = useTranslation()

  const addAsin = () => {
    const trimmed = value.trim().toUpperCase()
    if (!trimmed) return
    if (asins.length >= max) return
    if (asins.includes(trimmed)) return
    onChange([...asins, trimmed])
    setValue('')
  }

  const removeAsin = (asin: string) => {
    onChange(asins.filter((a) => a !== asin))
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addAsin()
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="e.g. B0B8R12XK1"
          className="flex-1"
          disabled={asins.length >= max}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={addAsin}
          disabled={!value.trim() || asins.length >= max}
        >
          <Plus className="h-4 w-4 mr-1" />
          {t('marketResearch.addAsin')}
        </Button>
      </div>
      {asins.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {asins.map((asin) => (
            <Badge key={asin} variant="secondary" className="gap-1 pr-1">
              {asin}
              <button
                type="button"
                onClick={() => removeAsin(asin)}
                className="ml-1 rounded-full p-0.5 hover:bg-muted-foreground/20"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        {asins.length}/{max} — {t('marketResearch.maxCompetitors')}
      </p>
    </div>
  )
}
