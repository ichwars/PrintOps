import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from '@playwright/test';

// Production preview, software-only API/camera fixtures: never contacts a printer.
const origin = process.env.OVERLAY_URL || 'http://127.0.0.1:4196';
const screenshots = process.env.OVERLAY_SCREENSHOTS || '/tmp/printops-o06-screenshots';
await mkdir(screenshots, { recursive: true });
const browser = await chromium.launch({ headless: true });
const status = { id: 7, name: 'Studio printer', model: 'H2D', camera_rotation: 0, connected: true,
  state: 'RUNNING', current_print: 'Workshop organizer.gcode.3mf', gcode_file: 'plate_1.gcode',
  progress: 45, remaining_time: 82, layer_num: 150, total_layers: 300, stg_cur_name: null,
  time_format: '24h', supports_chamber_sensor: true,
  temperatures: { bed: 60, nozzle: 180, nozzle_target: 220, nozzle_2: 215, chamber: 35 } };
const camera = `<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"><defs><linearGradient id="room" x2="0" y2="1"><stop stop-color="#192723"/><stop offset="1" stop-color="#070c0a"/></linearGradient></defs><path fill="url(#room)" d="M0 0h1280v720H0z"/><path stroke="#52615a" stroke-width="12" fill="none" d="M230 660V75h820v585M230 150h820M320 150v465m640-465v465"/><path fill="#323f37" stroke="#637c6c" stroke-width="4" d="m250 580 710 0 100 95H140z"/><path fill="#249652" stroke="#71d890" stroke-width="3" d="M480 550v-150h310v150zm0-105h310m-230-45v150m145-150v150"/><path fill="#a7b6af" d="M595 155h90v95h-90z"/><text x="640" y="56" text-anchor="middle" fill="#91aa9b" font-family="sans-serif" font-size="20">PrintOps software camera fixture</text></svg>`;
async function fixture(page, authEnabled, readings = status.temperatures) {
  const requests = [], errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.addInitScript(() => { localStorage.clear(); sessionStorage.clear(); localStorage.setItem('i18nextLng', 'en'); localStorage.setItem('printops-language', 'en'); });
  await page.route('**/sw-register.js', route => route.fulfill({ contentType: 'application/javascript', body: '' }));
  await page.routeWebSocket('**/api/v1/ws*', ws => ws.close());
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url()), pathname = url.pathname;
    requests.push({ path: pathname, token: url.searchParams.get('token') });
    if (pathname.endsWith('/camera/stream')) return route.fulfill({ contentType: 'image/svg+xml', body: camera });
    let body = [];
    if (pathname.endsWith('/overlay-status')) body = { ...status, temperatures: readings };
    else if (pathname === '/api/v1/auth/status') body = { auth_enabled: authEnabled, requires_setup: false };
    else if (pathname === '/api/v1/settings') body = { language: 'en', time_format: '24h' };
    else if (pathname === '/api/v1/printers/') body = [{ ...status, serial_number: 'software-fixture', is_active: true }];
    else if (pathname === '/api/v1/auth/encryption-status') body = { key_configured: true, key_source: 'generated', decryption_broken: false, migration_error_count: 0, legacy_plaintext_rows: {}, encrypted_rows: {} };
    else if (pathname === '/api/v1/version') body = { version: 'fixture', latest_version: 'fixture' };
    else if (pathname.endsWith('/stream-token') || pathname.endsWith('/media-token')) body = { token: 'fixture-session', expires_in: 3600 };
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  return { requests, errors };
}
try {
  for (const layout of [
    { name: 'desktop-default', viewport: { width: 1440, height: 900 }, query: '' },
    { name: 'desktop-landscape', viewport: { width: 1440, height: 900 }, query: '&show=progress,layers,eta,filename,status,printer,model,temperatures&artwork=landscape' },
    { name: 'mobile-portrait', viewport: { width: 390, height: 844 }, query: '&show=progress,layers,eta,filename,status,printer,model,temperatures&artwork=portrait' },
    { name: 'mobile-landscape', viewport: { width: 844, height: 390 }, query: '&show=progress,layers,eta,filename,status,printer,model,temperatures&artwork=landscape&size=small' },
    { name: 'mobile-no-sensors', viewport: { width: 390, height: 844 }, query: '&show=model,temperatures&camera=false', readings: {} },
  ]) {
    const page = await browser.newPage({ viewport: layout.viewport, serviceWorkers: 'block' });
    const { requests, errors } = await fixture(page, true, layout.readings);
    const url = `${origin}/overlay/7?token=bblt_fixture${layout.query}`;
    await page.goto(url);
    const label = layout.readings ? 'H2D' : 'Workshop organizer';
    await page.getByText(label, { exact: true }).waitFor();
    assert.equal(page.url(), url);
    assert.equal(await page.evaluate(() => sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token')), null);
    if (layout.query.includes('temperatures') && !layout.readings) {
      await page.getByText('180°C → 220°C', { exact: true }).waitFor();
      await page.getByText('215°C', { exact: true }).waitFor();
    } else assert.equal(await page.getByText(/°C/).count(), 0);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.reload();
    await page.getByText(label, { exact: true }).waitFor();
    assert.equal(page.url(), url);
    assert.equal(requests.some(request => ['/api/v1/printers/7', '/api/v1/printers/7/status', '/api/v1/settings', '/api/v1/auth/ws-token'].includes(request.path)), false);
    assert.equal(requests.filter(request => request.path.endsWith('/camera/stream')).every(request => request.token === 'bblt_fixture'), true);
    assert.deepEqual(errors, []);
    await page.screenshot({ path: path.join(screenshots, `${layout.name}.png`) });
    console.log(JSON.stringify({ flow: layout.name, viewport: layout.viewport, passed: true, errors }));
    await page.close();
  }
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport, serviceWorkers: 'block' });
    const { requests, errors } = await fixture(page, false);
    await page.goto(`${origin}/settings?tab=integrations&sub=api-metrics#card-camera-tokens`);
    const builder = page.getByRole('region', { name: 'Streaming overlay builder' });
    await builder.waitFor();
    await builder.scrollIntoViewIfNeeded();
    assert.equal(requests.some(request => request.path.endsWith('/camera/stream')), false);
    await builder.screenshot({ path: path.join(screenshots, `builder-${viewport.width}.png`) });
    await builder.getByLabel('Overlay token (optional)').fill('bblt_fixture');
    await builder.getByText('Model', { exact: true }).click();
    await builder.getByText('Temperatures', { exact: true }).click();
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
    await builder.getByRole('button', { name: 'Copy', exact: true }).click();
    assert.equal(await page.evaluate(() => navigator.clipboard.readText()), `${origin}/overlay/7?show=progress%2Clayers%2Ceta%2Cfilename%2Cstatus%2Cmodel%2Ctemperatures&token=bblt_fixture`);
    assert.equal(requests.some(request => request.path.endsWith('/camera/stream')), false);
    await builder.getByRole('button', { name: 'Show preview' }).click();
    await page.frameLocator('iframe[title="Stream Overlay"]').getByText('H2D', { exact: true }).waitFor();
    await builder.getByRole('button', { name: 'Hide preview' }).click();
    assert.equal(await builder.locator('iframe').count(), 0);
    assert.deepEqual(errors.filter(error => !/WebSocket.*failed|\[WebSocket\] Error/.test(error)), []);
    console.log(JSON.stringify({ flow: 'settings -> builder -> copy -> preview -> close', viewport, passed: true }));
    await page.close();
  }
} finally { await browser.close(); }
