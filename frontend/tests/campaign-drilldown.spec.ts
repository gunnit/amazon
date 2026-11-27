import { expect, test, type Page } from '@playwright/test'

const account = '10000000-0000-4000-8000-000000000011'
const otherAccount = '10000000-0000-4000-8000-000000000012'
const start = '2026-11-02'
const end = '2026-11-10'
const campaignId = '1201'
const name = 'Private brand campaign'
const asin = 'B0PRIVATE01'
const keyword = 'private brand keyword'
const metrics = {
  spend: '25', sales: '100', clicks: 50, impressions: 2000, ctr: '2.5', cpc: '0.5',
  roas: '4', acos: '25', orders: null, units: 8, conversion_rate: null,
}
const campaign = { ...metrics, account_id: account, campaign_id: campaignId, campaign_name: name, campaign_type: 'sponsoredProducts', state: 'enabled' }
const browserErrors = new WeakMap<Page, string[]>()

test.beforeEach(async ({ page }) => {
  const errors: string[] = []
  browserErrors.set(page, errors)
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', item => {
    if (item.type() === 'error') errors.push(item.text())
  })
  await page.addInitScript(({ start, end }) => {
    localStorage.setItem('access_token', 'fixture-token')
    if (!sessionStorage.getItem('inthezon-filters')) {
      sessionStorage.setItem('inthezon-filters', JSON.stringify({
        state: { datePreset: 'custom', customStartDate: start, customEndDate: end }, version: 0,
      }))
    }
  }, { start, end })
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    switch (url.pathname) {
      case '/api/v1/auth/me':
        return route.fulfill({ json: { id: account, email: 'qa@example.test', full_name: 'QA' } })
      case '/api/v1/auth/organization':
        return route.fulfill({ json: { id: account, name: 'QA', slug: 'qa', role: 'admin' } })
      case '/api/v1/accounts':
        return route.fulfill({ json: [account, otherAccount].map(id => ({
          id, account_name: 'Demo vendor', marketplace_country: 'IT', account_type: 'vendor',
          is_active: true, ads_connection_state: 'ok',
        })) })
      case '/api/v1/analytics/advertising':
        return route.fulfill({ json: {
          total_impressions: 2000, total_spend: 25, total_sales: 100,
          top_campaigns: [campaign], underperforming_campaigns: [], recommendations: [],
          campaigns: [campaign, ...Array.from({ length: 24 }, (_, i) => ({
            ...campaign, campaign_id: String(i + 10), campaign_name: `Campaign ${i + 1}`,
          })), { ...campaign, account_id: otherAccount, campaign_name: 'Other campaign' }],
        } })
      case '/api/v1/analytics/ads-vs-organic':
        return route.fulfill({ json: {
          summary: { total_sales: { value: 100, previous_value: 0, change_percent: 0, trend: 'flat' } },
          time_series: [], asin_breakdown: [], attribution_notes: [], ads_coverage: 'none',
        } })
      case `/api/v1/analytics/advertising/campaigns/${campaignId}`: {
        const id = url.searchParams.get('account_id')
        expect([account, otherAccount]).toContain(id)
        expect(url.searchParams.get('start_date')).toBe(start)
        expect(url.searchParams.get('end_date')).toBe(end)
        const isSP = id === account
        return route.fulfill({ json: {
          ...campaign, account_id: id, campaign_type: isSP ? 'sponsoredProducts' : 'sponsoredBrands',
          campaign_name: isSP ? name : 'Other campaign', marketplace_country: 'IT', currency: 'EUR',
          start_date: start, end_date: end, totals: metrics, daily: [{ ...metrics, date: start }],
          products: isSP ? [{ ...metrics, asin }] : [],
          keywords: isSP ? [{ ...metrics, keyword, match_type: 'EXACT' }] : [],
        } })
      }
      default:
        return route.fulfill({ json: [] })
    }
  })
})

test.afterEach(async ({ page }) => {
  expect(browserErrors.get(page)).toEqual([])
  await expect(page.locator('vite-error-overlay')).toHaveCount(0)
})

test('masked campaign drill-down preserves dates, metrics and keyword match types across navigation and refresh', async ({ page }) => {
  await page.goto('/advertising')
  await expect(page.getByRole('link', { name })).toBeVisible()
  await page.getByRole('switch', { name: 'Maschera identificativi campagna' }).click()
  await expect(page.getByText(name)).toHaveCount(0)
  const alias = page.getByRole('link', { name: /^Campagna [A-Z\d]+$/ })
  const aliasText = await alias.innerText()
  await alias.click()
  await expect(page.getByRole('heading', { name: aliasText })).toBeVisible()
  await expect(page.getByText('Prodotto 1')).toBeVisible()
  await expect(page.getByText(asin)).toHaveCount(0)
  await expect(page.locator('dt').filter({ hasText: 'Ordini attribuiti' }).locator('..')).toContainText('n/d')
  await page.reload()
  await page.getByRole('tab', { name: 'Parole chiave' }).click()
  await expect(page.getByText('Parola chiave 1')).toBeVisible()
  await expect(page.getByText('EXACT')).toBeVisible()
  const html = await page.locator('main').innerHTML()
  for (const privateText of [name, asin, keyword]) expect(html).not.toContain(privateText)
  await page.getByRole('switch', { name: 'Maschera identificativi campagna' }).click()
  await expect(page.getByText(keyword)).toBeVisible()
  await expect(page.getByRole('heading', { name })).toBeVisible()
  await page.getByRole('tab', { name: 'Per giorno' }).click()
  await expect(page.getByRole('rowheader', { name: '2 novembre 2026' })).toBeVisible()
  await page.getByRole('switch', { name: 'Maschera identificativi campagna' }).click()
  await page.getByRole('tab', { name: 'Prodotti pubblicizzati' }).click()
  await expect(page.getByText('Prodotto 1')).toBeVisible()
})

test('Performance keeps separate accounts with the same campaign ID and opens the matching campaign type', async ({ page }) => {
  await page.goto('/performance?tab=ads-vs-organic')
  await expect(page.getByRole('link', { name })).toBeVisible()
  await page.getByRole('button', { name: 'Successiva' }).click()
  await page.getByRole('link', { name: 'Other campaign' }).click()
  await expect(page).toHaveURL(new RegExp(`/campaigns/${otherAccount}/${campaignId}`))
  await expect(page.getByRole('tab', { name: 'Per giorno' })).toHaveAttribute('aria-selected', 'true')
  await page.getByRole('tab', { name: 'Prodotti pubblicizzati' }).click()
  await expect(page.getByText('Il dettaglio per prodotto è disponibile per le campagne Sponsored Products.')).toBeVisible()
  await page.getByRole('switch', { name: 'Maschera identificativi campagna' }).click()
  await page.locator('main').getByRole('link', { name: /ads|pubblicit/i }).click()
  await expect(page).toHaveURL(/performance\?tab=ads-vs-organic#campaigns$/)
  await expect(page.getByRole('link', { name: /^Campagna [A-Z\d]+$/ })).toHaveCount(25)
  await expect(page.getByText('Other campaign')).toHaveCount(0)
})

test('Advertising opens campaigns outside the two rankings', async ({ page }) => {
  await page.goto('/advertising')
  await page.getByRole('combobox', { name: 'Tutte le campagne' }).selectOption({ label: 'Other campaign' })
  await expect(page).toHaveURL(new RegExp(`/campaigns/${otherAccount}/${campaignId}`))
  await expect(page.getByRole('heading', { name: 'Other campaign' })).toBeVisible()
})

test('a direct presentation link masks campaign identifiers on the first render and after refresh', async ({ page }) => {
  await page.addInitScript(({ name, asin, keyword }) => {
    // Watch every inserted node, including those removed before the first assertion.
    new MutationObserver(records => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (!(node instanceof HTMLElement) || !node.closest('main')) continue
          if ([name, asin, keyword].some(value => node.textContent?.includes(value))) {
            document.documentElement.dataset.privateLabelRendered = 'true'
          }
        }
      }
    }).observe(document, { childList: true, subtree: true })
  }, { name, asin, keyword })
  await page.goto(`/advertising/campaigns/${account}/${campaignId}?start_date=${start}&end_date=${end}&presentation=1`)
  for (const refresh of [false, true]) {
    if (refresh) await page.reload()
    await expect(page.getByRole('heading', { name: /^Campagna [A-Z\d]+$/ })).toBeVisible()
    await expect(page.getByText('Prodotto 1')).toBeVisible()
    await page.getByRole('tab', { name: 'Parole chiave' }).click()
    await expect(page.getByText('Parola chiave 1')).toBeVisible()
    await expect(page.getByRole('switch')).toBeChecked()
    await expect(page.locator('html')).not.toHaveAttribute('data-private-label-rendered', 'true')
  }
  await page.getByRole('switch').click()
  await expect(page.getByRole('heading', { name })).toBeVisible()
  await expect(page).not.toHaveURL(/presentation=1/)
})
