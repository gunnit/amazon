import { expect, test } from '@playwright/test'

const createdAt = '2026-01-01T00:00:00Z'
const user = {
  id: '10000000-0000-4000-8000-000000000001',
  email: 'qa@example.test',
  full_name: 'QA User',
  is_active: true,
  is_superuser: false,
  created_at: createdAt,
}
const organization = {
  id: '20000000-0000-4000-8000-000000000001',
  name: 'QA Organization',
  slug: 'qa',
  timezone: 'Europe/Rome',
  created_at: createdAt,
  role: 'admin',
}

test('custom Performance export saves both dates and submits the selected month', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-11-26T12:00:00Z'))
  await page.addInitScript(() => localStorage.setItem('access_token', 'local-test-token'))

  const exportRequests: URL[] = []
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    switch (url.pathname) {
      case '/api/v1/auth/me':
        return route.fulfill({ json: user })
      case '/api/v1/auth/organization':
        return route.fulfill({ json: organization })
      case '/api/v1/exports/excel-bundle':
        exportRequests.push(url)
        return route.fulfill({
          contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          body: 'test workbook',
        })
      default:
        return route.fulfill({ json: [] })
    }
  })

  await page.goto('/performance?tab=export')
  await page.getByRole('tabpanel', { name: 'Esportazione' }).getByRole('button', { name: 'Esporta', exact: true }).click()

  const dialog = page.getByRole('dialog', { name: 'Esporta Report' })
  await dialog.getByRole('combobox').filter({ hasText: 'Ultimi 12 mesi' }).click()
  await page.getByRole('option', { name: 'Intervallo personalizzato' }).click()

  await expect(page.getByRole('grid').first()).toBeVisible()
  const october = page.getByRole('grid', { name: 'October 2026' })
  if (await october.count() === 0) {
    await page.getByRole('button', { name: 'Go to previous month' }).click()
  }

  const start = october.getByRole('gridcell', { name: '1', exact: true })
  const end = october.getByRole('gridcell', { name: '31', exact: true })
  const exportButton = dialog.getByRole('button', { name: 'Esporta', exact: true })
  await start.click()
  await expect(start).toHaveAttribute('aria-selected', 'true')
  await expect(exportButton).toBeDisabled()
  expect(exportRequests).toHaveLength(0)

  await end.press('Enter')
  await expect(october).toBeHidden()
  await expect(exportButton).toBeEnabled()
  expect(exportRequests).toHaveLength(0)

  const download = page.waitForEvent('download')
  await exportButton.press('Enter')
  expect((await download).suggestedFilename()).toMatch(/^inthezon_export_2026-10-01_2026-10-31_.*\.xlsx$/)
  expect(exportRequests).toHaveLength(1)
  expect(exportRequests[0].searchParams.get('start_date')).toBe('2026-10-01')
  expect(exportRequests[0].searchParams.get('end_date')).toBe('2026-10-31')
})
