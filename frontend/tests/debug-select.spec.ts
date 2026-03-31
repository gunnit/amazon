import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:5173';

test('debug select dropdown', async ({ page }) => {
  // Login first
  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState('networkidle');
  await page.fill('input#email', 'test@test.com');
  await page.fill('input#password', 'Test1234');
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL(BASE_URL + '/', { timeout: 10000 });
  await page.waitForLoadState('networkidle');

  // Wait for dashboard to load
  await page.waitForSelector('[class*="animate-spin"]', { state: 'detached', timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(2000);

  // Click the combobox to open
  const trigger = page.getByRole('combobox').first();
  await trigger.click();
  await page.waitForTimeout(1000);

  // Get the full HTML of all portals and the body
  const html = await page.evaluate(() => {
    // Check for Radix portals
    const portals = document.querySelectorAll('[data-radix-portal]');
    let portalHTML = '';
    portals.forEach((p, i) => {
      portalHTML += `\n--- Portal ${i} ---\n${p.innerHTML}\n`;
    });

    // Check for listbox
    const listbox = document.querySelector('[role="listbox"]');
    const listboxHTML = listbox ? listbox.outerHTML : 'NO LISTBOX FOUND';

    // Check what roles exist inside the select content
    const selectContent = document.querySelector('[data-radix-select-content]');
    const selectContentHTML = selectContent ? selectContent.outerHTML.substring(0, 2000) : 'NO SELECT CONTENT';

    return {
      portalHTML,
      listboxHTML: listboxHTML.substring(0, 2000),
      selectContentHTML,
    };
  });

  console.log('Portal HTML:', html.portalHTML.substring(0, 3000));
  console.log('Listbox HTML:', html.listboxHTML);
  console.log('Select Content HTML:', html.selectContentHTML);

  await page.screenshot({ path: 'tests/screenshots/debug-select.png', fullPage: true });
});
