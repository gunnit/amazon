import { useMemo, type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import type { TabProps } from '@/components/catalog/types'
import { isImageSlot } from './changeLabels'
import { ImageStrip } from './ImageStrip'
import { sameText, sideParts, wordDiff, type DiffOp } from './wordDiff'

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

/** Both sides of one field, prepared once: the word diffs are computed here, not per side. */
type Comparison =
  | { kind: 'text'; before: string | null; after: string | null; ops: DiffOp[] }
  | { kind: 'bullets'; before: string[]; after: string[]; ops: Array<DiffOp[] | null> }
  | { kind: 'images'; before: string[]; after: string[]; numbered: boolean }
  | { kind: 'aplus'; before: unknown; after: unknown }
  | { kind: 'attribute'; before: unknown[]; after: unknown[] }

function compare(field: string, before: unknown, after: unknown): Comparison {
  if (field === 'bullets') {
    const a = asStrings(before)
    const b = asStrings(after)
    const ops = Array.from({ length: Math.max(a.length, b.length) }, (_, i) =>
      a[i] !== undefined && b[i] !== undefined && !sameText(a[i], b[i]) ? wordDiff(a[i], b[i]) : null,
    )
    return { kind: 'bullets', before: a, after: b, ops }
  }
  if (field === 'images' || isImageSlot(field)) {
    return { kind: 'images', before: asStrings(before), after: asStrings(after), numbered: field === 'images' }
  }
  if (field === 'aplus') return { kind: 'aplus', before, after }
  const a = asText(before)
  const b = asText(after)
  if ((before == null || a !== null) && (after == null || b !== null)) {
    return { kind: 'text', before: a, after: b, ops: wordDiff(a ?? '', b ?? '') }
  }
  return { kind: 'attribute', before: asList(before), after: asList(after) }
}

function Empty({ t }: { t: T }) {
  return <span className="italic text-muted-foreground">{t('cm.diff.empty')}</span>
}

/** The side's own text, with the words the other side does not have highlighted. */
function DiffText({ ops, side }: { ops: DiffOp[]; side: Side }) {
  return (
    <>
      {sideParts(ops, side).map((op, i) =>
        op.type === 'same' ? (
          <span key={i}>{op[side]}</span>
        ) : (
          <mark key={i} className={side === 'before' ? REMOVED_CLASS : ADDED_CLASS}>
            {op[side]}
          </mark>
        ),
      )}
    </>
  )
}

function Bullets({ value, other, ops, side, t }: {
  value: string[]
  other: string[]
  ops: Array<DiffOp[] | null>
  side: Side
  t: T
}) {
  if (value.length === 0) return <Empty t={t} />
  return (
    <ol className="list-decimal space-y-1.5 pl-5 text-sm">
      {value.map((item, i) => {
        const diff = ops[i]
        return (
          <li key={i} className={cn('px-1 py-0.5', !sameText(item, other[i]) && CHANGED_ITEM)}>
            {diff ? <DiffText ops={diff} side={side} /> : item}
          </li>
        )
      })}
    </ol>
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

function renderSide(c: Comparison, side: Side, t: T): ReactNode {
  const other: Side = side === 'before' ? 'after' : 'before'
  switch (c.kind) {
    case 'bullets':
      return <Bullets value={c[side]} other={c[other]} ops={c.ops} side={side} t={t} />
    case 'images':
      if (c[side].length === 0 && c[other].length === 0) return <Empty t={t} />
      return <ImageStrip value={c[side]} other={c[other]} numbered={c.numbered} />
    case 'aplus': {
      const value = c[side]
      if (typeof value !== 'number') return <Empty t={t} />
      return (
        <span className={cn('text-sm', value !== c[other] && (side === 'before' ? REMOVED_CLASS : ADDED_CLASS))}>
          {t('cm.diff.aplusModules', { count: value })}
        </span>
      )
    }
    case 'text':
      return c[side] ? (
        <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
          <DiffText ops={c.ops} side={side} />
        </p>
      ) : (
        <Empty t={t} />
      )
    default:
      return <Attribute value={c[side]} other={c[other]} t={t} />
  }
}

/** Side-by-side comparison of one content field (text, bullets, images, A+ or attribute). */
export function FieldCompare({ field, before, after, beforeLabel, afterLabel, t }: Props) {
  // before/after come straight from the query data, so the diff runs once per field
  const comparison = useMemo(() => compare(field, before, after), [field, before, after])
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {(
        [
          ['before', beforeLabel],
          ['after', afterLabel],
        ] as const
      ).map(([side, label]) => (
        <section key={side} className="min-w-0 space-y-1.5">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</h4>
          <div className="rounded-md border bg-muted/30 p-3">{renderSide(comparison, side, t)}</div>
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
