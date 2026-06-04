import { test, expect, Page } from '@playwright/test';

const BASE_URL = 'http://localhost:5173';
const TEST_EMAIL = 'peppepretto@gmail.com';
const TEST_PASSWORD = 'QaTest123!';

async function loginViaUI(page: Page) {
  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState('networkidle');

  await page.fill('input#email', TEST_EMAIL);
  await page.fill('input#password', TEST_PASSWORD);

  await page.getByRole('button', { name: /sign in/i }).click();

  await page.waitForURL(BASE_URL + '/', { timeout: 10000 });
  await page.waitForLoadState('networkidle');
}

test.describe('Brand Analysis navigation', () => {
  test('sidebar link navigates to /brand-analysis and renders the page', async ({ page }) => {
    await loginViaUI(page);

    const navLink = page.locator('aside a, nav a').filter({ has: page.locator('svg') }).filter({
      hasText: /Analisi Brand|Brand Analysis/i,
    }).first();

    await expect(navLink).toBeVisible();
    await expect(navLink).toHaveAttribute('href', '/brand-analysis');

    await navLink.click();
    await page.waitForURL(`${BASE_URL}/brand-analysis`, { timeout: 10000 });

    await expect(page).toHaveURL(`${BASE_URL}/brand-analysis`);
    await expect(
      page.getByRole('heading', { level: 1, name: /Analisi Brand|Brand Analysis/i })
    ).toBeVisible();
  });
});
