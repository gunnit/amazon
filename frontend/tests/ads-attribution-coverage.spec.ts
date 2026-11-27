import { expect, test } from '@playwright/test'

const bitronId = '10000000-0000-4000-8000-000000000011'
const organizationId = '20000000-0000-4000-8000-000000000002'
const createdAt = '2026-01-01T00:00:00Z'

const cases = [
  { ads: 'none', retail: 'full', priorAds: 'none', priorRetail: 'full', start: '2026-10-01', end: '2026-10-31' },
  { ads: 'partial', retail: 'full', priorAds: 'full', priorRetail: 'full', start: '2026-08-01', end: '2026-08-23' },
  { ads: 'full', retail: 'full', priorAds: 'none', priorRetail: 'full', start: '2026-08-01', end: '2026-08-07' },
  { ads: 'full', retail: 'none', priorAds: 'full', priorRetail: 'full', start: '2026-10-01', end: '2026-10-07' },
  { ads: 'full', retail: 'partial', priorAds: 'full', priorRetail: 'full', start: '2026-10-01', end: '2026-10-07' },
  { ads: 'full', retail: 'full', priorAds: 'full', priorRetail: 'partial', start: '2026-10-01', end: '2026-10-07' },
  { ads: 'full', retail: 'full', priorAds: 'full', priorRetail: 'full', start: '2026-10-01', end: '2026-10-07' },
] as const

for (const { ads, retail, priorAds, priorRetail, start, end } of cases) {
  test(`Ads ${ads}/${priorAds} and Retail ${retail}/${priorRetail} preserve independent source metrics`, async ({ page }) => {
    await page.addInitScript(({ id, start, end }) => {
      localStorage.setItem('access_token', 'local-test-token')
      sessionStorage.setItem('inthezon-filters', JSON.stringify({
        state: { accountIds: [id], datePreset: 'custom', customStartDate: start, customEndDate: end },
        version: 0,
      }))
    }, { id: bitronId, start, end })

    // Deliberately supply values even with missing coverage to check that old
    // cached payloads never reveal a zero-Retail split or an unsupported delta.
    const metric = (value: number) => ({ value, previous_value: 100, change_percent: 100, trend: 'up' })
    const adSales = 200
    await page.route('**/api/v1/**', async (route) => {
      const url = new URL(route.request().url())
      switch (url.pathname) {
        case '/api/v1/auth/me':
          return route.fulfill({ json: {
            id: bitronId, email: 'qa@example.test', full_name: 'QA User',
            is_active: true, is_superuser: false, created_at: createdAt,
          } })
        case '/api/v1/auth/organization':
          return route.fulfill({ json: {
            id: organizationId, name: 'QA Organization', slug: 'qa',
            timezone: 'Europe/Rome', role: 'admin', created_at: createdAt,
          } })
        case '/api/v1/accounts':
          return route.fulfill({ json: [{
            id: bitronId, account_name: 'Bitron', account_type: 'seller',
            marketplace_country: 'IT', is_active: true, ads_connection_state: 'auth_failure',
          }] })
        case '/api/v1/analytics/ads-vs-organic':
          expect(url.searchParams.getAll('account_ids')).toEqual([bitronId])
          expect(url.searchParams.get('date_from')).toBe(start)
          expect(url.searchParams.get('date_to')).toBe(end)
          return route.fulfill({ json: {
            summary: {
              total_sales: metric(1000), ad_spend: metric(75), ad_sales: metric(adSales), organic_sales: metric(1000 - adSales),
              ad_share_pct: metric(adSales / 10), organic_share_pct: metric(100 - adSales / 10),
            },
            time_series: [{ date: start, total_sales: 1000, ad_sales: adSales, organic_sales: 1000 - adSales }],
            asin_breakdown: [],
            attribution_notes: [],
            ads_data_from: '2026-04-28',
            ads_data_until: '2026-08-30',
            ads_coverage: ads, previous_ads_coverage: priorAds,
            retail_coverage: retail, previous_retail_coverage: priorRetail,
          } })
        default:
          return route.fulfill({ json: [] })
      }
    })

    await page.goto('/performance?tab=ads-vs-organic')
    const total = page.getByText('Vendite totali', { exact: true }).locator('..')
    const spend = page.getByText('Spesa pubblicitaria', { exact: true }).locator('..')
    const paid = page.getByText('Vendite advertising', { exact: true }).first().locator('..')
    const organic = page.getByText('Vendite organiche', { exact: true }).first().locator('..')
    const organicShare = page.getByText('% Organico', { exact: true }).locator('..')
    const chart = page.getByRole('heading', { name: 'Vendite Advertising vs Organiche' })
    await expect(total).toContainText(retail === 'none' ? 'n/d' : /1[.,]000/)
    await expect(spend).toContainText(ads === 'none' ? 'n/d' : /75,00/)
    await expect(paid).toContainText(ads === 'none' ? 'n/d' : /200,00/)
    if (retail === 'partial') await expect(total).toContainText('Totale dei report disponibili')
    if (ads === 'partial') await expect(paid).toContainText('Totale dei report disponibili')
    if (retail !== 'full' || priorRetail !== 'full') await expect(total).not.toContainText('+100')
    if (ads === 'full' && priorAds === 'full') await expect(spend).toContainText('+100')

    if (ads === 'full' && retail === 'full') {
      await expect(organicShare).toContainText('80.0%')
      if (priorAds === 'full' && priorRetail === 'full') {
        await expect(organicShare).toContainText('+100')
      } else {
        await expect(organicShare).not.toContainText('+100')
      }
      await expect(chart).toBeVisible()
    } else {
      await expect(organicShare).toContainText('n/d')
      await expect(organic).toContainText('n/d')
      await expect(organicShare).not.toContainText('100%')
      await expect(page.getByText(/^La ripartizione non è disponibile/)).toBeVisible()
      await expect(chart).toHaveCount(0)
      if (retail === 'none') await expect(page.getByText(/non sono stati importati report sulle vendite Retail/)).toBeVisible()
      if (retail === 'partial') await expect(page.getByText(/report sulle vendite Retail coprono solo parte/)).toBeVisible()
    }
  })
}
