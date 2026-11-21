/**
 * Word-level diff for the content comparison views (R3).
 *
 * Longest common subsequence over words; whitespace never counts as a change
 * (the backend compares normalised text too). Pure and dependency-free.
 */

export interface DiffOp {
  type: 'same' | 'removed' | 'added'
  text: string
}

// Above this many LCS cells (about 1000 x 1000 words) the middle part is shown
// as one removal and one addition instead of a fine-grained diff.
const MAX_CELLS = 1_000_000

/** Words with the whitespace that follows them, so joining the tokens rebuilds the text. */
function tokenize(text: string): string[] {
  return text.match(/\S+\s*/g) ?? []
}

function push(ops: DiffOp[], type: DiffOp['type'], text: string) {
  if (!text) return
  const last = ops[ops.length - 1]
  if (last && last.type === type) last.text += text
  else ops.push({ type, text })
}

export function wordDiff(before: string, after: string): DiffOp[] {
  const a = tokenize(before)
  const b = tokenize(after)
  const ka = a.map((w) => w.trim())
  const kb = b.map((w) => w.trim())
  const ops: DiffOp[] = []

  // Common prefix and suffix need no table.
  let start = 0
  while (start < a.length && start < b.length && ka[start] === kb[start]) start++
  let endA = a.length
  let endB = b.length
  while (endA > start && endB > start && ka[endA - 1] === kb[endB - 1]) {
    endA--
    endB--
  }
  push(ops, 'same', b.slice(0, start).join(''))

  const n = endA - start
  const m = endB - start
  if (n * m > MAX_CELLS) {
    push(ops, 'removed', a.slice(start, endA).join(''))
    push(ops, 'added', b.slice(start, endB).join(''))
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
        push(ops, 'same', b[start + j])
        i++
        j++
      } else if (lcs[(i + 1) * width + j] >= lcs[i * width + j + 1]) {
        push(ops, 'removed', a[start + i])
        i++
      } else {
        push(ops, 'added', b[start + j])
        j++
      }
    }
    while (i < n) push(ops, 'removed', a[start + i++])
    while (j < m) push(ops, 'added', b[start + j++])
  }

  push(ops, 'same', b.slice(endB).join(''))
  return ops
}

/** Whitespace-insensitive text equality, as the backend compares content. */
export function sameText(a: unknown, b: unknown): boolean {
  const norm = (v: unknown) => (typeof v === 'string' ? v.split(/\s+/).filter(Boolean).join(' ') : v)
  return norm(a) === norm(b)
}
