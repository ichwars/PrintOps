import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { lexwareApi } from '../../api/client/lexware';
import { server } from '../mocks/server';

describe('Lexware PrintOps API contract', () => {
  it('uses only local connection routes and sends the tested organization with create', async () => {
    const requests: Array<{ method: string; pathname: string; body: unknown }> = [];
    server.use(http.all('/api/v1/lexware/connections*', async ({ request }) => {
      requests.push({ method: request.method, pathname: new URL(request.url).pathname, body: request.method === 'GET' || request.method === 'DELETE' ? null : await request.text().then((text) => text ? JSON.parse(text) : null) });
      if (request.method === 'DELETE') return new HttpResponse(null, { status: 204 });
      return HttpResponse.json({ organization_id: 'organization', company_name: 'Example' });
    }));
    await lexwareApi.connections();
    await lexwareApi.test('test-only-key');
    await lexwareApi.create({ business_profile_id: 7, api_key: 'test-only-key', organization_id: 'organization' });
    await lexwareApi.update(3, { enabled: false });
    await lexwareApi.sync(3);
    await lexwareApi.disconnect(3);
    expect(requests).toEqual([
      { method: 'GET', pathname: '/api/v1/lexware/connections', body: null },
      { method: 'POST', pathname: '/api/v1/lexware/connections/test', body: { api_key: 'test-only-key' } },
      { method: 'POST', pathname: '/api/v1/lexware/connections', body: { business_profile_id: 7, api_key: 'test-only-key', organization_id: 'organization' } },
      { method: 'PATCH', pathname: '/api/v1/lexware/connections/3', body: { enabled: false } },
      { method: 'POST', pathname: '/api/v1/lexware/connections/3/sync', body: null },
      { method: 'DELETE', pathname: '/api/v1/lexware/connections/3', body: null },
    ]);
  });

  it('preserves explicit targets, exact decimal values, selected fields and reviewed versions', async () => {
    const requests: unknown[] = [];
    server.use(
      http.get('/api/v1/lexware/connections/3/resources', ({ request }) => {
        expect(new URL(request.url).searchParams.get('kind')).toBe('articles');
        return HttpResponse.json([]);
      }),
      http.post('/api/v1/lexware/connections/3/:action', async ({ request }) => {
        requests.push(await request.json()); return HttpResponse.json({ unchanged: false });
      }),
    );
    await lexwareApi.resources(3, 'articles');
    await lexwareApi.preview(3, { resource_id: 12, article_id: 81 });
    await lexwareApi.import(3, { resource_id: 12, article_id: 81, version_hash: 'a'.repeat(64), local_version: 9, fields: ['sale_price'] });
    await lexwareApi.import(3, { resource_id: 13, article_id: null, version_hash: 'b'.repeat(64), local_version: null,
      fields: ['name', 'sale_price'], article_options: { sku: 'LOCAL-1', kind: 'trade', unit_code: 'pcs', stock_source: 'material', small_part_id: 40 } });
    expect(requests).toEqual([
      { resource_id: 12, article_id: 81 },
      { resource_id: 12, article_id: 81, version_hash: 'a'.repeat(64), local_version: 9, fields: ['sale_price'] },
      { resource_id: 13, article_id: null, version_hash: 'b'.repeat(64), local_version: null,
        fields: ['name', 'sale_price'], article_options: { sku: 'LOCAL-1', kind: 'trade', unit_code: 'pcs', stock_source: 'material', small_part_id: 40 } },
    ]);
  });
});
