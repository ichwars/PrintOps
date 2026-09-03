import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import LexwareDocumentsPage from '../../pages/LexwareDocumentsPage';
import { lexwareDocumentsApi } from '../../api/client/lexware-documents';
import { setAuthToken } from '../../api/client/core';
import { render } from '../utils';
import { server } from '../mocks/server';

const auth = vi.hoisted(() => ({ permissions: new Set<string>() }));
vi.mock('../../contexts/AuthContext', async () => ({
  ...await vi.importActual<typeof import('../../contexts/AuthContext')>('../../contexts/AuthContext'),
  useAuth: () => ({ hasPermission: (permission: string) => auth.permissions.has(permission) }),
}));

const document = {
  id: 12, connection_id: 4, business_profile_id: 2, company_name: 'External Co', source: 'lexware',
  external_id: 'b1895cec-754f-4d78-a7ae-a6c56609c5a2', voucher_type: 'invoice', voucher_status: 'paid',
  voucher_number: 'LX-42', voucher_date: '2026-08-01', due_date: '2026-08-14', contact_name: 'Customer Co',
  supported: true, archived: false, in_latest_sync: true, connection_enabled: true, sync_status: 'success',
  last_success_at: '2026-08-31T12:00:00Z', updated_at: '2026-08-31T12:00:00Z', version: 3, local_document_id: null,
  finance: { currency: 'EUR', total_amount: '123.45', open_amount: null, payment_state: 'unknown', payment_status: null,
    direction: 'receivable', credit: false, overdue: null, included_in_totals: false, exclusion_reason: 'unknown_payment', payment_items: [] },
  files: [],
};
const finance = { source: 'lexware', as_of: '2026-08-31', totals: [], included_count: 0, linked_count: 0, unknown_count: 1, excluded_count: 1, unsupported_count: 0, stale_connection_count: 0 };

beforeEach(() => {
  auth.permissions = new Set(['commercial_documents:read', 'payments:read', 'commercial_documents:draft']);
  setAuthToken(null);
  server.use(
    http.get('/api/v1/business-profiles/options', () => HttpResponse.json([{ id: 2, name: 'Main profile' }])),
    http.get('/api/v1/lexware/documents', () => HttpResponse.json({ items: [document], total: 1 })),
    http.get('/api/v1/lexware/documents/12', () => HttpResponse.json(document)),
    http.get('/api/v1/lexware/finance', () => HttpResponse.json(finance)),
    http.get('/api/v1/commercial-documents', () => HttpResponse.json([{ id: 6, number: 'LOCAL-6', document_type: 'invoice', technical_status: 'issued', total_amount: '123.45', currency: 'EUR' }])),
  );
});

describe('Lexware documents', () => {
  it('shows missing payment data as unknown and keeps the local-link action explicit', async () => {
    render(<LexwareDocumentsPage />);
    expect(await screen.findByText('LX-42')).toBeInTheDocument();
    expect(await screen.findByText('Unknown')).toBeInTheDocument();
    expect(screen.getByText(/Not a bank balance/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Details' }));
    expect(await screen.findByText('Manual PrintOps linkage')).toBeInTheDocument();
    expect(screen.queryByText('Settled (not necessarily a bank payment)')).not.toBeInTheDocument();
  });

  it('does not request finance or expose links and originals without payment permission', async () => {
    auth.permissions = new Set(['commercial_documents:read']);
    let financialRequests = 0;
    server.use(http.get('/api/v1/lexware/finance', () => { financialRequests++; return HttpResponse.json(finance); }));
    const { finance: _finance, files: _files, ...redacted } = document;
    server.use(
      http.get('/api/v1/lexware/documents', () => HttpResponse.json({ items: [redacted], total: 1 })),
      http.get('/api/v1/lexware/documents/12', () => HttpResponse.json(redacted)),
    );
    render(<LexwareDocumentsPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Details' }));
    expect(await screen.findByText('Financial details and original files require payment read permission.')).toBeInTheDocument();
    expect(screen.queryByText('Manual PrintOps linkage')).not.toBeInTheDocument();
    expect(screen.queryByText('Separate Lexware finance')).not.toBeInTheDocument();
    expect(financialRequests).toBe(0);
  });

  it('submits the selected local document and current version; surfaces a stale link conflict', async () => {
    let body: unknown;
    server.use(http.put('/api/v1/lexware/documents/12/link', async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ detail: 'Changed' }, { status: 409 });
    }));
    render(<LexwareDocumentsPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Details' }));
    await userEvent.click(screen.getByRole('combobox', { name: 'Choose a local document' }));
    await userEvent.click(await screen.findByRole('option', { name: /LOCAL-6/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Link document' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The document changed. Reload it before retrying.');
    expect(body).toEqual({ local_document_id: 6, expected_version: 3 });
  });

  it('resets pagination when search filters change and labels unsupported types', async () => {
    const queries: URL[] = [];
    server.use(http.get('/api/v1/lexware/documents', ({ request }) => {
      queries.push(new URL(request.url));
      return HttpResponse.json({ items: [{ ...document, supported: false, voucher_type: 'deliverynote' }], total: 26 });
    }));
    render(<LexwareDocumentsPage />);
    expect(await screen.findByText('Unsupported type — not imported into finance')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(queries.some(query => query.searchParams.get('offset') === '25')).toBe(true));
    await userEvent.type(screen.getByLabelText('Search number or contact'), 'LX');
    await waitFor(() => expect(queries.at(-1)?.searchParams.get('search')).toBe('LX'));
    expect(queries.at(-1)?.searchParams.get('offset')).toBe('0');
  });

  it('downloads the binary original with authentication, never a token in the URL', async () => {
    setAuthToken('test-download-token');
    server.use(http.get('/api/v1/lexware/documents/12/files/original-id', ({ request }) => {
      expect(request.headers.get('Authorization')).toBe('Bearer test-download-token');
      expect(new URL(request.url).search).toBe('');
      return new HttpResponse('%PDF-original', { headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="lexware-original.pdf"' } });
    }));
    const result = await lexwareDocumentsApi.download(12, 'original-id');
    expect(result.filename).toBe('lexware-original.pdf');
    expect(result.blob.size).toBe(13);
  });
});
