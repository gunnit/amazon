// Editorial design language shared by the report-producing surfaces
// (Brand Analysis, Weekly Brand Intelligence): mono microtype for labels and
// metadata, ink CTAs, underline fields, numbered section marks. Titles use the
// app's default sans; data and labels use IBM Plex Mono (font-mono).

// Every label/eyebrow is set in mono caps.
export const eyebrow =
  'font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground'

// Inline metadata chip (mode, scope, provenance, optional fields).
export const monoTag =
  'inline-flex items-center rounded-sm border border-foreground/20 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground'

// Ink CTA — primary action is foreground-on-background, not the brand blue.
export const inkButton =
  'rounded-sm bg-foreground font-mono text-xs uppercase tracking-[0.14em] text-background hover:bg-foreground/85'

export const ghostButton =
  'rounded-sm border-foreground/25 font-mono text-xs uppercase tracking-[0.14em] hover:bg-foreground/[0.04]'

// Underline-style field — forms read like a printed brief.
export const fieldInput =
  'rounded-none border-0 border-b border-foreground/30 bg-transparent px-0 shadow-none focus-visible:border-foreground focus-visible:ring-0 focus-visible:ring-offset-0 focus:ring-0 focus:ring-offset-0'

// Underline tabs instead of the default pill TabsList.
export const tabTrigger =
  'rounded-none border-b-2 border-transparent bg-transparent px-0 pb-3 pt-0 font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none'
