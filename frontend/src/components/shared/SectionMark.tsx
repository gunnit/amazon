import type { ReactNode } from 'react'

// Numbered editorial section header: "01 — TITLE ————————".
export function SectionMark({
  index,
  title,
  hint,
}: {
  index?: string
  title: string
  hint?: ReactNode
}) {
  return (
    <div className="flex items-baseline gap-4">
      {index ? (
        <span
          aria-hidden="true"
          className="font-mono text-sm font-medium leading-none text-foreground/35"
        >
          {index}
        </span>
      ) : null}
      <div className="min-w-0">
        <h2 className="font-mono text-xs font-semibold uppercase tracking-[0.22em] text-foreground">
          {title}
        </h2>
        {hint ? (
          <p className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-foreground">{hint}</p>
        ) : null}
      </div>
      <div
        aria-hidden="true"
        className="hidden flex-1 self-center border-t border-foreground/15 sm:block"
      />
    </div>
  )
}
