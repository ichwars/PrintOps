import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { SmallPartsPage } from '../../pages/SmallPartsPage';
import { server } from '../mocks/server';

const part = {
  id: 7,
  sku: 'M3-INSERT',
  name: 'M3 Gewindeeinsatz',
  description: null,
  search_terms: null,
  category_id: null,
  unit_code: 'C62',
  location_id: null,
  minimum_stock: '20.000000',
  unit_cost: '0.080000',
  supplier_reference: null,
  is_active: true,
  category: null,
  unit: { code: 'C62', label: 'Stück', decimal_places: 0, is_active: true },
  balance: { physical: '50.000000', reserved: '8.000000', available: '42.000000', is_low_stock: false },
  created_at: '2026-07-18T10:00:00Z',
  updated_at: '2026-07-18T10:00:00Z',
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SmallPartsPage />
    </QueryClientProvider>,
  );
}

describe('SmallPartsPage', () => {
  it('shows balances and searches the catalog', async () => {
    const seenQueries: string[] = [];
    server.use(
      http.get('/api/v1/small-parts', ({ request }) => {
        seenQueries.push(new URL(request.url).searchParams.get('q') ?? '');
        return HttpResponse.json({ items: [part], total: 1, limit: 50, offset: 0 });
      }),
    );
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole('heading', { name: 'Kleinteile' })).toBeInTheDocument();
    expect(await screen.findByText('M3 Gewindeeinsatz')).toBeInTheDocument();
    expect(screen.getByText('42 Stück verfügbar')).toBeInTheDocument();
    await user.type(screen.getByRole('searchbox', { name: 'Kleinteile durchsuchen' }), 'M3');

    await waitFor(() => expect(seenQueries).toContain('M3'));
  });

  it('posts a stock receipt with a required reason', async () => {
    const posted = vi.fn();
    server.use(
      http.get('/api/v1/small-parts', () => HttpResponse.json({ items: [part], total: 1, limit: 50, offset: 0 })),
      http.get('/api/v1/small-parts/7/ledger', () => HttpResponse.json([])),
      http.post('/api/v1/small-parts/7/ledger', async ({ request }) => {
        posted(await request.json());
        return HttpResponse.json({
          id: 1,
          small_part_id: 7,
          entry_kind: 'receipt',
          physical_delta: '10.000000',
          reserved_delta: '0.000000',
          reason: 'Einkauf',
          reference_type: null,
          reference_id: null,
          actor_id: null,
          idempotency_key: 'receipt-test-0001',
          created_at: '2026-07-18T12:00:00Z',
        }, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Bestand buchen' }));
    await user.type(screen.getByLabelText('Menge'), '10');
    await user.type(screen.getByLabelText('Grund'), 'Einkauf');
    await user.click(screen.getByRole('button', { name: 'Buchung speichern' }));

    await waitFor(() => expect(posted).toHaveBeenCalledWith(expect.objectContaining({ quantity: '10', reason: 'Einkauf' })));
  });
});
