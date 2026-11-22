// Access-token refresh for the API client, kept free of axios and the browser so
// `npm run check:token-refresh` can run it under node with fakes.
//
// When the 30-minute access token expires, every request in flight answers 401.
// They must share one refresh: the backend rotates (revokes) the refresh token,
// and a burst of refreshes also hits its rate limit. Rules:
//   - a request sent with an older token than the stored one is just retried;
//   - otherwise it waits for the single refresh in flight (or starts it), then
//     retries once with the new token;
//   - the user is logged out only when there is no refresh token or the refresh
//     itself answers 401/403; a 429 or a network error rejects the request and
//     keeps the session, so the next request can try again.

export interface TokenPair {
  access_token: string
  refresh_token: string
}

export interface TokenStore {
  getAccess(): string | null
  getRefresh(): string | null
  save(tokens: TokenPair): void
  clear(): void
}

export interface RefresherDeps {
  store: TokenStore
  /** POST /auth/refresh; rejects with the HTTP error (axios-shaped: `response.status`). */
  requestRefresh(refreshToken: string): Promise<TokenPair>
  /** Leave for the login page; called after the tokens are cleared. */
  redirectToLogin(): void
}

/** Thrown by refreshAccessToken when there is no refresh token to use. */
export class NoRefreshToken extends Error {
  constructor() {
    super('No refresh token')
    this.name = 'NoRefreshToken'
  }
}

const statusOf = (error: unknown): number | undefined =>
  (error as { response?: { status?: number } } | null)?.response?.status

/** The session is over: no refresh token, or the backend refused the refresh token. */
export const endsSession = (refreshError: unknown): boolean =>
  refreshError instanceof NoRefreshToken || statusOf(refreshError) === 401 || statusOf(refreshError) === 403

export function createTokenRefresher(deps: RefresherDeps) {
  let refreshing: Promise<string> | null = null

  /** The new access token; concurrent callers share one refresh call. */
  function refreshAccessToken(): Promise<string> {
    if (refreshing === null) {
      refreshing = (async () => {
        const refreshToken = deps.store.getRefresh()
        if (!refreshToken) throw new NoRefreshToken()
        const tokens = await deps.requestRefresh(refreshToken)
        deps.store.save(tokens)
        return tokens.access_token
      })().finally(() => {
        refreshing = null
      })
    }
    return refreshing
  }

  /**
   * Recover a request that answered 401. ``sentAuthorization`` is the header it
   * was sent with; ``retry`` resends it with the given access token. Rejects with
   * ``error`` (the original 401) when the session cannot be recovered now.
   */
  async function recover<T>(
    sentAuthorization: string | undefined | null,
    retry: (accessToken: string) => Promise<T>,
    error: unknown,
  ): Promise<T> {
    const current = deps.store.getAccess()
    if (current && sentAuthorization !== `Bearer ${current}`) {
      return retry(current) // refreshed meanwhile by another request
    }
    let token: string
    try {
      token = await refreshAccessToken()
    } catch (refreshError) {
      if (endsSession(refreshError)) {
        deps.store.clear()
        deps.redirectToLogin()
      }
      throw error
    }
    return retry(token)
  }

  return { refreshAccessToken, recover }
}
