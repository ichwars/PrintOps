import { expect, test } from '@playwright/test';

const spools = Array.from({ length: 100 }, (_, index) => ({
  id: index + 1, material: 'PLA', subtype: null, brand: 'PrintOps',
  color_name: index === 0 ? 'Transparent' : `Spool ${index + 1}`,
  rgba: index === 0 ? '00000000' : 'FF0000FF', extra_colors: null, effect_type: null,
  label_weight: 1000, core_weight: 200, weight_used: 0, weight_used_baseline: 0,
  archived_at: null, location_id: null, storage_location: null, category: null,
  created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
}));

for (const width of [1440, 390]) {
  test.describe(`label sheet at ${width}px`, () => {
    test.use({ viewport: { width, height: width === 390 ? 740 : 900 } });
    test('a long selection keeps the start position and print controls reachable', async ({ page }, testInfo) => {
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
      await page.addInitScript(() => localStorage.setItem('bambutrack_language', 'en'));
      await page.routeWebSocket('**/*', () => {});
      await page.route('**/sw-register.js', route => route.fulfill({ contentType: 'application/javascript', body: '' }));
      await page.route('**/api/v1/**', route => {
        const path = new URL(route.request().url()).pathname.replace(/\/+$/, '');
        let data: unknown = [];
        if (path === '/api/v1/auth/status') data = { auth_enabled: false, requires_setup: false };
        else if (path === '/api/v1/settings') data = { currency: 'EUR' };
        else if (path === '/api/v1/settings/spoolman') data = { spoolman_enabled: 'false' };
        else if (path === '/api/v1/inventory/colors/map') data = { colors: {} };
        else if (path === '/api/v1/inventory/spools') data = spools;
        else if (path === '/api/v1/auth/encryption-status') data = {
          key_configured: true, key_source: 'generated', decryption_broken: false, migration_error_count: 0,
          legacy_plaintext_rows: {}, encrypted_rows: {},
        };
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
      });
      await page.goto('/inventory');
      await expect(page).toHaveURL(/\/inventory$/);
      await expect(page).toHaveTitle(/PrintOps/);
      await page.getByRole('button', { name: 'Print labels…', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'Print spool labels' })).toBeVisible();
      await expect(page.getByText('100 selected', { exact: false })).toBeVisible();
      const first = page.getByRole('spinbutton', { name: /Start position.*L7160/ });
      const print = page.getByRole('button', { name: /Avery L7160/ });
      await first.fill('22');
      await expect(first).toHaveAttribute('aria-invalid', 'true');
      await expect(print).toBeDisabled();
      await first.fill('21');
      await expect(print).toBeEnabled();
      await first.focus();
      await first.press('ArrowDown');
      await expect(first).toHaveValue('20');
      await first.press('ArrowUp');
      await expect(first).toHaveValue('21');
      await print.scrollIntoViewIfNeeded();
      const modal = page.getByRole('heading', { name: 'Print spool labels' }).locator('../..');
      const bounds = await modal.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
      expect(await modal.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
      await expect(page.locator('vite-error-overlay')).toHaveCount(0);
      await page.screenshot({ path: testInfo.outputPath('label-sheet-start.png') });
      // A known API failure keeps the user's sheet position and selection available for retry.
      await page.route('**/api/v1/inventory/labels', route => route.fulfill({
        status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'PDF unavailable' }),
      }));
      const request = page.waitForRequest('**/api/v1/inventory/labels');
      await print.click();
      const body = (await request).postDataJSON();
      expect(body.start_position).toBe(21);
      expect(body.spool_ids).toHaveLength(100);
      await expect(page.getByText(/Could not generate labels/)).toBeVisible();
      await expect(first).toHaveValue('21');
      await page.getByRole('button', { name: 'Cancel', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'Print spool labels' })).toHaveCount(0);
      expect(errors.filter(error => !error.includes('503'))).toEqual([]);
    });
  });
}
