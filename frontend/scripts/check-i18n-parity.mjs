// Fails if it.ts and en.ts do not carry exactly the same keys — English text
// leaking into the Italian UI has bitten us before.
import { readFileSync } from 'node:fs'

const keys = (file) =>
  new Set(
    [...readFileSync(new URL(`../src/i18n/${file}`, import.meta.url), 'utf8').matchAll(/^\s*'([^']+)':/gm)]
      .map((m) => m[1]),
  )

const it = keys('it.ts')
const en = keys('en.ts')
const missingInEn = [...it].filter((k) => !en.has(k))
const missingInIt = [...en].filter((k) => !it.has(k))

if (missingInEn.length || missingInIt.length) {
  if (missingInEn.length) console.error(`Missing in en.ts (${missingInEn.length}):\n  ${missingInEn.join('\n  ')}`)
  if (missingInIt.length) console.error(`Missing in it.ts (${missingInIt.length}):\n  ${missingInIt.join('\n  ')}`)
  process.exit(1)
}

console.log(`i18n parity OK — ${it.size} keys in both locales`)
