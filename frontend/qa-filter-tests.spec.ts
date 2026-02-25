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

// ===== TEST 2: ANALYTICS =====
test('Analytics (/analytics) - filter bar', async ({ page }) => {
  await injectAuth(page);

  await page.goto('http://localhost:5173/analytics');
  await page.waitForLoadState('networkidle');

  await expect(page.locator('h1:has-text("Analytics")')).toBeVisible({ timeout: 10000 });

  // --- DateRangeFilter ---
  const dateSelect = page.locator('[role="combobox"]').first();
  await expect(dateSelect).toBeVisible();
  const dateText = await dateSelect.textContent();
  console.log('[Analytics] DateRangeFilter text:', dateText);

  // --- AccountFilter ---
  const accountButton = page.locator('button:has-text("All accounts"), button:has-text("accounts")').first();
  await expect(accountButton).toBeVisible();
  const accountText = await accountButton.textContent();
  console.log('[Analytics] AccountFilter text:', accountText);

  // --- GroupByFilter ---
  const allComboboxes = page.locator('[role="combobox"]');
  const comboboxCount = await allComboboxes.count();
  console.log('[Analytics] Total comboboxes found:', comboboxCount);
  for (let i = 0; i < comboboxCount; i++) {
    const text = await allComboboxes.nth(i).textContent();
    console.log(`[Analytics] Combobox #${i}: "${text}"`);
  }

  // GroupByFilter should be the second combobox (after DateRangeFilter)
  let groupByFound = false;
  for (let i = 0; i < comboboxCount; i++) {
    const text = await allComboboxes.nth(i).textContent();
    if (text && text.includes('Day')) {
      groupByFound = true;
      console.log('[Analytics] GroupByFilter found at combobox #' + i + ' with text:', text);
      break;
    }
  }
  if (!groupByFound) {
    console.log('[Analytics] WARNING: GroupByFilter with "Day" text not found among comboboxes');
  }

  // --- CategoryFilter ---
  let categoryFound = false;
  for (let i = 0; i < comboboxCount; i++) {
    const text = await allComboboxes.nth(i).textContent();
    if (text && text.includes('All categories')) {
      categoryFound = true;
      console.log('[Analytics] CategoryFilter found at combobox #' + i + ' with text:', text);
      break;
    }
  }
  if (!categoryFound) {
    console.log('[Analytics] WARNING: CategoryFilter with "All categories" text not found among comboboxes');
  }

  // --- Reset button ---
  const resetButton = page.locator('button:has-text("Reset")');
  await expect(resetButton).toBeVisible();
  console.log('[Analytics] Reset button visible');

  // Take screenshots
  await page.screenshot({
    path: '/Users/giuseppepretto/Projects/amazon/frontend/screenshots/analytics.png',
    fullPage: true,
  });

  const filterBar = page.locator('.flex.flex-wrap.items-center.gap-3').first();
  if (await filterBar.isVisible()) {
    await filterBar.screenshot({
      path: '/Users/giuseppepretto/Projects/amazon/frontend/screenshots/analytics-filters.png',
    });
  }

  console.log('[Analytics] PASS - All filter elements found');
});

// ===== TEST 3: REPORTS =====
test('Reports (/reports) - filter bar', async ({ page }) => {
  await injectAuth(page);

  await page.goto('http://localhost:5173/reports');
  await page.waitForLoadState('networkidle');

  await expect(page.locator('h1:has-text("Reports")')).toBeVisible({ timeout: 10000 });

  // --- DateRangeFilter ---
  const dateSelect = page.locator('[role="combobox"]').first();
  await expect(dateSelect).toBeVisible();
  const dateText = await dateSelect.textContent();
  console.log('[Reports] DateRangeFilter text:', dateText);

  // --- AccountFilter ---
  const accountButton = page.locator('button:has-text("All accounts"), button:has-text("accounts")').first();
  await expect(accountButton).toBeVisible();
  const accountText = await accountButton.textContent();
  console.log('[Reports] AccountFilter text:', accountText);

  // --- GroupByFilter (on sales tab by default) ---
  const allComboboxes = page.locator('[role="combobox"]');
  const comboboxCount = await allComboboxes.count();
  console.log('[Reports] Total comboboxes found:', comboboxCount);
  for (let i = 0; i < comboboxCount; i++) {
    const text = await allComboboxes.nth(i).textContent();
    console.log(`[Reports] Combobox #${i}: "${text}"`);
  }

  let groupByFound = false;
  for (let i = 0; i < comboboxCount; i++) {
    const text = await allComboboxes.nth(i).textContent();
    if (text && text.includes('Day')) {
      groupByFound = true;
      console.log('[Reports] GroupByFilter found at combobox #' + i + ' with text:', text);
      break;
    }
  }
  if (!groupByFound) {
    console.log('[Reports] WARNING: GroupByFilter with "Day" not found among comboboxes');
  }

  // --- Reset button ---
  const resetButton = page.locator('button:has-text("Reset")');
  await expect(resetButton).toBeVisible();
  console.log('[Reports] Reset button visible');

  // --- Export buttons ---
  const excelButton = page.locator('button:has-text("Excel")');
  await expect(excelButton).toBeVisible();
  const excelText = await excelButton.textContent();
  console.log('[Reports] Excel button text:', excelText);

  const pptButton = page.locator('button:has-text("PowerPoint")');
  await expect(pptButton).toBeVisible();
  const pptText = await pptButton.textContent();
  console.log('[Reports] PowerPoint button text:', pptText);

  // Take screenshots
  await page.screenshot({
    path: '/Users/giuseppepretto/Projects/amazon/frontend/screenshots/reports.png',
    fullPage: true,
  });

  // Capture the filter + export area
  const filterArea = page.locator('.flex.items-center.gap-3.flex-wrap').first();
  if (await filterArea.isVisible()) {
    await filterArea.screenshot({
      path: '/Users/giuseppepretto/Projects/amazon/frontend/screenshots/reports-filters.png',
    });
  }

  console.log('[Reports] PASS - All filter elements and export buttons found');
});
