/**
 * Heuristics for detecting placeholder account names that need to be renamed
 * to real client-facing names.
 *
 * We deliberately keep this client-side so it's easy to extend without a
 * migration. The list mirrors the placeholders we've seen used in early
 * production data and obvious testing values.
 */

const PLACEHOLDER_EXACT = new Set<string>([
  'real',
  'real account',
  'fake',
  'fake account',
  'second',
  'second account',
  'first',
  'first account',
  'primary',
  'primary account',
  'main',
  'main account',
  'test',
  'test account',
  'demo',
  'demo account',
  'sample',
  'sample account',
  'placeholder',
  'default',
  'tbd',
  'todo',
  'unnamed',
  'no name',
  'new account',
  'my store',
])

const PLACEHOLDER_PREFIX = ['account ', 'accounts ']

export function isPlaceholderAccountName(name: string | null | undefined): boolean {
  if (!name) return true
  const normalized = name.trim().toLowerCase()
  if (!normalized) return true
  if (PLACEHOLDER_EXACT.has(normalized)) return true
  if (PLACEHOLDER_PREFIX.some((prefix) => normalized.startsWith(prefix))) {
    // e.g. "account 1", "account #2"
    return /^accounts?\s+#?\d+$/i.test(name.trim())
  }
  return false
}
