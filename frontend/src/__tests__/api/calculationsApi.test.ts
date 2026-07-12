import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { calculationsApi } from '../../api/calculations';

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('calculations API', () => {
  it('uses the calculation workflow endpoints and serializes command payloads', async () => {
    const calls: Array<{ path: string; method: string; body: unknown }> = [];
    server.use(
      http.all('/api/v1/calculations/*', async ({ request }) => {
        const url = new URL(request.url);
        let body: unknown = null;
        if (request.method !== 'GET') body = await request.json().catch(() => null);
        calls.push({ path: `${url.pathname}${url.search}`, method: request.method, body });
        if (url.pathname.endsWith('/validation')) return HttpResponse.json({ blockers: [], warnings: [] });
        if (url.pathname.endsWith('/revisions') || url.pathname.endsWith('/templates')) return HttpResponse.json([]);
        return HttpResponse.json({ id: 7 });
      }),
    );

    await calculationsApi.list({ status: 'draft', limit: 10, offset: 5 });
    await calculationsApi.list();
    await calculationsApi.preview({} as never);
    await calculationsApi.previewBatch([], {} as never);
    await calculationsApi.get(7);
    await calculationsApi.create({} as never);
    await calculationsApi.update(7, {} as never);
    await calculationsApi.validate(7);
    await calculationsApi.approve(7, 3, { manual_source_values: 'Checked' });
    await calculationsApi.revise(7);
    await calculationsApi.archive(7, 3);
    await calculationsApi.revisions(7);
    await calculationsApi.createTemplate(7, 'Standard');
    await calculationsApi.templates();
    await calculationsApi.instantiateTemplate(4, 'New quote');

    expect(calls.map(call => `${call.method} ${call.path}`)).toEqual([
      'GET /api/v1/calculations/?status=draft&limit=10&offset=5',
      'GET /api/v1/calculations/?limit=50&offset=0',
      'POST /api/v1/calculations/preview',
      'POST /api/v1/calculations/preview-batch',
      'GET /api/v1/calculations/7',
      'POST /api/v1/calculations/',
      'PUT /api/v1/calculations/7',
      'GET /api/v1/calculations/7/validation',
      'POST /api/v1/calculations/7/approve',
      'POST /api/v1/calculations/7/revise',
      'POST /api/v1/calculations/7/archive?expected_version=3',
      'GET /api/v1/calculations/7/revisions',
      'POST /api/v1/calculations/7/templates',
      'GET /api/v1/calculations/templates',
      'POST /api/v1/calculations/templates/4/instantiate',
    ]);
    expect(calls[8].body).toEqual({ expected_version: 3, warning_reasons: { manual_source_values: 'Checked' } });
    expect(calls[14].body).toEqual({ title: 'New quote', customer_id: null });
  });

  it('uploads a 3MF source and reports rejected uploads', async () => {
    server.use(http.post('/api/v1/calculations/source-files', () => HttpResponse.json({ filename: 'part.3mf' })));
    await expect(calculationsApi.uploadSource(new File(['zip'], 'part.3mf'))).resolves.toMatchObject({ filename: 'part.3mf' });

    server.use(http.post('/api/v1/calculations/source-files', () => new HttpResponse(null, { status: 422 })));
    await expect(calculationsApi.uploadSource(new File(['bad'], 'bad.3mf'))).rejects.toThrow('Upload failed (422)');
  });
});
