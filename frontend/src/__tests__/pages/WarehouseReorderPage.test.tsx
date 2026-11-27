import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SmallPart } from '../../api/smallParts';
import type { WarehouseArticle } from '../../api/client/warehouse-articles';
import { WarehouseReorderPage } from '../../pages/WarehouseReorderPage';
import i18n from '../../i18n';
import { server } from '../mocks/server';

const permissions = vi.hoisted(() => new Set(['inventory:read']));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ hasPermission: (permission: string) => permissions.has(permission) }) }));

// The warehouseReorder namespace is integrated centrally into the locale files;
// until then the tests register the English copy directly on the i18n instance.
const reorderCopyEn = {
  orders: {
    runtimeDomain: {
      warehouseReorder: {
        title: 'Reorder needs',
        subtitle: 'Aggregated low stock from warehouse goods and material.',
        empty: 'No reorder needs.',
        open: 'Open',
        summaryWarehouse: 'Low-stock warehouse goods',
        summaryMaterial: 'Low-stock material',
        summaryTotal: 'Total',
        colArea: 'Area',
        colSuggested: 'Suggested order quantity',
        colAction: 'Action',
        areaWarehouse: 'Warehouse goods',
        areaMaterial: 'Material',
      },
    },
  },
};

const article: WarehouseArticle = {
  id: 1, sku: 'GOOD-1', name: 'Printed bracket', kind: 'finished', unit_code: 'C62', description: null,
  stock_source: 'own', small_part_id: null, project_id: null, calculation_revision_id: null,
  sale_price: '12.5', unit_cost: '0', tax_rate: '19', minimum_stock: '10', is_active: true,
  version: 1, has_history: false, created_at: '2026-08-31T10:00:00Z', updated_at: '2026-08-31T10:00:00Z',
  balance: { physical: '5', reserved: '2', available: '3', is_low_stock: true },
  locations: [],
};

const article2: WarehouseArticle = {
  ...article,
  id: 2, sku: 'GOOD-2', name: 'Second article',
  minimum_stock: '5', balance: { physical: '5', reserved: '0', available: '5', is_low_stock: true },
};

const part: SmallPart = {
  id: 7, sku: 'M3-INSERT', name: 'M3 threaded insert', description: null, search_terms: null,
  category_id: null, unit_code: 'C62', location_id: null, minimum_stock: '20.000000', unit_cost: '0.080000',
  supplier_reference: null, default_consumption_reason: 'Production', internal_notes: null, is_active: true,
  preferred_offer: null, category: null,
  unit: { code: 'C62', label: 'Piece', decimal_places: 0, is_active: true },
  balance: { physical: '6.000000', reserved: '2.000000', available: '4.000000', is_low_stock: true },
  created_at: '2026-07-18T10:00:00Z', updated_at: '2026-07-18T10:00:00Z',
};

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return { ...render(<MemoryRouter><QueryClientProvider client={client}><WarehouseReorderPage /></QueryClientProvider></MemoryRouter>), client };
}

beforeEach(async () => {
  await i18n.changeLanguage('en');
  i18n.addResourceBundle('en', 'translation', reorderCopyEn, true, true);
  permissions.clear();
  permissions.add('inventory:read');
  server.use(
    http.get('*/api/v1/warehouse-articles', () => HttpResponse.json({ items: [article], total: 1, limit: 200, offset: 0 })),
    http.get('*/api/v1/small-parts', () => HttpResponse.json({ items: [part], total: 1, limit: 200, offset: 0 })),
  );
});

afterEach(() => vi.restoreAllMocks());

describe('WarehouseReorderPage', () => {
  it('aggregates low stock from warehouse goods and material with suggested quantities and links', async () => {
    mount();

    expect(await screen.findByRole('heading', { name: 'Reorder needs' })).toBeInTheDocument();
    expect(await screen.findByText('GOOD-1')).toBeInTheDocument();
    expect(screen.getByText('M3-INSERT')).toBeInTheDocument();

    // Area badges
    expect(screen.getByText('Warehouse goods')).toBeInTheDocument();
    expect(screen.getByText('Material')).toBeInTheDocument();

    // Suggested order quantity = minimum - available: 10 - 3 = 7, 20 - 4 = 16
    expect(screen.getByText('7 C62')).toBeInTheDocument();
    expect(screen.getByText('16 C62')).toBeInTheDocument();
    expect(screen.getByText('3 C62')).toBeInTheDocument();
    expect(screen.getByText('4 C62')).toBeInTheDocument();

    // Summary cards
    expect(screen.getByText('Low-stock warehouse goods').parentElement).toHaveTextContent('1');
    expect(screen.getByText('Low-stock material').parentElement).toHaveTextContent('1');
    expect(screen.getByText('Total').parentElement).toHaveTextContent('2');

    // Row actions open the existing pages
    const openLinks = screen.getAllByRole('link', { name: 'Open' });
    const hrefs = openLinks.map((link) => link.getAttribute('href'));
    expect(hrefs).toContain('/warehouse/stock');
    expect(hrefs).toContain('/warehouse/parts');

    // Header actions lead to suppliers and offers
    expect(screen.getByRole('link', { name: 'Suppliers' })).toHaveAttribute('href', '/warehouse/suppliers');
    expect(screen.getByRole('link', { name: 'Offers' })).toHaveAttribute('href', '/orders/offers');
  });

  it('requests both endpoints with active + low_stock filters and loops pages until total is reached', async () => {
    const requested: string[] = [];
    server.use(
      http.get('*/api/v1/warehouse-articles', ({ request }) => {
        const url = new URL(request.url);
        requested.push(`warehouse-articles${url.search}`);
        const offset = Number(url.searchParams.get('offset') ?? '0');
        // Force one item per page so the loop has to request the next page.
        const items = [article, article2].slice(offset, offset + 1);
        return HttpResponse.json({ items, total: 2, limit: 200, offset });
      }),
      http.get('*/api/v1/small-parts', ({ request }) => {
        const url = new URL(request.url);
        requested.push(`small-parts${url.search}`);
        return HttpResponse.json({ items: [part], total: 1, limit: 200, offset: 0 });
      }),
    );
    mount();

    expect(await screen.findByText('GOOD-1')).toBeInTheDocument();
    expect(await screen.findByText('GOOD-2')).toBeInTheDocument();
    expect(screen.getByText('M3-INSERT')).toBeInTheDocument();

    expect(requested).toHaveLength(3);
    for (const entry of requested) {
      expect(entry).toContain('active=true');
      expect(entry).toContain('low_stock=true');
      expect(entry).toContain('limit=200');
    }
    const articleRequests = requested.filter((entry) => entry.startsWith('warehouse-articles'));
    expect(articleRequests).toHaveLength(2);
    expect(articleRequests.some((entry) => entry.includes('offset=0'))).toBe(true);
    expect(articleRequests.some((entry) => entry.includes('offset=1'))).toBe(true);
  });

  it('shows the empty state when both areas have no low stock', async () => {
    server.use(
      http.get('*/api/v1/warehouse-articles', () => HttpResponse.json({ items: [], total: 0, limit: 200, offset: 0 })),
      http.get('*/api/v1/small-parts', () => HttpResponse.json({ items: [], total: 0, limit: 200, offset: 0 })),
    );
    mount();

    expect(await screen.findByText('No reorder needs.')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('shows the error state with retry when a request fails', async () => {
    server.use(
      http.get('*/api/v1/warehouse-articles', () => HttpResponse.json({ detail: 'Unavailable' }, { status: 503 })),
    );
    const user = userEvent.setup();
    mount();

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load warehouse data.');
    expect(screen.queryByText('GOOD-1')).not.toBeInTheDocument();

    server.use(
      http.get('*/api/v1/warehouse-articles', () => HttpResponse.json({ items: [article], total: 1, limit: 200, offset: 0 })),
    );
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('GOOD-1')).toBeInTheDocument();
  });

  it('refuses to fetch and shows the no-read alert without inventory:read', async () => {
    permissions.clear();
    let articlesRequested = false;
    let partsRequested = false;
    server.use(
      http.get('*/api/v1/warehouse-articles', () => { articlesRequested = true; return HttpResponse.json({ items: [], total: 0 }); }),
      http.get('*/api/v1/small-parts', () => { partsRequested = true; return HttpResponse.json({ items: [], total: 0 }); }),
    );
    mount();

    expect(screen.getByRole('alert')).toHaveTextContent('You do not have permission to read warehouse articles.');
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(articlesRequested).toBe(false);
    expect(partsRequested).toBe(false);
  });
});
