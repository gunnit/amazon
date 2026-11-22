// Checks the access-token refresh behind the API client (src/services/tokenRefresh.ts):
// parallel 401s share one refresh, a request sent with an old token is retried
// without refreshing, and only a refused refresh (401/403) or a missing refresh
// token logs the user out — a 429 or a network error keeps the session.
// Run: npm run check:token-refresh
import { readFileSync } from 'node:fs'
import { transformSync } from 'esbuild' // vite's own dependency: no extra package

const source = readFileSync(new URL('../src/services/tokenRefresh.ts', import.meta.url), 'utf8')
const { code } = transformSync(source, { loader: 'ts', format: 'esm' })
const { createTokenRefresher } = await import(
  `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
)

let failures = 0
const check = (name, actual, expected) => {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    failures++
    console.error(`FAIL ${name}\n  expected ${JSON.stringify(expected)}\n  got      ${JSON.stringify(actual)}`)
  }
}

const httpError = (status) => Object.assign(new Error(`HTTP ${status}`), { response: { status } })
const tick = () => new Promise((resolve) => setTimeout(resolve, 5))

/** A refresher over in-memory tokens; ``answer`` decides what the refresh endpoint does. */
function setup({ access = 'A1', refresh = 'R1', answer } = {}) {
  const state = { access, refresh, refreshCalls: [], redirects: 0, cleared: 0 }
  const store = {
    getAccess: () => state.access,
    getRefresh: () => state.refresh,
    save: (tokens) => {
      state.access = tokens.access_token
      state.refresh = tokens.refresh_token
    },
    clear: () => {
      state.access = null
      state.refresh = null
      state.cleared++
    },
  }
  const refresher = createTokenRefresher({
    store,
    requestRefresh: async (token) => {
      state.refreshCalls.push(token)
      await tick() // the other 401s arrive while this one is in flight
      if (answer) return answer(token)
      return { access_token: 'A2', refresh_token: 'R2' }
    },
    redirectToLogin: () => {
      state.redirects++
    },
  })
  // A request sent with ``sent``: resolves with the token it is retried with.
  const fail401 = (sent) => {
    const error = httpError(401)
    return refresher.recover(sent ? `Bearer ${sent}` : undefined, async (token) => `retried with ${token}`, error)
  }
  return { state, refresher, fail401 }
}

// 1. Five parallel 401s: one refresh, every request retried with the new token.
{
  const { state, fail401 } = setup()
  const results = await Promise.all([1, 2, 3, 4, 5].map(() => fail401('A1')))
  check('parallel 401s share one refresh', state.refreshCalls, ['R1'])
  check('every request retried with the new token', results, Array(5).fill('retried with A2'))
  check('both tokens stored', [state.access, state.refresh], ['A2', 'R2'])
  check('no logout', state.redirects, 0)
}

// 2. A late 401 from a request sent with the old token: retried, no second refresh.
{
  const { state, fail401 } = setup()
  await fail401('A1')
  const late = await fail401('A1')
  check('late 401 retried with the stored token', late, 'retried with A2')
  check('late 401 does not refresh again', state.refreshCalls, ['R1'])
}

// 3. After a refresh settles, the next expiry refreshes again (the in-flight promise is cleared).
{
  let n = 1
  const { state, fail401 } = setup({
    answer: () => {
      n++
      return { access_token: `A${n}`, refresh_token: `R${n}` }
    },
  })
  await fail401('A1')
  const again = await fail401('A2')
  check('a new expiry starts a new refresh', state.refreshCalls, ['R1', 'R2'])
  check('retried with the newest token', again, 'retried with A3')
}

// 4. Refresh rate-limited (429): the request fails, the session stays, a later 401 retries the refresh.
{
  let limited = true
  const { state, fail401 } = setup({
    answer: () => {
      if (limited) throw httpError(429)
      return { access_token: 'A2', refresh_token: 'R2' }
    },
  })
  const outcomes = await Promise.allSettled([fail401('A1'), fail401('A1')])
  check('429: the requests reject', outcomes.map((o) => o.status), ['rejected', 'rejected'])
  check('429: with the original 401', outcomes.map((o) => o.reason?.response?.status), [401, 401])
  check('429: one refresh for both', state.refreshCalls, ['R1'])
  check('429: no logout, tokens kept', [state.redirects, state.cleared, state.access, state.refresh], [0, 0, 'A1', 'R1'])
  limited = false
  check('429: the next 401 refreshes again', await fail401('A1'), 'retried with A2')
}

// 5. Network error during the refresh: no logout.
{
  const { state, fail401 } = setup({
    answer: () => {
      throw new Error('Network Error') // no response: axios network failure
    },
  })
  const outcome = await Promise.allSettled([fail401('A1')])
  check('network error: rejected', outcome[0].status, 'rejected')
  check('network error: no logout', [state.redirects, state.access], [0, 'A1'])
}

// 6. The backend refuses the refresh token (401 or 403): logged out once per refresh.
for (const status of [401, 403]) {
  const { state, fail401 } = setup({
    answer: () => {
      throw httpError(status)
    },
  })
  const outcomes = await Promise.allSettled([fail401('A1'), fail401('A1'), fail401('A1')])
  check(`refresh ${status}: requests reject`, outcomes.map((o) => o.status), ['rejected', 'rejected', 'rejected'])
  check(`refresh ${status}: tokens cleared`, [state.access, state.refresh], [null, null])
  check(`refresh ${status}: one refresh call`, state.refreshCalls, ['R1'])
  check(`refresh ${status}: redirected to login`, state.redirects > 0, true)
}

// 7. No refresh token: logged out without calling the endpoint.
{
  const { state, fail401 } = setup({ refresh: null })
  const outcome = await Promise.allSettled([fail401('A1')])
  check('no refresh token: rejected', outcome[0].status, 'rejected')
  check('no refresh token: no refresh call', state.refreshCalls, [])
  check('no refresh token: logged out', [state.redirects, state.access], [1, null])
}

if (failures) {
  console.error(`${failures} token refresh check(s) failed`)
  process.exit(1)
}
console.log('token refresh ok')
