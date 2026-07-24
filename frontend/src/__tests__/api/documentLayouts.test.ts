import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { HttpResponse, http } from 'msw';
import { setupServer } from 'msw/node';

import { setAuthToken } from '../../api/client';
import {
  LayoutVersionConflictError,
  documentLayoutsApi,
  resolveLayoutAccess,
  type LayoutPatch,
} from '../../api/documentLayouts';

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  server.resetHandlers();
  setAuthToken(null);
  vi.restoreAllMocks();
});
afterAll(() => server.close());

const summary = {
  id: 17,
  scope: { business_profile_id: 4, document_type: 'invoice', language: 'de' },
  version: 3,
  status: 'draft',
  lock_version: 8,
  effective_from: null,
  created_at: '2026-07-23T10:00:00Z',
  updated_at: '2026-07-23T10:10:00Z',
};

describe('document layouts API', () => {
  it('loads the catalog and a typed layout detail', async () => {
    server.use(
      http.get('/api/v1/document-layouts/catalog', () =>
        HttpResponse.json({
          templates: [{ key: 'classic', version: '1.0', description: 'Classic' }],
          page_formats_mm: { A4: [210, 297] },
          languages: ['de', 'en'],
          document_types: ['invoice'],
        }),
      ),
      http.get('/api/v1/document-layouts/17', () =>
        HttpResponse.json({
          summary,
          effective: { schema_version: 1 },
          sourced: { effective: { schema_version: 1 } },
          validation_status: 'valid',
          validation_report: {},
          assets: [],
        }),
      ),
    );

    const catalog = await documentLayoutsApi.getCatalog();
    const detail = await documentLayoutsApi.getLayout(17);

    expect(catalog.templates[0].key).toBe('classic');
    expect(detail.summary.lock_version).toBe(8);
    expect(detail.assets).toEqual([]);
  });

  it('patches a draft with its lock version and edit session', async () => {
    const patch: LayoutPatch = {
      expected_lock_version: 8,
      edit_session_id: 'session-1234',
      page: { margin_top_mm: 20 },
    };
    server.use(
      http.patch('/api/v1/document-layouts/17', async ({ request }) => {
        expect(await request.json()).toEqual(patch);
        return HttpResponse.json({ ...summary, lock_version: 9 });
      }),
    );

    await expect(documentLayoutsApi.patchLayout(17, patch)).resolves.toMatchObject({
      lock_version: 9,
    });
  });

  it('raises a dedicated conflict error for stale layout versions', async () => {
    server.use(
      http.patch('/api/v1/document-layouts/17', () =>
        HttpResponse.json(
          { detail: { code: 'layout_version_conflict', message: 'stale draft' } },
          { status: 409 },
        ),
      ),
    );

    await expect(
      documentLayoutsApi.patchLayout(17, {
        expected_lock_version: 7,
        edit_session_id: 'session-1234',
        page: { margin_top_mm: 19 },
      }),
    ).rejects.toBeInstanceOf(LayoutVersionConflictError);
  });

  it('uploads an asset as FormData through the authenticated API path', async () => {
    setAuthToken('layout-token');
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({
        id: 3,
        business_profile_id: 4,
        asset_type: 'logo',
        original_name: 'logo.svg',
        mime_type: 'image/svg+xml',
        size_bytes: 7,
        sha256: 'a'.repeat(64),
        preflight_status: 'valid',
        preflight_report: {},
        created_at: '2026-07-23T10:00:00Z',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );

    const asset = await documentLayoutsApi.uploadAsset({
      businessProfileId: 4,
      assetType: 'logo',
      declaredSha256: 'a'.repeat(64),
      file: new File(['<svg/>'], 'logo.svg', { type: 'image/svg+xml' }),
    });

    const [url, options] = fetchSpy.mock.calls[0];
    const headers = new Headers(options?.headers);
    const form = options?.body;
    expect(url).toBe('/api/v1/document-layouts/assets');
    expect(headers.get('authorization')).toBe('Bearer layout-token');
    expect(headers.has('content-type')).toBe(false);
    expect(form).toBeInstanceOf(FormData);
    expect((form as FormData).get('business_profile_id')).toBe('4');
    expect((form as FormData).get('asset_type')).toBe('logo');
    expect((form as FormData).get('declared_sha256')).toBe('a'.repeat(64));
    expect((form as FormData).get('font_embedding_rights_confirmed')).toBe('false');
    expect((form as FormData).get('file')).toBeInstanceOf(File);
    expect(asset.preflight_status).toBe('valid');
  });

  it('polls preview state with AbortSignal and ETag, then returns the PDF blob', async () => {
    const controller = new AbortController();
    server.use(
      http.get('/api/v1/document-layouts/preview/job-1', ({ request }) => {
        expect(request.headers.get('if-none-match')).toBe('"job-v1"');
        expect(request.signal.aborted).toBe(false);
        return HttpResponse.json(
          { public_id: 'job-1', status: 'ready', layout_id: 17, lock_version: 8, expires_at: '2026-07-23T11:00:00Z', result_sha256: 'b'.repeat(64) },
          { headers: { ETag: '"job-v2"' } },
        );
      }),
      http.get('/api/v1/document-layouts/preview/job-1/pdf', () =>
        new HttpResponse(new Blob(['pdf'], { type: 'application/pdf' }), {
          headers: { 'Content-Type': 'application/pdf', ETag: '"pdf-v1"' },
        }),
      ),
    );

    const polled = await documentLayoutsApi.pollPreviewJob('job-1', {
      signal: controller.signal,
      etag: '"job-v1"',
    });
    const pdf = await documentLayoutsApi.downloadPreviewPdf('job-1', controller.signal);

    expect(polled.etag).toBe('"job-v2"');
    expect(polled.job?.status).toBe('ready');
    expect(pdf.blob.type).toBe('application/pdf');
    expect(pdf.etag).toBe('"pdf-v1"');
  });

  it('covers readiness, lifecycle, and external export contracts', async () => {
    server.use(
      http.get('/api/v1/document-layouts/17/readiness', () =>
        HttpResponse.json({ ready: true, findings: [], renderer_version: 'renderer-1', validator_version: 'validator-1' }),
      ),
      http.post('/api/v1/document-layouts/17/publish', async ({ request }) => {
        expect(await request.json()).toEqual({ expected_lock_version: 8, reason: 'Approved', effective_from: null });
        return HttpResponse.json({ ...summary, status: 'active' });
      }),
      http.post('/api/v1/document-layouts/17/withdraw', async ({ request }) => {
        expect(await request.json()).toEqual({ reason: 'Replaced' });
        return HttpResponse.json({ ...summary, status: 'withdrawn' });
      }),
      http.post('/api/v1/document-render', async ({ request }) => {
        expect(await request.json()).toEqual({
          document_snapshot_id: 44,
          published_layout_id: 17,
          idempotency_id: 'external-1234',
        });
        return HttpResponse.json({
          artifact_id: 91,
          sha256: 'c'.repeat(64),
          validation_status: 'valid',
          content_type: 'application/pdf',
          correlation_id: 'corr-1',
        });
      }),
    );

    expect((await documentLayoutsApi.getReadiness(17)).ready).toBe(true);
    expect((await documentLayoutsApi.publishLayout(17, { expected_lock_version: 8, reason: 'Approved', effective_from: null })).status).toBe('active');
    expect((await documentLayoutsApi.withdrawLayout(17, { reason: 'Replaced' })).status).toBe('withdrawn');
    expect((await documentLayoutsApi.exportExternal({ document_snapshot_id: 44, published_layout_id: 17, idempotency_id: 'external-1234' })).artifact_id).toBe(91);
  });

  it('expresses missing permissions as an explicit read-only access state', () => {
    expect(resolveLayoutAccess(['document_layouts:read'], true)).toEqual({
      mode: 'read-only',
      canRead: true,
      canManage: false,
      reason: 'missing_manage_permission',
    });
    expect(resolveLayoutAccess([], true)).toEqual({
      mode: 'unavailable',
      canRead: false,
      canManage: false,
      reason: 'missing_read_permission',
    });
    expect(resolveLayoutAccess([], false).mode).toBe('manage');
  });
});
