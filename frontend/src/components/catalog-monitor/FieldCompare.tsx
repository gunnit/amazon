import { useState, type ReactNode } from 'react'
import { ImageOff } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { TabProps } from '@/components/catalog/types'
import { isImageSlot } from './changeLabels'
import { sameText, wordDiff, type DiffOp } from './wordDiff'

// Highlights shared by every comparison: what the left side loses, what the right side gains.
const REMOVED_CLASS = 'rounded-sm bg-red-100 text-red-900 dark:bg-red-900/50 dark:text-red-100'
const ADDED_CLASS = 'rounded-sm bg-amber-100 text-amber-900 dark:bg-amber-900/50 dark:text-amber-100'
const CHANGED_ITEM = 'rounded-md bg-amber-50 ring-1 ring-amber-400 dark:bg-amber-950/40 dark:ring-amber-500'

type Side = 'before' | 'after'
type T = TabProps['t']

interface Props {
  field: string
  before: unknown
  after: unknown
  beforeLabel: string
  afterLabel: string
  t: T
}

const asText = (v: unknown): string | null =>
  typeof v === 'string' ? v : typeof v === 'number' ? String(v) : null
const asList = (v: unknown): unknown[] => (Array.isArray(v) ? v : v == null ? [] : [v])
const asStrings = (v: unknown): string[] => asList(v).map((x) => (typeof x === 'string' ? x : JSON.stringify(x)))

function Empty({ t }: { t: T }) {
  return <span className="italic text-muted-foreground">{t('cm.diff.empty')}</span>
}

/** The side's words, with the ones the other side does not have highlighted. */
function DiffText({ ops, side }: { ops: DiffOp[]; side: Side }) {
  const hidden = side === 'before' ? 'added' : 'removed'
  return (
    <>
      {ops
        .filter((op) => op.type !== hidden)
        .map((op, i) =>
          op.type === 'same' ? (
            <span key={i}>{op.text}</span>
          ) : (
            <mark key={i} className={side === 'before' ? REMOVED_CLASS : ADDED_CLASS}>
              {op.text}
            </mark>
          ),
        )}
    </>
  )
}

function TextValue({ value, other, side, t }: { value: string | null; other: string | null; side: Side; t: T }) {
  if (!value) return <Empty t={t} />
  const ops = side === 'before' ? wordDiff(value, other ?? '') : wordDiff(other ?? '', value)
  return (
    <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
      <DiffText ops={ops} side={side} />
    </p>
  )
}

function Bullets({ value, other, side, t }: { value: string[]; other: string[]; side: Side; t: T }) {
  if (value.length === 0) return <Empty t={t} />
  return (
    <ol className="list-decimal space-y-1.5 pl-5 text-sm">
      {value.map((item, i) => {
        const counterpart = other[i]
        const changed = !sameText(item, counterpart)
        return (
          <li key={i} className={cn('px-1 py-0.5', changed && CHANGED_ITEM)}>
            {changed && counterpart ? (
              <DiffText
                side={side}
                ops={side === 'before' ? wordDiff(item, counterpart) : wordDiff(counterpart, item)}
              />
            ) : (
              item
            )}
          </li>
        )
      })}
    </ol>
  )
}

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
function ImageStrip({ value, other, numbered, t }: { value: string[]; other: string[]; numbered: boolean; t: T }) {
  const slots = Math.max(value.length, other.length)
  if (slots === 0) return <Empty t={t} />
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

const entryText = (v: unknown) => (v !== null && typeof v === 'object' ? JSON.stringify(v) : String(v))

/** Attribute values as key: value lines, one block per value; differing blocks highlighted. */
function Attribute({ value, other, t }: { value: unknown[]; other: unknown[]; t: T }) {
  if (value.length === 0) return <Empty t={t} />
  return (
    <div className="space-y-1.5">
      {value.map((entry, i) => {
        const changed = JSON.stringify(entry) !== JSON.stringify(other[i])
        const pairs =
          entry !== null && typeof entry === 'object' && !Array.isArray(entry)
            ? Object.entries(entry as Record<string, unknown>)
            : [['value', entry] as [string, unknown]]
        return (
          <dl
            key={i}
            className={cn('grid grid-cols-[auto_1fr] gap-x-2 px-1.5 py-1 font-mono text-xs', changed && CHANGED_ITEM)}
          >
            {pairs.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted-foreground">{k}:</dt>
                <dd className="break-all">{entryText(v)}</dd>
              </div>
            ))}
          </dl>
        )
      })}
    </div>
  )
}

function renderSide(field: string, value: unknown, other: unknown, side: Side, t: T): ReactNode {
  if (field === 'bullets') return <Bullets value={asStrings(value)} other={asStrings(other)} side={side} t={t} />
  if (field === 'images' || isImageSlot(field)) {
    return (
      <ImageStrip value={asStrings(value)} other={asStrings(other)} numbered={field === 'images'} t={t} />
    )
  }
  if (field === 'aplus') {
    if (typeof value !== 'number') return <Empty t={t} />
    return (
      <span className={cn('text-sm', value !== other && (side === 'before' ? REMOVED_CLASS : ADDED_CLASS))}>
        {t('cm.diff.aplusModules', { count: value })}
      </span>
    )
  }
  const text = asText(value)
  const otherText = asText(other)
  if ((value == null || text !== null) && (other == null || otherText !== null)) {
    return <TextValue value={text} other={otherText} side={side} t={t} />
  }
  return <Attribute value={asList(value)} other={asList(other)} t={t} />
}

/** Side-by-side comparison of one content field (text, bullets, images, A+ or attribute). */
export function FieldCompare({ field, before, after, beforeLabel, afterLabel, t }: Props) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {(
        [
          ['before', beforeLabel, before, after],
          ['after', afterLabel, after, before],
        ] as const
      ).map(([side, label, value, other]) => (
        <section key={side} className="min-w-0 space-y-1.5">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</h4>
          <div className="rounded-md border bg-muted/30 p-3">{renderSide(field, value, other, side, t)}</div>
        </section>
      ))}
    </div>
  )
}

/** Explains the highlight colours under a comparison; with a field, only the ones it uses. */
export function DiffLegend({ t, field }: { t: T; field?: string }) {
  const images = field === undefined || field === 'images' || isImageSlot(field)
  const text = field === undefined || !images
  return (
    <p className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      {text && (
        <>
          <span>
            <mark className={cn(REMOVED_CLASS, 'px-1')}>{t('cm.diff.legendRemoved')}</mark>
          </span>
          <span>
            <mark className={cn(ADDED_CLASS, 'px-1')}>{t('cm.diff.legendAdded')}</mark>
          </span>
        </>
      )}
      {images && (
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-sm ring-2 ring-amber-500" aria-hidden="true" />
          {t('cm.diff.legendSlot')}
        </span>
      )}
    </p>
  )
}
