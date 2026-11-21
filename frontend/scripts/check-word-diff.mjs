// Checks the word diff behind the side-by-side content comparison (Catalogo >
// Protezione contenuti): each side must rebuild its own text, words and spacing
// included, and only the words the other side lacks may be highlighted.
// Run: npm run check:word-diff
import { readFileSync } from 'node:fs'
import { transformSync } from 'esbuild' // vite's own dependency: no extra package

const source = readFileSync(
  new URL('../src/components/catalog-monitor/wordDiff.ts', import.meta.url),
  'utf8',
)
const { code } = transformSync(source, { loader: 'ts', format: 'esm' })
const { wordDiff, sideParts, sameText } = await import(
  `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
)

let failures = 0
const check = (name, actual, expected) => {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  if (!ok) {
    failures++
    console.error(`FAIL ${name}\n  expected ${JSON.stringify(expected)}\n  got      ${JSON.stringify(actual)}`)
  }
}
// What a side renders: its text, with **highlighted** parts.
const render = (ops, side) =>
  sideParts(ops, side)
    .map((op) => (op.type === 'same' ? op[side] : `**${op[side]}**`))
    .join('')
const rebuilt = (ops, side) => sideParts(ops, side).map((op) => op[side]).join('')

const cases = [
  ['one two three', 'one two'],
  ['one two', 'one two three'],
  ['Borraccia termica TESTBRAND 500 ml acciaio', 'Borraccia TESTBRAND 750 ml in acciaio inox'],
  ['uguale  testo\ncon a capo', 'uguale testo con a capo'],
  ['  spazio iniziale', 'spazio iniziale  '],
  ['', 'nuovo titolo'],
  ['vecchio titolo', ''],
  ['a b c', 'c b a'],
]
for (const [before, after] of cases) {
  const ops = wordDiff(before, after)
  check(`before side rebuilds ${JSON.stringify(before)}`, rebuilt(ops, 'before'), before)
  check(`after side rebuilds ${JSON.stringify(after)}`, rebuilt(ops, 'after'), after)
}

check('removed tail keeps its space', render(wordDiff('one two three', 'one two'), 'before'), 'one two **three**')
check('removed tail, after side', render(wordDiff('one two three', 'one two'), 'after'), 'one two')
check('added tail', render(wordDiff('one two', 'one two three'), 'after'), 'one two **three**')
check(
  'changed words, before side',
  render(wordDiff('Borraccia termica TESTBRAND 500 ml', 'Borraccia TESTBRAND 750 ml'), 'before'),
  'Borraccia **termica **TESTBRAND **500 **ml',
)
check(
  'changed words, after side',
  render(wordDiff('Borraccia termica TESTBRAND 500 ml', 'Borraccia TESTBRAND 750 ml'), 'after'),
  'Borraccia TESTBRAND **750 **ml',
)
check('whitespace is no change', wordDiff('a  b', 'a b').map((op) => op.type), ['same'])
check('sameText ignores spacing', [sameText('a  b', 'a b'), sameText('a', 'b')], [true, false])

const big = Array.from({ length: 1200 }, (_, i) => `w${i}`).join(' ')
const coarse = wordDiff(big, `x ${big.split(' ').reverse().join(' ')}`)
check('large input falls back to one removal and one addition', coarse.map((op) => op.type), ['removed', 'added'])

if (failures) {
  console.error(`word diff: ${failures} check(s) failed`)
  process.exit(1)
}
console.log('word diff OK')
