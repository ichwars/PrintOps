import { expect, test } from '@playwright/test';

const projects = [
  { id: 1, name: 'Airframe', parent_id: null, child_count: 2, completed_count: 12, status: 'active' },
  { id: 2, name: 'Wing', parent_id: 1, child_count: 1, completed_count: 0, status: 'active' },
  { id: 3, name: 'Spar', parent_id: 2, child_count: 0, completed_count: 0, status: 'active' },
  { id: 4, name: 'Tail', parent_id: 1, child_count: 0, completed_count: 0, status: 'completed' },
].map(project => ({
  description: null, color: '#00ae42', archive_count: 0, failed_count: 0, queue_count: 0,
  archives: [], created_at: '2026-10-01T00:00:00Z', ...project,
}));

for (const touch of [false, true]) {
  test.describe(`project groups ${touch ? 'touch' : 'keyboard'}`, () => {
    test.use({ viewport: { width: touch ? 390 : 1440, height: 900 }, hasTouch: touch });
    test('groups collapse, restore and respect filters and the saved default', async ({ page }, testInfo) => {
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
      await page.addInitScript(() => localStorage.setItem('bambutrack_language', 'en'));
      await page.routeWebSocket('**/*', () => {});
      await page.route('**/sw-register.js', route => route.fulfill({ contentType: 'application/javascript', body: '' }));
      await page.route('**/api/v1/**', route => {
        const url = new URL(route.request().url());
        const path = url.pathname.replace(/\/+$/, '');
        let data: unknown = [];
        if (path === '/api/v1/auth/status') data = { auth_enabled: false, requires_setup: false };
        else if (path === '/api/v1/settings') data = { currency: 'EUR' };
        else if (path === '/api/v1/inventory/colors/map') data = { colors: {} };
        else if (path === '/api/v1/projects') {
          const status = url.searchParams.get('status');
          data = status ? projects.filter(project => project.status === status) : projects;
        }
        else if (path === '/api/v1/auth/encryption-status') data = {
          key_configured: true, key_source: 'generated', decryption_broken: false, migration_error_count: 0,
          legacy_plaintext_rows: {}, encrypted_rows: {},
        };
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
      });
      await page.goto('/projects');
      await expect(page).toHaveURL(/\/projects$/);
      await expect(page).toHaveTitle(/PrintOps/);
      await expect(page.getByRole('heading', { name: 'Projects', exact: true })).toBeVisible();
      const root = page.getByRole('button', { name: /sub-projects of Airframe$/ });
      await expect(root).toHaveAttribute('aria-expanded', 'true');
      await expect.poll(() => root.evaluate(element => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
      await expect(page.getByText('1 matching / 2 total')).toBeVisible();
      if (touch) await root.tap();
      else await root.press('Space');
      await expect(root).toHaveAttribute('aria-expanded', 'false');
      await expect(page.getByRole('heading', { name: 'Wing', exact: true })).toHaveCount(0);
      await expect(page.getByText('12 parts').first()).toBeVisible();
      if (touch) await root.tap();
      else await root.press('Enter');
      await expect(page.getByRole('heading', { name: 'Spar', exact: true })).toBeVisible();
      const defaultControl = page.getByRole('checkbox', { name: 'Collapse sub-projects by default' });
      await page.getByText('Collapse sub-projects by default', { exact: true }).click();
      await expect(root).toHaveAttribute('aria-expanded', 'false');
      await page.reload();
      await expect(defaultControl).toBeChecked();
      await expect(root).toHaveAttribute('aria-expanded', 'false');
      await page.screenshot({ path: testInfo.outputPath('project-groups-collapsed.png'), fullPage: true });
      await page.getByRole('button', { name: 'Completed', exact: true }).click();
      // The matching child remains accessible when its parent is filtered out.
      await expect(page.getByRole('heading', { name: 'Tail', exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Active', exact: true }).click();
      await expect(root).toHaveAttribute('aria-expanded', 'false');
      await root.click();
      // The nested group inherits the global default until explicitly opened.
      await page.getByRole('button', { name: 'Expand sub-projects of Wing' }).click();
      await expect(page.getByRole('heading', { name: 'Spar', exact: true })).toBeVisible();
      expect(await page.locator('vite-error-overlay').count()).toBe(0);
      expect(errors).toEqual([]);
      await page.screenshot({ path: testInfo.outputPath('project-groups.png'), fullPage: true });
    });
  });
}
