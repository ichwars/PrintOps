import { expect, test, type Locator, type Page } from '@playwright/test';

async function installLibrary(page: Page) {
  await page.addInitScript(() => localStorage.setItem('bambutrack_language', 'en'));
  await page.route('**/sw-register.js', route => route.fulfill({ contentType: 'application/javascript', body: '' }));
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname.replace(/\/+$/, '');
    let data: unknown = [];
    if (path === '/api/v1/auth/status') data = { auth_enabled: false, requires_setup: false };
    else if (path === '/api/v1/auth/encryption-status') data = {
      key_configured: true, key_source: 'generated', decryption_broken: false, migration_error_count: 0,
      legacy_plaintext_rows: { oidc_providers: 0, user_totp: 0 }, encrypted_rows: { oidc_providers: 0, user_totp: 0 },
    };
    else if (path === '/api/v1/settings') data = { use_slicer_api: true, library_disk_warning_gb: 5 };
    else if (path === '/api/v1/library/folders') data = [{ id: 42, name: 'Touch models', children: [], file_count: 1, parent_id: null }];
    else if (path === '/api/v1/library/files') data = [{
      id: 7, filename: 'gear.stl', file_type: 'stl', file_size: 1024, folder_id: 42,
      created_at: '2026-09-08T00:00:00Z', print_count: 0, tags: [],
    }];
    else if (path === '/api/v1/library/folders/42/readme') data = { filename: 'README.md', content: 'Touch fixture', truncated: false };
    else if (path === '/api/v1/library/trash') data = { items: [], total: 0 };
    else if (path === '/api/v1/library/stats') data = { total_files: 1, total_folders: 1, total_size_bytes: 1024, disk_free_bytes: 10e9, disk_total_bytes: 100e9 };
    else if (path === '/api/v1/projects') data = [{ id: 11, name: 'Touch project', color: '#00ae42', archive_count: 0, completed_count: 0, failed_count: 0, queue_count: 0 }];
    else if (path === '/api/v1/archives') data = [{
      id: 21, filename: 'gear.gcode.3mf', print_name: 'Touch archive', file_path: '/fixture.3mf',
      thumbnail_path: '/fixture.png', status: 'completed', tags: 'test', print_count: 1,
      created_at: '2026-09-08T00:00:00Z', print_time_seconds: 120, filament_used_grams: 2,
    }];
    else if (path === '/api/v1/archives/stats') data = { total_archives: 1, total_print_time_seconds: 120, total_filament_grams: 2 };
    else if (path === '/api/v1/archives/tags') data = [{ name: 'test', count: 1 }];
    else if (path === '/api/v1/archives/21/plates') data = { archive_id: 21, is_multi_plate: true, plates: [{ index: 1, name: 'First plate' }, { index: 2, name: 'Second plate' }] };
    else if (path.includes('/thumbnail')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="gray"/></svg>' });
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
  });
}

for (const touch of [true, false]) {
  test.describe(`project/archive ${touch ? 'touch' : 'keyboard'}`, () => {
    test.use({ viewport: { width: touch ? 1024 : 1440, height: 1000 }, hasTouch: touch });
    test('project menu, archive plates and tag actions do not require hover', async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      await installLibrary(page);
      await page.goto('/projects');
      const projectTrigger = page.getByRole('button', { name: 'Actions: Touch project' });
      if (touch) {
        await expect.poll(() => opacity(projectTrigger)).toBe(1);
        await projectTrigger.tap();
      } else await projectTrigger.press('Enter');
      const projectMenu = page.getByRole('menu', { name: 'Actions: Touch project' });
      await expect(projectMenu.getByRole('menuitem', { name: 'Edit' })).toBeFocused();
      await hitTarget(projectMenu.getByRole('menuitem', { name: 'Delete' }));
      await page.keyboard.press('Escape');
      await expect(projectTrigger).toBeFocused();

      await page.goto('/archives');
      const card = page.locator('[data-archive-id="21"]');
      const options = card.getByRole('button', { name: 'More options' });
      if (touch) {
        await expect.poll(() => opacity(options)).toBe(1);
        await card.getByRole('img', { name: 'Touch archive' }).tap();
      } else {
        await options.focus();
        await expect.poll(() => opacity(options)).toBe(1);
      }
      const nextPlate = card.getByRole('button', { name: 'Next plate' });
      await expect(nextPlate).toBeVisible();
      if (touch) {
        await expect.poll(() => opacity(nextPlate)).toBe(1);
        await nextPlate.tap();
      } else await nextPlate.press('Enter');
      await expect(card.getByRole('img', { name: 'Touch archive' })).toHaveAttribute('src', /plate.*2|2.*thumbnail/);
      await options.press('Enter');
      await expect(page.getByRole('button', { name: 'Print', exact: true }).last()).toBeFocused();
      await page.keyboard.press('Escape');
      await expect(options).toBeFocused();

      await page.getByRole('button', { name: 'Manage Tags', exact: true }).click();
      const rename = page.getByRole('button', { name: 'Rename tag' });
      if (touch) {
        await expect.poll(() => opacity(rename)).toBe(1);
        await rename.tap();
      } else {
        await rename.focus();
        await expect.poll(() => opacity(rename)).toBe(1);
        await rename.press('Enter');
      }
      await expect(page.locator('input:focus')).toHaveValue('test');
      expect(errors).toEqual([]);
    });
  });
}

async function opacity(control: Locator) {
  return control.evaluate(element => {
    let opacity = 1;
    for (let node: Element | null = element; node; node = node.parentElement) opacity *= Number(getComputedStyle(node).opacity);
    return opacity;
  });
}

async function hitTarget(control: Locator) {
  await expect.poll(() => control.evaluate(element => {
    const rect = element.getBoundingClientRect();
    return element.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
  })).toBe(true);
}

test.describe('short touch viewport', () => {
  test.use({ viewport: { width: 390, height: 200 }, hasTouch: true });
  test('a constrained menu scrolls internally without dismissing', async ({ page }) => {
    await installLibrary(page);
    await page.goto('/files?folder=42');
    await page.getByRole('button', { name: 'Actions: gear.stl', exact: true }).tap();
    const menu = page.getByRole('menu', { name: 'Actions: gear.stl' });
    const layer = menu.locator('..');
    // Reproduce a queued notification from scrolling the trigger into view.
    // No position changed since opening, so this must not dismiss the popup.
    await page.evaluate(() => document.dispatchEvent(new Event('scroll')));
    await expect(menu).toBeVisible();
    await expect.poll(() => layer.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);
    await page.keyboard.press('End');
    await hitTarget(menu.getByRole('menuitem', { name: 'Delete', exact: true }));
    await expect.poll(() => layer.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    await page.keyboard.press('Home');
    await hitTarget(menu.getByRole('menuitem', { name: 'Slice', exact: true }));
    await page.keyboard.press('Escape');
    await expect(menu).toHaveCount(0);
  });
});

for (const viewport of [{ width: 390, height: 320 }, { width: 390, height: 844 }, { width: 1024, height: 844 }, { width: 1440, height: 1000 }]) {
  const touch = viewport.width < 1440;
  test.describe(`${viewport.width}x${viewport.height} ${touch ? 'touch' : 'mouse'}`, () => {
    test.use({ viewport, hasTouch: touch });

    test('file/folder actions are reachable, unclipped and keyboard-operable', async ({ page }, testInfo) => {
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => {
        if (message.type() === 'error' && !/^(?:WebSocket connection.*failed|\[WebSocket\] Error)/i.test(message.text())) errors.push(message.text());
      });
      await installLibrary(page);
      await page.goto('/files?folder=42');
      await expect(page).toHaveTitle(/PrintOps/i);
      await expect(page.getByRole('heading', { name: 'gear.stl' })).toBeVisible();
      await expect(page.locator('vite-error-overlay')).toHaveCount(0);
      const trigger = page.getByRole('button', { name: 'Actions: gear.stl', exact: true });
      await trigger.scrollIntoViewIfNeeded();
      if (touch) {
        expect(await page.evaluate(() => matchMedia('(hover: none)').matches)).toBe(true);
        await expect.poll(() => opacity(trigger)).toBe(1);
        await trigger.tap();
      } else {
        await page.mouse.move(0, 0);
        await expect.poll(() => opacity(trigger)).toBe(0);
        await trigger.hover();
        await expect.poll(() => opacity(trigger)).toBe(1);
        await page.mouse.move(0, 0);
        // Reach the trigger using only Tab, not simulated hover or DOM focus.
        for (let i = 0; i < 100 && !(await trigger.evaluate(el => el === document.activeElement)); i++) await page.keyboard.press('Tab');
        await expect(trigger).toBeFocused();
        await expect.poll(() => opacity(trigger)).toBe(1);
        await page.keyboard.press('Enter');
      }
      const menu = page.getByRole('menu', { name: 'Actions: gear.stl' });
      const first = menu.getByRole('menuitem').first();
      await expect(first).toHaveText('Slice');
      await expect(first).toBeFocused();
      await hitTarget(first);
      await expect.poll(() => opacity(menu)).toBe(1);
      await expect.poll(() => opacity(trigger)).toBe(1);
      const layer = menu.locator('..');
      await expect.poll(async () => {
        const rect = await layer.boundingBox();
        return Boolean(rect && rect.y >= 7 && rect.y + rect.height <= viewport.height - 7);
      }).toBe(true);
      const box = await menu.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(7);
      expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width - 7);
      expect(box!.y).toBeGreaterThanOrEqual(7);
      await page.screenshot({ path: testInfo.outputPath('file-menu.png') });
      await page.keyboard.press('End');
      await expect(menu.getByRole('menuitem', { name: 'Delete', exact: true })).toBeFocused();
      await hitTarget(menu.getByRole('menuitem', { name: 'Delete', exact: true }));
      await expect(menu).toBeVisible();
      await page.keyboard.press('Home');
      await expect(first).toBeFocused();
      await page.keyboard.press('Escape');
      await expect(menu).toHaveCount(0);
      await expect(trigger).toBeFocused();
      await page.keyboard.press('Enter');
      await page.keyboard.press('Tab');
      await expect(menu).toHaveCount(0);
      expect(await page.evaluate(() => document.activeElement?.tagName)).not.toBe('BODY');
      await trigger.press('Enter');
      await menu.getByRole('menuitem', { name: 'Rename', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'Rename File' })).toBeVisible();
      await page.getByRole('button', { name: 'Cancel', exact: true }).click();

      const folderTrigger = page.getByRole('button', { name: 'Actions: Touch models', exact: true });
      await folderTrigger.scrollIntoViewIfNeeded();
      if (touch) {
        await expect.poll(() => opacity(folderTrigger)).toBe(1);
        await folderTrigger.tap();
      } else await folderTrigger.press('Enter');
      const folderMenu = page.getByRole('menu', { name: 'Actions: Touch models' });
      await hitTarget(folderMenu.getByRole('menuitem', { name: 'Rename' }));
      await page.keyboard.press('Escape');
      await expect(folderTrigger).toBeFocused();
      if (!touch) {
        // The action popup must not leave an overlay intercepting file drops.
        const transfer = await page.evaluateHandle(() => {
          const data = new DataTransfer();
          data.items.add(new File(['solid gear\nendsolid gear'], 'drop.stl', { type: 'application/sla' }));
          return data;
        });
        const card = page.getByRole('heading', { name: 'gear.stl' }).locator('../..');
        await card.dispatchEvent('dragenter', { dataTransfer: transfer });
        await card.dispatchEvent('dragover', { dataTransfer: transfer });
        await card.dispatchEvent('drop', { dataTransfer: transfer });
        await expect(page.getByRole('heading', { name: 'Upload Files' })).toBeVisible();
        await expect(page.getByText('drop.stl', { exact: true })).toBeVisible();
        await page.getByRole('button', { name: 'Cancel', exact: true }).click();
      }
      expect(errors).toEqual([]);
    });
  });
}
