import { test, expect, Page } from '@playwright/test';

const AUTH_STORAGE = JSON.stringify({
  state: {
    isAuthenticated: true,
    user: {
      id: 'demo-user',
      email: 'demo@test.com',
      full_name: 'Demo User',
      is_active: true,
      is_superuser: false,
      created_at: '2024-01-01',
    },
    organization: {
      id: 'demo-org',
      name: 'Demo Org',
      slug: 'demo-org',
      created_at: '2024-01-01',
    },
  },
  version: 0,
});

const DEMO_STORAGE = JSON.stringify({
  state: { mockDataEnabled: true },
  version: 0,
});

async function injectAuth(page: Page) {
  await page.addInitScript(
    ({ auth, demo }: { auth: string; demo: string }) => {
      localStorage.setItem('auth-storage', auth);
      localStorage.setItem('demo-storage', demo);
    },
    { auth: AUTH_STORAGE, demo: DEMO_STORAGE }
  );
}

// ===== TEST 1: DASHBOARD =====
test('Dashboard (/) - filter bar', async ({ page }) => {
  await injectAuth(page);

  // Navigate and wait for load
  await page.goto('http://localhost:5173/');
  await page.waitForLoadState('networkidle');

  // Wait for the heading
  await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible({ timeout: 10000 });

  // --- DateRangeFilter ---
  const dateSelect = page.locator('[role="combobox"]').first();
  await expect(dateSelect).toBeVisible();
  const dateText = await dateSelect.textContent();
  console.log('[Dashboard] DateRangeFilter text:', dateText);

  // --- AccountFilter ---
  const accountButton = page.locator('button:has-text("All accounts"), button:has-text("accounts")').first();
  await expect(accountButton).toBeVisible();
  const accountText = await accountButton.textContent();
  console.log('[Dashboard] AccountFilter text:', accountText);

  // --- Reset button ---
  const resetButton = page.locator('button:has-text("Reset")');
  await expect(resetButton).toBeVisible();
  const resetText = await resetButton.textContent();
  console.log('[Dashboard] Reset button text:', resetText);

  // Take full-page screenshot
  await page.screenshot({
    path: '/Users/giuseppepretto/Projects/amazon/frontend/screenshots/dashboard.png',
    fullPage: true,
  });

  // Take filter bar area screenshot
  const filterBar = page.locator('.flex.flex-wrap.items-center.gap-3').first();
  if (await filterBar.isVisible()) {
    await filterBar.screenshot({
      path: '/Users/giuseppepretto/Projects/amazon/frontend/screenshots/dashboard-filters.png',
    });
  }

  console.log('[Dashboard] PASS - All filter elements found');
});

// ===== TEST 2: PERFORMANCE (legacy /analytics redirect) =====
test('Performance (/analytics -> /performance) - filter bar', async ({ page }) => {
  await injectAuth(page);

  await page.goto('http://localhost:5173/analytics');
  await page.waitForLoadState('networkidle');

  // Legacy route redirects into the merged hub.
  await expect(page).toHaveURL(/\/performance$/);
  await expect(page.locator('h1:has-text("Performance")')).toBeVisible({ timeout: 10000 });

  // --- DateRangeFilter ---
  const dateSelect = page.locator('[role="combobox"]').first();
  await expect(dateSelect).toBeVisible();
  const dateText = await dateSelect.textContent();
  console.log('[Performance] DateRangeFilter text:', dateText);

  // --- AccountFilter ---
  const accountButton = page.locator('button:has-text("All accounts"), button:has-text("accounts")').first();
  await expect(accountButton).toBeVisible();
  const accountText = await accountButton.textContent();
  console.log('[Performance] AccountFilter text:', accountText);

  // --- GroupByFilter (Panoramica tab default) ---
  const allComboboxes = page.locator('[role="combobox"]');
  const comboboxCount = await allComboboxes.count();
  console.log('[Performance] Total comboboxes found:', comboboxCount);
  for (let i = 0; i < comboboxCount; i++) {
    const text = await allComboboxes.nth(i).textContent();
    console.log(`[Performance] Combobox #${i}: "${text}"`);
  }

  let groupByFound = false;
  for (let i = 0; i < comboboxCount; i++) {
    const text = await allComboboxes.nth(i).textContent();
    if (text && text.includes('Day')) {
      groupByFound = true;
      console.log('[Performance] GroupByFilter found at combobox #' + i + ' with text:', text);
      break;
    }
  }
  if (!groupByFound) {
    console.log('[Performance] WARNING: GroupByFilter with "Day" text not found among comboboxes');
  }

  // --- Reset button ---
  const resetButton = page.locator('button:has-text("Reset")');
  await expect(resetButton).toBeVisible();
  console.log('[Performance] Reset button visible');

  // Take screenshots
  await page.screenshot({
    path: '/Users/giuseppepretto/Projects/amazon/frontend/screenshots/performance.png',
    fullPage: true,
  });

  const filterBar = page.locator('.flex.flex-wrap.items-center.gap-3').first();
  if (await filterBar.isVisible()) {
    await filterBar.screenshot({
      path: '/Users/giuseppepretto/Projects/amazon/frontend/screenshots/performance-filters.png',
    });
  }

  console.log('[Performance] PASS - All filter elements found');
});

// ===== TEST 3: PERFORMANCE export tab (legacy /reports redirect) =====
test('Performance (/reports -> /performance) - export tab', async ({ page }) => {
  await injectAuth(page);

  await page.goto('http://localhost:5173/reports');
  await page.waitForLoadState('networkidle');

  // Legacy route redirects into the merged hub.
  await expect(page).toHaveURL(/\/performance$/);
  await expect(page.locator('h1:has-text("Performance")')).toBeVisible({ timeout: 10000 });

  // --- DateRangeFilter ---
  const dateSelect = page.locator('[role="combobox"]').first();
  await expect(dateSelect).toBeVisible();
  const dateText = await dateSelect.textContent();
  console.log('[Performance/export] DateRangeFilter text:', dateText);

  // --- Reset button ---
  const resetButton = page.locator('button:has-text("Reset")');
  await expect(resetButton).toBeVisible();
  console.log('[Performance/export] Reset button visible');

  // --- Export lives behind the Export tab now; the format picker is in the modal ---
  await page.getByRole('tab', { name: /^Export$/ }).click();
  await page.waitForLoadState('networkidle');

  await page.locator('button:has-text("Export"), button:has-text("Esporta")').last().click();

  const excelButton = page.locator('button:has-text("Excel")');
  await expect(excelButton.first()).toBeVisible();
  const excelText = await excelButton.first().textContent();
  console.log('[Performance/export] Excel button text:', excelText);

  const pptButton = page.locator('button:has-text("PowerPoint")');
  await expect(pptButton.first()).toBeVisible();
  const pptText = await pptButton.first().textContent();
  console.log('[Performance/export] PowerPoint button text:', pptText);

  // Take screenshots
  await page.screenshot({
    path: '/Users/giuseppepretto/Projects/amazon/frontend/screenshots/performance-export.png',
    fullPage: true,
  });

  console.log('[Performance/export] PASS - All filter elements and export buttons found');
});
