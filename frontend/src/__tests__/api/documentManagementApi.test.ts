import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { HttpResponse, http } from 'msw';
import { setupServer } from 'msw/node';

import { ApiError } from '../../api/client';
import { documentManagementApi } from '../../api/documentManagement';

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('document management API', () => {
  it('publishes a configuration with optimistic version and reason', async () => {
    server.use(
      http.post('/api/v1/document-configurations/17/publish', async ({ request }) => {
        expect(await request.json()).toEqual({
          expected_version: 3,
          effective_from: '2026-08-01',
          reason: 'Updated invoice terms',
        });
        return HttpResponse.json({
          id: 17,
          business_profile_id: 4,
          document_type: 'invoice',
          language: 'de-DE',
          version: 3,
          status: 'scheduled',
          effective_from: '2026-08-01',
          lock_version: 4,
          change_reason: 'Updated invoice terms',
          published_at: null,
          policy: null,
          validation_findings: [],
        });
      }),
    );

    const result = await documentManagementApi.publishConfiguration(
      17,
      3,
      '2026-08-01',
      'Updated invoice terms',
    );

    expect(result.status).toBe('scheduled');
  });

  it('preserves structured findings on API errors', async () => {
    server.use(
      http.post('/api/v1/commercial-documents/9/validate', () =>
        HttpResponse.json(
          {
            detail: {
              code: 'document_not_ready',
              message: 'Document is incomplete',
              field_path: 'einvoice.buyer_reference',
              rule_id: 'BR-DE-15',
              correlation_id: 'corr-123',
              findings: [],
            },
          },
          { status: 409 },
        ),
      ),
    );

    const error = await documentManagementApi.validateDocument(9).catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).detail?.rule_id).toBe('BR-DE-15');
    expect((error as ApiError).detail?.correlation_id).toBe('corr-123');
  });
});
