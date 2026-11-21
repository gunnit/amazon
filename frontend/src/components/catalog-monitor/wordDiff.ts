/**
 * Word-level diff for the content comparison views (R3).
 *
 * Longest common subsequence over words; whitespace never counts as a change
 * (the backend compares normalised text too). Every operation carries the text of
 * each side, so each side rebuilds its own string exactly, spacing included.
 * Pure and dependency-free; `npm run check:word-diff` exercises it.
 */

export interface DiffOp {
  type: 'same' | 'removed' | 'added'
  /** This part of the "before" text ('' for an addition). */
  before: string
  /** This part of the "after" text ('' for a removal). */
  after: string
}

// Above this many LCS cells (about 1000 x 1000 words) the middle part is shown
// as one removal and one addition instead of a fine-grained diff.
const MAX_CELLS = 1_000_000

/** Leading whitespace, then words with the whitespace that follows them: joined, they rebuild the text. */
function tokenize(text: string): string[] {
  return text.match(/^\s+|\S+\s*/g) ?? []
}

function push(ops: DiffOp[], type: DiffOp['type'], before: string, after: string) {
  if (!before && !after) return
  const last = ops[ops.length - 1]
  if (last && last.type === type) {
    last.before += before
    last.after += after
  } else {
    ops.push({ type, before, after })
  }
}

export function wordDiff(before: string, after: string): DiffOp[] {
  const a = tokenize(before)
  const b = tokenize(after)
  const ka = a.map((w) => w.trim())
  const kb = b.map((w) => w.trim())
  const ops: DiffOp[] = []
  const same = (i: number, j: number) => push(ops, 'same', a[i], b[j])
  const removed = (i: number) => push(ops, 'removed', a[i], '')
  const added = (j: number) => push(ops, 'added', '', b[j])

  // Common prefix and suffix need no table.
  let start = 0
  while (start < a.length && start < b.length && ka[start] === kb[start]) {
    same(start, start)
    start++
  }
  let endA = a.length
  let endB = b.length
  while (endA > start && endB > start && ka[endA - 1] === kb[endB - 1]) {
    endA--
    endB--
  }

  const n = endA - start
  const m = endB - start
  if (n * m > MAX_CELLS) {
    for (let i = start; i < endA; i++) removed(i)
    for (let j = start; j < endB; j++) added(j)
  } else {
    // lcs[i][j] = LCS length of a[start+i..endA) and b[start+j..endB)
    const width = m + 1
    const lcs = new Uint32Array((n + 1) * width)
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m - 1; j >= 0; j--) {
        lcs[i * width + j] =
          ka[start + i] === kb[start + j]
            ? lcs[(i + 1) * width + j + 1] + 1
            : Math.max(lcs[(i + 1) * width + j], lcs[i * width + j + 1])
      }
    }
    let i = 0
    let j = 0
    while (i < n && j < m) {
      if (ka[start + i] === kb[start + j]) {
        same(start + i, start + j)
        i++
        j++
      } else if (lcs[(i + 1) * width + j] >= lcs[i * width + j + 1]) {
        removed(start + i)
        i++
      } else {
        added(start + j)
        j++
      }
    }
    for (; i < n; i++) removed(start + i)
    for (; j < m; j++) added(start + j)
  }

  for (let k = 0; endA + k < a.length; k++) same(endA + k, endB + k)
  return ops
}

/** One side's text as the diff splits it: every operation that side has. */
export function sideParts(ops: DiffOp[], side: 'before' | 'after'): DiffOp[] {
  return ops.filter((op) => op[side] !== '')
}

/** Whitespace-insensitive text equality, as the backend compares content. */
export function sameText(a: unknown, b: unknown): boolean {
  const norm = (v: unknown) => (typeof v === 'string' ? v.split(/\s+/).filter(Boolean).join(' ') : v)
  return norm(a) === norm(b)
}
