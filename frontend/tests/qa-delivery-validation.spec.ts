import { test, expect, Page, ConsoleMessage, Request } from '@playwright/test';

const BASE_URL = 'http://localhost:5173';
const SHOTS = '/Users/giuseppepretto/Projects/keelai/amazon/test-results';
const EMAIL = 'peppepretto@gmail.com';
const PASSWORD = 'QaTest123!';

type Diag = { consoleErrors: string[]; pageErrors: string[]; failedRequests: string[] };

function attachDiagnostics(page: Page): Diag {
  const diag: Diag = { consoleErrors: [], pageErrors: [], failedRequests: [] };
  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() === 'error') diag.consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => diag.pageErrors.push(String(err?.message ?? err)));
  page.on('requestfailed', (req: Request) => {
    const errText = req.failure()?.errorText ?? '';
    // ERR_ABORTED = React Query cancelling in-flight requests on navigation/unmount. Benign.
    if (errText.includes('ERR_ABORTED')) return;
    diag.failedRequests.push(`${req.method()} ${req.url()} :: ${errText}`);
  });
  page.on('response', (res) => {
    const s = res.status();
    if (s >= 400 && res.url().includes('/api/')) {
      diag.failedRequests.push(`HTTP ${s} ${res.request().method()} ${res.url()}`);
    }
  });
  return diag;
}

function dumpDiag(label: string, diag: Diag) {
  console.log(`\n===== DIAG [${label}] =====`);
  console.log('consoleErrors:', JSON.stringify(diag.consoleErrors));
  console.log('pageErrors:', JSON.stringify(diag.pageErrors));
  console.log('failedRequests:', JSON.stringify(diag.failedRequests));
  console.log(`===== END DIAG [${label}] =====`);
}

// Safe screenshot: 'animations: allow' (the default) does NOT wait for CSS
// animations to finish — Recharts charts animate continuously and would
// otherwise block page.screenshot from ever settling. Never throws.
async function shot(page: Page, path: string, clip?: { x: number; y: number; width: number; height: number }) {
  try {
    await page.screenshot({ path, fullPage: false, animations: 'allow', timeout: 8000, ...(clip ? { clip } : {}) });
  } catch (e) {
    console.log(`SHOT FAILED ${path}: ${String((e as Error)?.message ?? e).slice(0, 120)}`);
  }
}

// CDP screenshot: Page.captureScreenshot grabs the current frame immediately and
// does NOT block on the compositor, so it survives chart-heavy (Recharts) pages
// that hang the standard page.screenshot()/teardown.
import { writeFileSync } from 'fs';
async function cdpShot(page: Page, path: string) {
  try {
    const client = await page.context().newCDPSession(page);
    const { data } = await client.send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(path, Buffer.from(data, 'base64'));
    await client.detach().catch(() => {});
  } catch (e) {
    console.log(`CDP SHOT FAILED ${path}: ${String((e as Error)?.message ?? e).slice(0, 120)}`);
  }
}

async function login(page: Page) {
  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState('networkidle');
  await page.fill('input#email', EMAIL);
  await page.fill('input#password', PASSWORD);
  await page.getByRole('button', { name: /accedi|sign in/i }).click();
  await page.waitForURL(`${BASE_URL}/`, { timeout: 20000 });
  await page.waitForLoadState('networkidle');
}

test.describe.configure({ mode: 'serial' });
// Disable the harness auto-screenshot on failure: on chart-heavy pages it can
// hang in teardown waiting for the page to settle. We capture our own via shot().
test.use({ screenshot: 'off' });

test('FLOW1+2 login + brand analysis nav', async ({ page }) => {
  test.setTimeout(90000);
  const diag = attachDiagnostics(page);

  await login(page);
  await expect(page.getByRole('heading', { name: /Dashboard/i }).first()).toBeVisible();
  await shot(page, `${SHOTS}/qa-login.png`);
  console.log('FLOW1 login URL:', page.url());

  const brandLink = page.locator('a:visible', { hasText: /Analisi Brand|Brand Analysis/i }).first();
  const brandVisible = await brandLink.isVisible().catch(() => false);
  console.log('FLOW2 brand nav visible:', brandVisible);
  expect(brandVisible).toBeTruthy();
  await expect(brandLink).toHaveAttribute('href', '/brand-analysis');
  await brandLink.click();
  await page.waitForURL(`${BASE_URL}/brand-analysis`, { timeout: 15000 });
  await page.waitForLoadState('networkidle');
  const h1 = page.getByRole('heading', { level: 1 }).first();
  const h1Text = await h1.textContent().catch(() => null);
  console.log('FLOW2 url:', page.url(), '| h1:', h1Text);
  await expect(h1).toBeVisible();
  const bodyText = (await page.locator('body').innerText().catch(() => '')) || '';
  console.log('FLOW2 mentions upload/fallback path:', /carica|upload|esterni|export|template/i.test(bodyText));
  console.log('FLOW2 shows raw error/crash:', /TypeError|undefined is not|Cannot read|Something went wrong|Errore imprevisto/i.test(bodyText));
  await shot(page, `${SHOTS}/qa-brand-analysis.png`);
  dumpDiag('FLOW1+2', diag);
});

test('FLOW3 catalog period-aware summary + import tab', async ({ page }) => {
  test.setTimeout(90000);
  const diag = attachDiagnostics(page);
  await login(page);
  await page.goto(`${BASE_URL}/catalog`);
  await page.waitForLoadState('networkidle');

  for (const accName of ['Dialcos', 'Bitron']) {
    const picker = page.getByRole('combobox').first();
    const btnPicker = page.locator('button').filter({ hasText: /Seleziona account|account/i }).first();
    let opened = false;
    if (await picker.isVisible().catch(() => false)) { await picker.click().catch(() => {}); opened = true; }
    else if (await btnPicker.isVisible().catch(() => false)) { await btnPicker.click().catch(() => {}); opened = true; }
    if (opened) {
      const opt = page.getByRole('option', { name: new RegExp(accName, 'i') }).first();
      if (await opt.isVisible().catch(() => false)) {
        await opt.click().catch(() => {});
        await page.waitForLoadState('networkidle');
        console.log('FLOW3 selected account:', accName);
        break;
      } else { await page.keyboard.press('Escape').catch(() => {}); }
    }
  }
  await page.waitForTimeout(1500);
  const catBody = (await page.locator('body').innerText().catch(() => '')) || '';
  const countSummaryMatch = catBody.match(/\d+\s+prodotti con vendite nel periodo su\s+\d+\s+sincronizzati/i);
  console.log('FLOW3 countSummary present:', !!countSummaryMatch, '|', countSummaryMatch?.[0]);
  console.log('FLOW3 "Senza vendite" badge present:', /Senza vendite/i.test(catBody));
  expect(!!countSummaryMatch).toBeTruthy();
  await shot(page, `${SHOTS}/qa-catalog-products.png`);

  const importaTab = page.getByRole('tab', { name: /^Importa$/i }).first();
  const importaTabAlt = page.locator('button, [role="tab"]').filter({ hasText: /^Importa$/i }).first();
  let importTabClicked = false;
  if (await importaTab.isVisible().catch(() => false)) { await importaTab.click().catch(() => {}); importTabClicked = true; }
  else if (await importaTabAlt.isVisible().catch(() => false)) { await importaTabAlt.click().catch(() => {}); importTabClicked = true; }
  console.log('FLOW3 Importa tab clicked:', importTabClicked);
  await page.waitForTimeout(800);
  const importBody = (await page.locator('body').innerText().catch(() => '')) || '';
  const tmplBtn = page.getByRole('button', { name: /Scarica template CSV/i }).first();
  const tmplLink = page.locator('a, button').filter({ hasText: /Scarica template CSV/i }).first();
  const tmplVisible = (await tmplBtn.isVisible().catch(() => false)) || (await tmplLink.isVisible().catch(() => false));
  console.log('FLOW3 import card title present:', /Importa prodotti/i.test(importBody));
  console.log('FLOW3 "Scarica template CSV" present:', tmplVisible);
  expect(tmplVisible).toBeTruthy();
  await shot(page, `${SHOTS}/qa-catalog-import.png`);
  dumpDiag('FLOW3', diag);
});

test('FLOW4 forecast ASIN input + reliability explainer + months cadence', async ({ page }) => {
  test.setTimeout(90000);
  const diag = attachDiagnostics(page);
  await login(page);
  await page.goto(`${BASE_URL}/forecasts`);
  // Capture the "Genera nuova previsione" card as soon as it paints, BEFORE the
  // Recharts chart below mounts and pegs the compositor (which blocks full-page
  // screenshots). Clip to the top region to guarantee a stable capture.
  await page.getByText(/Genera nuova previsione/i).first().waitFor({ state: 'visible', timeout: 15000 }).catch(() => {});
  await cdpShot(page, `${SHOTS}/qa-forecasts.png`);

  await page.waitForLoadState('networkidle').catch(() => {});
  // The default (latest) forecast loads from forecastsApi.list(); for this org
  // the latest is a Dialcos VENDOR monthly forecast. Wait for its cadence badge.
  const cadence = page.getByText(/Cadenza mensile \(vendor\)/i).first();
  const cadenceVisible = await cadence.waitFor({ state: 'visible', timeout: 30000 }).then(() => true).catch(() => false);
  console.log('FLOW4 "Cadenza mensile (vendor)" badge rendered:', cadenceVisible);

  // ASIN paste input present + accepts free text
  const asinInput = page.locator('input[placeholder*="B00"]').first();
  const asinVisible = await asinInput.isVisible().catch(() => false);
  console.log('FLOW4 ASIN paste input visible:', asinVisible);

  const fBody = (await page.locator('body').innerText().catch(() => '')) || '';
  console.log('FLOW4 ASIN paste hint present:', /Incolla un ASIN/i.test(fBody));
  console.log('FLOW4 Affidabilità label present:', /Affidabilità/i.test(fBody));
  console.log('FLOW4 reliability explainer text present:', /Come si calcola l'affidabilità|MAPE|Derivata dalla MAPE|errore medio/i.test(fBody));
  console.log('FLOW4 "mesi" appears (months cadence, NOT giorni):', /\d+\s+mesi\b/i.test(fBody) || /\bmesi\b/i.test(fBody));
  console.log('FLOW4 friendly low-reliability message present:', /bassa affidabilità|Storico limitato/i.test(fBody));

  // Capture the loaded forecast detail (cadence badge + reliability panel).
  // Take the screenshot via CDP (page.screenshot can hang on the animating
  // Recharts SVG; the CDP capture does not wait for the compositor to settle).
  if (cadenceVisible) {
    await cadence.scrollIntoViewIfNeeded().catch(() => {});
    await page.waitForTimeout(1000);
    await cdpShot(page, `${SHOTS}/qa-forecasts-detail.png`);
  }

  expect(asinVisible).toBeTruthy();
  expect(cadenceVisible).toBeTruthy();
  expect(/\bmesi\b/i.test(fBody)).toBeTruthy();
  dumpDiag('FLOW4', diag);
});

test('FLOW5 scheduled reports renders, no email-not-configured banner', async ({ page }) => {
  test.setTimeout(90000);
  const diag = attachDiagnostics(page);
  await login(page);
  await page.goto(`${BASE_URL}/reports`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  const rBody = (await page.locator('body').innerText().catch(() => '')) || '';
  const rH1 = await page.getByRole('heading').first().textContent().catch(() => null);
  console.log('FLOW5 reports heading:', rH1);
  console.log('FLOW5 email-not-configured banner present (should be FALSE):',
    /email non configurat|Invio email non configurato/i.test(rBody));

  const schedTab = page.locator('[role="tab"], button').filter({ hasText: /Programmat|Scheduled|Pianificat/i }).first();
  if (await schedTab.isVisible().catch(() => false)) {
    await schedTab.click().catch(() => {});
    await page.waitForTimeout(1000);
  }
  const rBody2 = (await page.locator('body').innerText().catch(() => '')) || '';
  console.log('FLOW5 (after sched tab) email-not-configured present (should be FALSE):',
    /email non configurat|Invio email non configurato/i.test(rBody2));
  console.log('FLOW5 raw error/crash shown:', /TypeError|Cannot read|Something went wrong|Errore imprevisto/i.test(rBody2));
  expect(/email non configurat|Invio email non configurato/i.test(rBody2)).toBeFalsy();
  await shot(page, `${SHOTS}/qa-reports.png`);
  dumpDiag('FLOW5', diag);
  await page.goto('about:blank').catch(() => {});
});

test('FLOW6 recommendations renders + graceful AI degradation', async ({ page }) => {
  test.setTimeout(90000);
  const diag = attachDiagnostics(page);
  await login(page);
  await page.goto(`${BASE_URL}/recommendations`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1500);
  const recBody = (await page.locator('body').innerText().catch(() => '')) || '';
  const recH1 = await page.getByRole('heading').first().textContent().catch(() => null);
  console.log('FLOW6 recommendations heading:', recH1);
  console.log('FLOW6 page rendered (title present):', /Raccomandazioni/i.test(recBody));
  expect(/Raccomandazioni/i.test(recBody)).toBeTruthy();
  await shot(page, `${SHOTS}/qa-recommendations.png`);

  const genBtn = page.getByRole('button', { name: /Genera adesso|Genera/i }).first();
  if (await genBtn.isVisible().catch(() => false)) {
    await genBtn.click().catch(() => {});
    await page.waitForTimeout(800);
    const menuItem = page.getByRole('menuitem').first();
    if (await menuItem.isVisible().catch(() => false)) await menuItem.click().catch(() => {});
    // wait for generation to resolve (success / empty / unavailable)
    await page.waitForTimeout(12000);
    const recBody2 = (await page.locator('body').innerText().catch(() => '')) || '';
    console.log('FLOW6 after generate — aiUnavailable present:', /Suggerimenti AI non disponibili/i.test(recBody2));
    console.log('FLOW6 after generate — empty-state present:', /Nessuna raccomandazione/i.test(recBody2));
    console.log('FLOW6 after generate — white screen (empty body):', recBody2.trim().length < 40);
    console.log('FLOW6 after generate — raw 500/stack shown:', /500|Internal Server Error|Traceback|TypeError|Cannot read/i.test(recBody2));
    await shot(page, `${SHOTS}/qa-recommendations-generate.png`);
  } else {
    console.log('FLOW6 generate button not visible');
  }
  dumpDiag('FLOW6', diag);
  await page.goto('about:blank').catch(() => {});
});
