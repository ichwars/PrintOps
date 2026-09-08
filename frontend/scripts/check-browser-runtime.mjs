import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';

// Use a production preview, never the dev server. An isolated historical
// playwright-core package can be selected without changing application deps.
const require = createRequire(import.meta.url);
const playwright = require(process.env.BASELINE_PLAYWRIGHT || 'playwright');
const engine = process.env.BASELINE_ENGINE || 'chromium';
const url = process.env.BASELINE_URL || 'http://127.0.0.1:4184';
const browser = await playwright[engine].launch({ headless: true });
const markdown = [
  '# Safari baseline README', '', '| Part | Qty |', '| --- | ---: |', '| Gear | 2 |', '',
  '- [x] Printed', '- [ ] Packed', '', '~~Old revision~~', '',
  'Material note[^1]', '', '[^1]: Use PETG.', '',
  '[Docs](https://example.com/docs)', '', '<https://example.com>', '',
  'https://example.com/bare print@example.com', '',
  '[Blocked](javascript:alert%281%29)', '', '<script>window.readmeExecuted = true</script>',
].join('\n');

try {
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport, serviceWorkers: 'block' });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('response', (response) => {
      if (response.status() >= 400) errors.push(`HTTP ${response.status()} ${response.url()}`);
    });
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text());
    });
    await page.addInitScript(() => {
      localStorage.setItem('i18nextLng', 'en');
      localStorage.setItem('printops-language', 'en');
    });
    // Offline caching is outside this HTTP-fixture test. Blocking registration
    // avoids the old Playwright shim returning undefined instead of a Promise.
    await page.route('**/sw-register.js', (route) => route.fulfill({ contentType: 'application/javascript', body: '' }));
    await page.route('**/api/v1/**', (route) => {
      const pathname = new URL(route.request().url()).pathname;
      let body = [];
      if (pathname === '/api/v1/auth/status') body = { auth_enabled: false, requires_setup: false };
      else if (pathname === '/api/v1/library/folders') body = [{
        id: 42, name: 'Baseline models', parent_id: null, children: [], file_count: 0,
        total_size: 0, created_at: '2026-09-08T00:00:00Z',
      }];
      else if (pathname === '/api/v1/library/folders/42/readme') body = { filename: 'README.md', content: markdown, truncated: false };
      else if (pathname === '/api/v1/library/trash') body = { items: [], total: 0 };
      else if (pathname === '/api/v1/library/stats') body = { total_files: 0, total_folders: 1, total_size: 0, files_by_type: {} };
      else if (pathname === '/api/v1/settings') body = { language: 'en' };
      else if (pathname === '/api/v1/auth/encryption-status') body = {
        key_configured: true, key_source: 'generated', decryption_broken: false, migration_error_count: 0,
        legacy_plaintext_rows: { oidc_providers: 0, user_totp: 0 },
        encrypted_rows: { oidc_providers: 0, user_totp: 0 },
      };
      else if (pathname === '/api/v1/version') body = { version: 'baseline-test' };
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.goto(`${url}/files?folder=42`);
    const heading = page.getByRole('heading', { name: 'Safari baseline README' });
    try {
      await heading.waitFor();
    } catch (error) {
      console.error(JSON.stringify({ url: page.url(), errors, text: await page.locator('body').innerText() }));
      throw error;
    }
    assert.match(await page.title(), /PrintOps/i);
    assert.match(page.url(), /\/files\?folder=42$/);
    assert.equal(await page.locator('vite-error-overlay').count(), 0);
    const panel = page.getByRole('button', { name: 'README.md', exact: true }).locator('..');
    assert.match(await panel.getByRole('table').innerText(), /Gear/);
    assert.equal(await panel.getByRole('checkbox').first().isChecked(), true);
    assert.equal(await panel.getByRole('checkbox').first().isDisabled(), true);
    assert.equal(await panel.locator('del').innerText(), 'Old revision');
    assert.match(await panel.locator('[data-footnotes]').innerText(), /Use PETG/);
    assert.equal(await panel.getByRole('link', { name: 'Docs', exact: true }).getAttribute('rel'), 'noopener noreferrer');
    assert.equal(await panel.getByRole('link', { name: 'Blocked', exact: true }).getAttribute('href'), '');
    assert.equal(await panel.locator('a[href="https://example.com/bare"]').count(), 0);
    assert.equal(await page.evaluate(() => Boolean(window.readmeExecuted)), false);
    const toggle = page.getByRole('button', { name: 'README.md', exact: true });
    await toggle.click();
    assert.equal(await heading.count(), 0);
    await toggle.click();
    await heading.waitFor();
    // WebSocket has no backend in this deterministic API fixture; its transport
    // failure is unrelated to parsing/rendering and must not hide other errors.
    const relevantErrors = errors.filter((error) => !/^(?:WebSocket connection.*failed|\[WebSocket\] Error)/i.test(error));
    assert.deepEqual(relevantErrors, []);
    if (process.env.BASELINE_SCREENSHOTS) {
      await page.screenshot({ path: path.join(process.env.BASELINE_SCREENSHOTS, `${engine}-${viewport.width}.png`) });
    }
    console.log(JSON.stringify({ engine, version: browser.version(), viewport, flow: 'files -> README -> collapse -> expand', errors: relevantErrors, passed: true }));
    await page.close();
  }
} finally {
  await browser.close();
}
