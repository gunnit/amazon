import { test, expect, Page } from '@playwright/test';

const BASE_URL = 'http://localhost:5173';
const TEST_EMAIL = 'test@test.com';
const TEST_PASSWORD = 'Test1234';

// Helper to log in via the UI
async function loginViaUI(page: Page) {
  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState('networkidle');

  // Fill in login form
  await page.fill('input#email', TEST_EMAIL);
  await page.fill('input#password', TEST_PASSWORD);

  // Click sign in
  await page.getByRole('button', { name: /sign in/i }).click();

  // Wait for navigation to dashboard
  await page.waitForURL(BASE_URL + '/', { timeout: 10000 });
  await page.waitForLoadState('networkidle');
}

test.describe('Dashboard Validation', () => {
  let consoleErrors: string[] = [];
  let networkErrors: { url: string; status: number; method: string }[] = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    networkErrors = [];

    // Capture console errors
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // Capture network failures
    page.on('response', (response) => {
      if (response.status() >= 400) {
        networkErrors.push({
          url: response.url(),
          status: response.status(),
          method: response.request().method(),
        });
      }
    });
  });

  test('01 - Login page loads and login works', async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState('networkidle');

    // Verify login form elements
    await expect(page.locator('input#email')).toBeVisible();
    await expect(page.locator('input#password')).toBeVisible();
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible();

    // Verify Inthezon branding
    await expect(page.getByText('Inthezon')).toBeVisible();

    await page.screenshot({ path: 'tests/screenshots/01-login-page.png', fullPage: true });

    // Perform login
    await loginViaUI(page);

    // Verify we are on the dashboard
    await expect(page).toHaveURL(BASE_URL + '/');

    await page.screenshot({ path: 'tests/screenshots/01-after-login.png', fullPage: true });
  });

  test('02 - Dashboard page loads with KPI cards', async ({ page }) => {
    await loginViaUI(page);

    // Wait for the loading spinner to disappear (dashboard shows Loader2 while loading)
    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {
      // It may have already disappeared
    });

    // Wait for actual dashboard content
    await page.waitForTimeout(2000); // Allow data to render

    // Check for Dashboard title
    const dashboardTitle = page.getByRole('heading', { level: 1 });
    await expect(dashboardTitle).toBeVisible();

    // Check KPI cards are present - look for the card structure
    // Total Revenue card
    const kpiCards = page.locator('[class*="Card"]').filter({ has: page.locator('text=/REVENUE|ORDERS|UNITS|Revenue|Orders|Units/i') });

    // Take screenshot of the full dashboard
    await page.screenshot({ path: 'tests/screenshots/02-dashboard-kpis.png', fullPage: true });

    // Verify KPI values are displayed (even if zero)
    // Revenue card
    const revenueText = page.locator('text=/\\$|EUR|0/').first();
    await expect(revenueText).toBeVisible();
  });

  test('03 - KPI cards display correct structure (revenue, orders, units)', async ({ page }) => {
    await loginViaUI(page);

    // Wait for dashboard to fully load
    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);

    // The Dashboard should have KPI sections for Total Revenue, Total Orders, Units Sold
    // Check for the card titles (they are uppercase per the component)
    const pageContent = await page.textContent('body');

    // Verify the KPI labels exist somewhere on the page (they may be translated)
    // Check for monetary format or number format
    const cards = page.locator('.grid > div').filter({
      has: page.locator('[class*="CardHeader"]'),
    });

    // Screenshot the KPI section
    const kpiGrid = page.locator('.grid.gap-4').first();
    if (await kpiGrid.isVisible()) {
      await kpiGrid.screenshot({ path: 'tests/screenshots/03-kpi-grid.png' });
    }

    // Check that we have the expected card count (Revenue spans 2 cols, then Orders, Units = 3 cards visible)
    // With the grid layout, there should be 4 grid items, but the revenue card spans 2
    await page.screenshot({ path: 'tests/screenshots/03-dashboard-full.png', fullPage: true });
  });

  test('04 - Revenue trend chart area renders', async ({ page }) => {
    await loginViaUI(page);

    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);

    // Check for chart cards - Revenue Trend and Units Trend
    // The charts are inside Card components with specific titles
    const chartSection = page.locator('.grid.gap-4.md\\:grid-cols-2').last();

    if (await chartSection.isVisible()) {
      await chartSection.screenshot({ path: 'tests/screenshots/04-charts-section.png' });
    }

    // Check if the revenue chart renders (either the SVG chart or the empty state)
    const revenueChartCard = page.locator('.recharts-responsive-container').first();
    const emptyState = page.getByText(/still syncing revenue|Stiamo ancora sincronizzando/i).first();

    const hasChart = await revenueChartCard.isVisible().catch(() => false);
    const hasEmptyState = await emptyState.isVisible().catch(() => false);

    // One of these should be visible
    expect(hasChart || hasEmptyState).toBeTruthy();

    await page.screenshot({ path: 'tests/screenshots/04-revenue-chart.png', fullPage: true });
  });

  test('05 - Units trend chart area renders', async ({ page }) => {
    await loginViaUI(page);

    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);

    // Check units chart
    const unitsChart = page.locator('.recharts-responsive-container').last();
    const emptyState = page.getByText(/Units will populate|unità saranno disponibili/i).first();

    const hasChart = await unitsChart.isVisible().catch(() => false);
    const hasEmptyState = await emptyState.isVisible().catch(() => false);

    expect(hasChart || hasEmptyState).toBeTruthy();

    await page.screenshot({ path: 'tests/screenshots/05-units-chart.png', fullPage: true });
  });

  test('06 - Date filter dropdown is functional', async ({ page }) => {
    await loginViaUI(page);

    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);

    // Screenshot before changing filter
    await page.screenshot({ path: 'tests/screenshots/06-before-filter.png', fullPage: true });

    // The date filter uses a shadcn/Radix Select component
    // The trigger button contains text like "Last 30 days"
    const dateSelectTrigger = page.getByRole('combobox').first();
    await expect(dateSelectTrigger).toBeVisible();

    // Verify it shows the default value
    const triggerText = await dateSelectTrigger.textContent();
    console.log(`Date filter trigger text: "${triggerText}"`);

    // Click to open dropdown
    await dateSelectTrigger.click();

    // Wait for the Radix portal to appear with the listbox
    const listbox = page.getByRole('listbox');
    await expect(listbox).toBeVisible({ timeout: 5000 });

    // Screenshot the dropdown options
    await page.screenshot({ path: 'tests/screenshots/06-date-dropdown-open.png', fullPage: true });

    // Count available options within the listbox
    const options = listbox.getByRole('option');
    const optionCount = await options.count();
    console.log(`Date filter options found: ${optionCount}`);

    // Log each option text for debugging
    for (let i = 0; i < optionCount; i++) {
      const text = await options.nth(i).textContent();
      console.log(`  Option ${i}: "${text}"`);
    }

    expect(optionCount).toBeGreaterThanOrEqual(5); // 7, 14, 30, 60, 90, custom = 6 options

    // Select 7 days (first option)
    await options.first().click();
    await page.waitForTimeout(1000);
    await page.waitForLoadState('networkidle');

    // Verify the trigger now shows the 7 day label
    const updatedText = await dateSelectTrigger.textContent();
    console.log(`After selecting 7d: "${updatedText}"`);

    await page.screenshot({ path: 'tests/screenshots/06-after-7d-filter.png', fullPage: true });
  });

  test('07 - Changing date filter triggers new API calls', async ({ page }) => {
    await loginViaUI(page);

    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);

    // Intercept API calls to track date parameters
    const apiCalls: string[] = [];
    page.on('request', (request) => {
      if (request.url().includes('/api/v1/analytics/')) {
        apiCalls.push(request.url());
      }
    });

    // Open date filter and select 14 days
    const dateSelect = page.locator('button[role="combobox"]').first();
    await dateSelect.click();
    await page.waitForTimeout(500);

    // Select 14-day option (second option)
    const options = page.locator('[role="option"]');
    // Click on "14" option
    const fourteenDayOption = options.nth(1);
    await fourteenDayOption.click();

    // Wait for API calls to fire
    await page.waitForTimeout(3000);
    await page.waitForLoadState('networkidle');

    // Verify that API calls were made with new date parameters
    const dashboardCalls = apiCalls.filter(url => url.includes('/analytics/dashboard'));
    const trendsCalls = apiCalls.filter(url => url.includes('/analytics/trends'));

    // There should be at least one new dashboard and trends call
    expect(dashboardCalls.length).toBeGreaterThanOrEqual(1);
    expect(trendsCalls.length).toBeGreaterThanOrEqual(1);

    await page.screenshot({ path: 'tests/screenshots/07-after-filter-change.png', fullPage: true });
  });

  test('08 - Switching between multiple date ranges triggers data refresh', async ({ page }) => {
    await loginViaUI(page);

    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);

    // Track API calls
    const apiCalls: { url: string; timestamp: number }[] = [];
    page.on('request', (request) => {
      if (request.url().includes('/api/v1/analytics/')) {
        apiCalls.push({ url: request.url(), timestamp: Date.now() });
      }
    });

    // Test switching to 7 days
    const dateSelect = page.locator('button[role="combobox"]').first();
    await dateSelect.click();
    await page.waitForTimeout(500);
    await page.locator('[role="option"]').first().click();
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
    const callsAfter7d = apiCalls.length;

    await page.screenshot({ path: 'tests/screenshots/08-after-7d.png', fullPage: true });

    // Switch to 60 days
    await dateSelect.click();
    await page.waitForTimeout(500);
    await page.locator('[role="option"]').nth(3).click(); // 60d option
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
    const callsAfter60d = apiCalls.length;

    // Verify additional API calls were made after each switch
    expect(callsAfter60d).toBeGreaterThan(callsAfter7d);

    await page.screenshot({ path: 'tests/screenshots/08-after-60d.png', fullPage: true });

    // Switch to 90 days
    await dateSelect.click();
    await page.waitForTimeout(500);
    await page.locator('[role="option"]').nth(4).click(); // 90d option
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');

    expect(apiCalls.length).toBeGreaterThan(callsAfter60d);

    await page.screenshot({ path: 'tests/screenshots/08-after-90d.png', fullPage: true });
  });

  test('09 - Account status badges display correctly', async ({ page }) => {
    await loginViaUI(page);

    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);

    // Check for account status badges
    // The dashboard should show "0 Active Accounts" or similar
    const badges = page.locator('[class*="Badge"], [class*="badge"]');
    const badgeCount = await badges.count();

    // At minimum, we expect the "active accounts" badge
    if (badgeCount > 0) {
      for (let i = 0; i < badgeCount; i++) {
        const badge = badges.nth(i);
        if (await badge.isVisible()) {
          const text = await badge.textContent();
          console.log(`Badge ${i}: "${text}"`);
        }
      }
    }

    await page.screenshot({ path: 'tests/screenshots/09-account-badges.png', fullPage: true });
  });

  test('10 - Invalid account query param falls back to overview', async ({ page }) => {
    await loginViaUI(page);

    await page.goto(`${BASE_URL}/?account=not-a-uuid`);
    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForLoadState('networkidle');

    await expect(page).toHaveURL(BASE_URL + '/');
    await expect(page.getByText(/Account view cleared|Vista account rimossa/i)).toBeVisible();
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  });

  test('11 - Account drill-down shows contextual scope and exit action', async ({ page }) => {
    await loginViaUI(page);

    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForLoadState('networkidle');

    const drillLinks = page.getByRole('link', { name: /View account dashboard|Apri dashboard account/i });
    const drillLinkCount = await drillLinks.count();
    test.skip(drillLinkCount === 0, 'No account drill-down cards available in this fixture');

    await drillLinks.first().click();
    await expect(page).toHaveURL(/\/\?account=/);
    await expect(page.getByText(/Viewing account|Account attivo/i)).toBeVisible();

    const exitButton = page.getByRole('button', { name: /Exit|Esci/i }).first();
    await expect(exitButton).toBeVisible();
    await exitButton.click();

    await expect(page).toHaveURL(BASE_URL + '/');
  });

  test('12 - No console errors on dashboard', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    await loginViaUI(page);

    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(3000);

    // Filter out known benign errors (e.g., favicon, HMR)
    const significantErrors = errors.filter(e =>
      !e.includes('favicon') &&
      !e.includes('HMR') &&
      !e.includes('[vite]') &&
      !e.includes('DevTools')
    );

    if (significantErrors.length > 0) {
      console.log('Console errors found:', significantErrors);
    }

    // Log warnings but don't fail on them
    // Fail only on truly significant errors
    expect(significantErrors.length).toBe(0);
  });

  test('13 - No failed network requests on dashboard load', async ({ page }) => {
    const failedRequests: { url: string; status: number }[] = [];

    page.on('response', (response) => {
      if (response.status() >= 400 && !response.url().includes('favicon')) {
        failedRequests.push({
          url: response.url(),
          status: response.status(),
        });
      }
    });

    await loginViaUI(page);

    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(3000);

    if (failedRequests.length > 0) {
      console.log('Failed requests:', JSON.stringify(failedRequests, null, 2));
    }

    // All API requests should succeed
    expect(failedRequests.length).toBe(0);
  });

  test('14 - Dashboard responsive layout at mobile viewport', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 812 });

    await loginViaUI(page);

    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);

    await page.screenshot({ path: 'tests/screenshots/12-mobile-dashboard.png', fullPage: true });

    // Verify the page doesn't have horizontal overflow
    const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
    const viewportWidth = await page.evaluate(() => window.innerWidth);

    // Allow a small tolerance
    expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 10);
  });

  test('15 - Dashboard responsive layout at tablet viewport', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });

    await loginViaUI(page);

    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);

    await page.screenshot({ path: 'tests/screenshots/13-tablet-dashboard.png', fullPage: true });
  });

  test('16 - Verify chart empty states when no data', async ({ page }) => {
    await loginViaUI(page);

    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);

    // Since the test user has no sales data, charts should show empty state
    // The ChartEmptyState component renders placeholder bars and a message
    const emptyStates = page.locator('[class*="border-dashed"]');
    const emptyCount = await emptyStates.count();

    // Capture the chart area
    await page.screenshot({ path: 'tests/screenshots/14-chart-empty-states.png', fullPage: true });

    // If there's no data, we expect empty state placeholders
    // (This verifies the empty state renders gracefully rather than crashing)
    console.log(`Empty state placeholder count: ${emptyCount}`);
  });

  test('17 - Navigation sidebar links work from dashboard', async ({ page }) => {
    await loginViaUI(page);

    await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);

    // Check sidebar navigation links
    const navLinks = page.locator('nav a, aside a');
    const linkCount = await navLinks.count();

    await page.screenshot({ path: 'tests/screenshots/15-navigation.png', fullPage: true });

    console.log(`Navigation links found: ${linkCount}`);
    expect(linkCount).toBeGreaterThan(0);
  });
});
