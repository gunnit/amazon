import { test, expect, Page } from '@playwright/test'

const BASE_URL = 'http://localhost:5173'
const TEST_EMAIL = 'test@test.com'
const TEST_PASSWORD = 'Test1234'

async function loginViaUI(page: Page) {
  await page.goto(`${BASE_URL}/login`)
  await page.waitForLoadState('networkidle')
  await page.fill('input#email', TEST_EMAIL)
  await page.fill('input#password', TEST_PASSWORD)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL(BASE_URL + '/', { timeout: 10000 })
  await page.waitForLoadState('networkidle')
}

test('analytics ads vs organic tab requests the new endpoint', async ({ page }) => {
  const requests: string[] = []

  page.on('request', (request) => {
    if (request.url().includes('/api/v1/analytics/ads-vs-organic')) {
      requests.push(request.url())
    }
  })

  await loginViaUI(page)
  await page.goto(`${BASE_URL}/analytics`)
  await page.waitForLoadState('networkidle')

  await page.getByRole('tab', { name: /ads vs organic|ads vs organico/i }).click()
  await page.waitForTimeout(1500)
  await page.waitForLoadState('networkidle')

  await expect(
    page.getByText(/Advertising vs Organic Sales|Vendite Advertising vs Organiche/i).first()
  ).toBeVisible()
  expect(requests.length).toBeGreaterThanOrEqual(1)
})
