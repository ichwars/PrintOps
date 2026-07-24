import { expect, test, type Page, type Route } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { layoutDetail, layoutSummary } from '../src/__tests__/components/settings/document-layout/layoutFixtures';

const here = path.dirname(fileURLToPath(import.meta.url));
const pdfFixture = path.resolve(here, '../../backend/tests/fixtures/document_layouts/letterhead-a4.pdf');
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64');

type EvidenceKind = 'zugferd' | 'xrechnung';

interface MockState {
  detail: ReturnType<typeof layoutDetail>;
  ready: boolean;
  previewSource: string;
  evidenceKind: EvidenceKind | null;
  assetAttached: boolean;
  patchCount: number;
}

function respond(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

async function installDocumentLayoutApi(page: Page, evidenceKind: EvidenceKind | null = null) {
  const state: MockState = {
    detail: structuredClone(layoutDetail()),
    ready: false,
    previewSource: 'invoice-en-standard',
    evidenceKind,
    assetAttached: false,
    patchCount: 0,
  };

  await page.addInitScript(() => {
    localStorage.setItem('i18nextLng', 'en');
  });

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname.replace(/\/+$/, '');
    const method = request.method();

    if (pathname === '/api/v1/auth/status') {
      return respond(route, { auth_enabled: false, requires_setup: false });
    }
    if (pathname === '/api/v1/business-profiles/options') {
      return respond(route, [{
        id: 2,
        name: 'Main GmbH',
        country_code: 'DE',
        default_currency: 'EUR',
        timezone: 'Europe/Berlin',
        default_locale: 'en',
        billing_mode: 'commercial',
        is_default: true,
        is_active: true,
      }]);
    }
    if (pathname === '/api/v1/document-layouts/catalog') {
      return respond(route, {
        templates: [
          { key: 'classic', version: '1.0.0', description: 'Classic' },
          { key: 'modern', version: '1.0.0', description: 'Modern' },
          { key: 'compact', version: '1.0.0', description: 'Compact' },
        ],
        page_formats_mm: { A4: [210, 297], Letter: [215.9, 279.4] },
        languages: ['de', 'en'],
        document_types: ['invoice'],
      });
    }
    if (pathname === '/api/v1/document-layouts/samples') {
      return respond(route, [{
        id: 'invoice-en-standard',
        label: 'Standard invoice',
        document_type: 'invoice',
        language: 'en',
      }]);
    }
    if (pathname === '/api/v1/commercial-documents') {
      return respond(route, [{
        id: 41,
        number: 'RE-2026-0041',
        document_type: 'invoice',
        language: 'en',
        issue_date: '2026-07-23',
        technical_status: 'issued',
      }]);
    }
    if (pathname === '/api/v1/document-layouts' && method === 'GET') {
      return respond(route, [
        state.detail.summary,
        { ...layoutSummary(1), id: 11, version: 0, status: 'withdrawn' },
      ]);
    }
    if (pathname === '/api/v1/document-layouts/17' && method === 'GET') {
      return respond(route, state.detail);
    }
    if (pathname === '/api/v1/document-layouts/17' && method === 'PATCH') {
      const body = request.postDataJSON() as Record<string, Record<string, unknown>>;
      state.patchCount += 1;
      state.detail.summary.lock_version += 1;
      state.detail.summary.updated_at = new Date().toISOString();
      for (const section of ['page', 'typography', 'header', 'title', 'positions', 'totals', 'technical', 'notes', 'footer'] as const) {
        if (body[section]) Object.assign(state.detail.effective[section], body[section]);
      }
      return respond(route, state.detail.summary);
    }
    if (pathname === '/api/v1/document-layouts/17/readiness') {
      return respond(route, state.ready ? {
        ready: true,
        findings: [],
        renderer_version: '1.0.0',
        validator_version: '1.30.2',
      } : {
        ready: false,
        findings: [{
          code: 'logo_required',
          severity: 'blocker',
          field_path: 'assets.logo',
          message_key: 'logo_required',
          message: 'Upload and assign a valid logo.',
          correction_hint: 'Open assets.',
          external_rule_id: null,
        }],
        renderer_version: '1.0.0',
        validator_version: '1.30.2',
      });
    }
    if (pathname === '/api/v1/document-layouts/17/audit') {
      return respond(route, [{
        id: 1,
        layout_id: 17,
        event_type: 'updated',
        edit_session_id: 'browser-test',
        reason: 'Browser acceptance',
        changed_field_paths: ['page.margin_top_mm'],
        actor_id: null,
        first_seen_at: '2026-07-23T08:00:00Z',
        last_seen_at: '2026-07-23T08:01:00Z',
      }]);
    }
    if (pathname === '/api/v1/document-layouts/assets' && method === 'POST') {
      return respond(route, {
        id: 71,
        business_profile_id: 2,
        asset_type: 'logo',
        original_name: 'logo.png',
        mime_type: 'image/png',
        size_bytes: png.length,
        sha256: 'a'.repeat(64),
        preflight_status: 'valid',
        preflight_report: { width_px: 1, height_px: 1, metadata_removed: true },
        created_at: '2026-07-23T08:00:00Z',
      });
    }
    if (pathname === '/api/v1/document-layouts/17/assets' && method === 'POST') {
      state.assetAttached = true;
      state.ready = true;
      state.detail.assets = [{
        id: 71,
        business_profile_id: 2,
        asset_type: 'logo',
        original_name: 'logo.png',
        mime_type: 'image/png',
        size_bytes: png.length,
        sha256: 'a'.repeat(64),
        preflight_status: 'valid',
        preflight_report: { width_px: 1, height_px: 1, metadata_removed: true },
        created_at: '2026-07-23T08:00:00Z',
      }];
      return respond(route, { layout_id: 17, asset_id: 71, role: 'logo' });
    }
    if (pathname === '/api/v1/document-layouts/assets/71' && method === 'GET') {
      return route.fulfill({ status: 200, contentType: 'image/png', body: png });
    }
    if (pathname === '/api/v1/document-layouts/preview' && method === 'POST') {
      const body = request.postDataJSON() as { source_id: string };
      state.previewSource = body.source_id;
      return respond(route, {
        public_id: '11111111-1111-4111-8111-111111111111',
        status: 'ready',
        layout_id: 17,
        lock_version: state.detail.summary.lock_version,
        expires_at: '2026-07-24T08:00:00Z',
        result_sha256: 'b'.repeat(64),
      }, 200);
    }
    if (pathname.endsWith('/preview/11111111-1111-4111-8111-111111111111/pdf')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/pdf',
        headers: { ETag: '"browser-pdf"' },
        path: pdfFixture,
      });
    }
    if (pathname.endsWith('/preview/11111111-1111-4111-8111-111111111111/report')) {
      const einvoice = state.previewSource === '41' && state.evidenceKind ? {
        kind: state.evidenceKind,
        original: state.evidenceKind === 'zugferd' ? 'pdf' : 'xml',
        profile: state.evidenceKind === 'zugferd' ? 'EN16931' : 'XRechnung 3.0',
        xml_sha256: 'c'.repeat(64),
        pdf_artifact_id: state.evidenceKind === 'xrechnung' ? 91 : null,
      } : undefined;
      return respond(route, {
        status: 'ready',
        findings: {
          validation_status: 'valid',
          warnings: [],
          ...(einvoice ? { einvoice } : {}),
        },
      });
    }
    if (pathname === '/api/v1/document-layouts/17/publish' && method === 'POST') {
      state.detail.summary.status = 'active';
      state.detail.summary.version += 1;
      return respond(route, state.detail.summary);
    }
    if (pathname === '/api/v1/document-render/artifacts/91') {
      return route.fulfill({ status: 200, contentType: 'application/pdf', path: pdfFixture });
    }
    if (pathname.startsWith('/api/v1/')) {
      const listLike = /(printers|smart-plugs|notifications|api-keys|notification-templates|external-links|queue|groups|users|plugins|providers|presets|options|default-sidebar-order)$/.test(pathname);
      return respond(route, listLike ? [] : {});
    }
    return route.continue();
  });

  return state;
}

async function openWorkspace(page: Page) {
  await page.goto('/settings?tab=orders-calculation&sub=format-preview');
  await expect(page.locator('#document-layout-workspace')).toBeVisible();
  await expect(page.locator('#document-layout-workspace').getByRole('heading', { name: /Format & Preview/i })).toBeVisible();
  await expect(page.getByRole('img', { name: 'PDF page 1' })).toBeVisible();
}

test.describe('document layout desktop workflow', () => {
  test.use({ viewport: { width: 1440, height: 1000 } });

  test('preview left and compact controls right with persisted autosave and release flow', async ({ page }) => {
    const state = await installDocumentLayoutApi(page);
    await openWorkspace(page);

    const main = page.locator('#document-layout-workspace main');
    const preview = main.locator(':scope > div').first();
    const controls = main.locator(':scope > aside');
    const previewBox = await preview.boundingBox();
    const controlsBox = await controls.boundingBox();
    expect(previewBox).not.toBeNull();
    expect(controlsBox).not.toBeNull();
    expect(previewBox!.x).toBeLessThan(controlsBox!.x);
    expect(previewBox!.width / controlsBox!.width).toBeGreaterThan(1.65);

    const publish = page.getByRole('button', { name: /^Publish$/i });
    await expect(publish).toBeDisabled();

    const topMargin = page.getByRole('spinbutton', { name: /Top margin/i });
    await topMargin.fill('23');
    await expect.poll(() => state.patchCount).toBe(1);
    await expect(page.getByText('Saved', { exact: true }).first()).toBeVisible();

    await page.reload();
    await expect(page.getByRole('spinbutton', { name: /Top margin/i })).toHaveValue('23');

    await page.getByRole('button', { name: /Assets and fonts/i }).click();
    await page.locator('input[type=file]').setInputFiles({
      name: 'logo.png',
      mimeType: 'image/png',
      buffer: png,
    });
    await expect.poll(() => state.assetAttached).toBe(true);
    await expect(page.getByText('logo.png')).toBeVisible();
    await expect(page.getByText(/Preflight passed/i)).toBeVisible();
    await expect(publish).toBeEnabled();

    await page.getByRole('button', { name: /History/i }).click();
    await expect(page.getByText('Version 1')).toBeVisible();
    await expect(page.getByText('Browser acceptance')).toBeVisible();
    await page.getByRole('button', { name: /Close/i }).click();

    await publish.click();
    await page.getByLabel(/Publication reason/i).fill('Approved in browser acceptance');
    await page.getByRole('button', { name: /Confirm/i }).click();
    await expect.poll(() => state.detail.summary.status).toBe('active');
  });
});

test.describe('document layout mobile workflow', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('mobile stacks preview before controls without overflow', async ({ page }) => {
    await installDocumentLayoutApi(page);
    await openWorkspace(page);

    const main = page.locator('#document-layout-workspace main');
    const preview = main.locator(':scope > div').first();
    const controls = main.locator(':scope > aside');
    const previewBox = await preview.boundingBox();
    const controlsBox = await controls.boundingBox();
    expect(previewBox).not.toBeNull();
    expect(controlsBox).not.toBeNull();
    expect(previewBox!.y).toBeLessThan(controlsBox!.y);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
    expect(await page.evaluate(() => window.innerWidth)).toBe(390);
  });
});

for (const evidenceKind of ['zugferd', 'xrechnung'] as const) {
  test(evidenceKind + ' exposes the correct original and evidence in a real-document preview', async ({ page }) => {
    await installDocumentLayoutApi(page, evidenceKind);
    await openWorkspace(page);

    const source = page.getByRole('combobox', { name: /Preview source/i });
    await source.click();
    await page.getByRole('option', { name: /RE-2026-0041/i }).click();

    const evidence = page.getByTestId('einvoice-evidence');
    await expect(evidence).toBeVisible();
    await expect(evidence).toContainText(evidenceKind === 'zugferd' ? 'PDF is original' : 'XML is original');
    await expect(evidence).toContainText(evidenceKind === 'zugferd' ? 'ZUGFeRD' : 'XRechnung');
    await expect(evidence).toContainText('XML SHA-256:');
    if (evidenceKind === 'xrechnung') {
      await expect(page.getByRole('button', { name: /Download separate PDF visual copy/i })).toBeVisible();
      await expect(evidence).not.toContainText('ZUGFeRD');
    }
  });
}
