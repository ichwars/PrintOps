import { expect, test } from '@playwright/test';

const gcode = 'G90\nM82\nG1 X10 Y10 Z0.2 F1200\nG1 X50 Y10 E1\nG1 X50 Y50 E2\nG1 X10 Y50 E3\nG1 X10 Y10 E4\nG1 Z0.4\nG1 X50 Y10 E5\n';

test.use({ deviceScaleFactor: 2 });

test.beforeEach(async ({ page }) => {
  await page.route('**/js/three.min.js', async route => {
    const response = await route.fetch();
    const instrumentation = `
      window.previewSizes = 0; window.previewRenders = 0;
      const OriginalRenderer = THREE.WebGLRenderer;
      THREE.WebGLRenderer = function(options) {
        const instance = new OriginalRenderer(options);
        const originalSize = instance.setSize;
        const originalRender = instance.render;
        instance.setSize = function(...args) { window.previewSizes++; return originalSize.apply(this, args); };
        instance.render = function(...args) { window.previewRenders++; return originalRender.apply(this, args); };
        return instance;
      };
      THREE.WebGLRenderer.prototype = OriginalRenderer.prototype;
    `;
    await route.fulfill({ response, body: (await response.text()) + instrumentation });
  });
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/gcode')) {
      return route.fulfill({ contentType: 'text/plain', body: gcode });
    }
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ filename: 'Two plates', build_volume: { x: 256, y: 256, z: 256 } }) });
  });
});

for (const width of [390, 1440]) {
  test(`requested plate and stable high DPI canvas at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const request = page.waitForRequest(url => new URL(url.url()).pathname.endsWith('/gcode'));
    await page.goto('/gcode-viewer/?library_file=1&plate=2');
    expect(new URL((await request).url()).searchParams.get('plate')).toBe('2');
    await expect.poll(() => page.evaluate(() => (window as unknown as { previewRenders: number }).previewRenders)).toBeGreaterThan(1);
    await page.waitForTimeout(500);
    const first = await page.evaluate(() => ({ count: (window as unknown as { previewSizes: number }).previewSizes, height: document.documentElement.scrollHeight }));
    await page.waitForTimeout(1500);
    const second = await page.evaluate(() => ({ count: (window as unknown as { previewSizes: number }).previewSizes, height: document.documentElement.scrollHeight }));
    expect(second.count - first.count).toBeLessThanOrEqual(1);
    expect(second.height).toBe(first.height);
    expect(second.height).toBeLessThanOrEqual(900);
    await page.screenshot({ path: testInfo.outputPath('gcode-preview.png') });
    await page.setViewportSize({ width: width === 390 ? 600 : 1000, height: 700 });
    await expect.poll(() => page.locator('#mycanvas').evaluate(canvas => (canvas as HTMLCanvasElement).width)).toBe((width === 390 ? 600 : 1000) * 2);
    expect(errors).toEqual([]);
  });
}

test('invalid explicit plate is visible and does not fetch default G-code', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', request => { if (new URL(request.url()).pathname.endsWith('/gcode')) requests.push(request.url()); });
  await page.goto('/gcode-viewer/?library_file=1&plate=2x');
  await expect(page.getByRole('alert')).toContainText('Invalid plate');
  await page.waitForTimeout(500);
  expect(requests).toEqual([]);
});

test('missing explicit plate displays the HTTP failure without fetching another plate', async ({ page }) => {
  const requests: string[] = [];
  await page.route('**/api/v1/library/files/1/gcode?plate=3', route => {
    requests.push(route.request().url());
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Plate 3 not found"}' });
  });
  await page.goto('/gcode-viewer/?library_file=1&plate=3');
  await expect(page.getByRole('alert')).toContainText('HTTP 404');
  await expect(page.locator('#bb-play-btn')).toBeDisabled();
  expect(requests).toHaveLength(1);
});
