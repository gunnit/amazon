import { useState } from 'react'
import { ImageOff } from 'lucide-react'
import { cn } from '@/lib/utils'

function Thumb({ url, label, changed }: { url: string | null; label?: string; changed: boolean }) {
  const [failed, setFailed] = useState(false)
  const box = cn(
    'relative flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded border bg-white',
    changed && 'ring-2 ring-amber-500 ring-offset-1 ring-offset-background',
  )
  const badge = label && (
    <span className="absolute left-0.5 top-0.5 rounded bg-background/90 px-1 text-[10px] font-semibold tabular-nums text-foreground">
      {label}
    </span>
  )
  if (!url) {
    return <span className={cn(box, 'border-dashed bg-muted')}>{badge}</span>
  }
  return (
    <a href={url} target="_blank" rel="noreferrer" className={box} title={url}>
      {failed ? (
        <ImageOff className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      ) : (
        <img
          src={url}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
          className="max-h-full max-w-full object-contain"
        />
      )}
      {badge}
    </a>
  )
}

/** Numbered thumbnails; a slot that differs from the other side is outlined. */
export function ImageStrip({ value, other, numbered }: { value: string[]; other: string[]; numbered: boolean }) {
  const slots = Math.max(value.length, other.length)
  return (
    <ul className="flex flex-wrap gap-2">
      {Array.from({ length: slots }, (_, i) => (
        <li key={i}>
          <Thumb
            url={value[i] ?? null}
            label={numbered ? String(i + 1) : undefined}
            changed={(value[i] ?? null) !== (other[i] ?? null)}
          />
        </li>
      ))}
    </ul>
  )
}
