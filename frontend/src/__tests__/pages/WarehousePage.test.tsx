import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '../../i18n';
import { WarehousePage } from '../../pages/WarehousePage';
import { server } from '../mocks/server';

const permissions = vi.hoisted(() => new Set<string>(['inventory:read']));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ hasPermission: (permission: string) => permissions.has(permission) }) }));

// The new warehousePage keys (stats/reorder, updated area bodies) are integrated
// centrally into the locale files; until then inject them into the en bundle.
const warehousePageBundle = {
  orders: {
    runtimeDomain: {
      warehousePage: {
        areas: {
          parts: { body: 'Purchased parts, hardware, packaging and consumables — with live stock, reservations and reorder points.' },
          stock: { body: 'Finished and trade goods with stock movements, reservations and reorder needs.' },
        },
        stats: { activeItems: 'Active items', reserved: 'Reserved', stockValue: 'Stock value' },
        reorder: { title: 'Reorder needs', items: 'items below reorder point', open: 'Open reorder list' },
      },
    },
  },
};

const spool = (id: number, labelWeight: number, weightUsed: number, archived = false) => ({
  id,
  archived_at: archived ? '2026-01-01T00:00:00Z' : null,
  label_weight: labelWeight,
  weight_used: weightUsed,
});

// 5 active spools, 2 of them low stock, 1900 g remaining in total.
const spools = [
  spool(1, 1000, 850),
  spool(2, 1000, 900),
  spool(3, 1000, 500),
  spool(4, 500, 100),
  spool(5, 1000, 250),
  spool(6, 1000, 0, true),
];

const part = (id: number, physical: string, reserved: string, unitCost: string, low: boolean) => ({
  id,
  sku: `P-${id}`,
  name: `Part ${id}`,
  description: null,
  search_terms: null,
  category_id: null,
  location_id: null,
  minimum_stock: '1',
  unit_cost: unitCost,
  supplier_reference: null,
  default_consumption_reason: 'Produktion',
  internal_notes: null,
  is_active: true,
  preferred_offer: null,
  category: null,
  unit: { code: 'C62', label: 'Piece', decimal_places: 0, is_active: true },
  balance: { physical, reserved, available: '0', is_low_stock: low },
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
});

// 7 active parts, 4 low stock, 6.5 reserved, stock value 10*1 + 20*5.67 = 123.40.
const parts = [
  part(1, '10', '2.5', '1.00', false),
  part(2, '20', '4', '5.67', true),
  part(3, '1', '0', '0', true),
  part(4, '1', '0', '0', true),
  part(5, '1', '0', '0', true),
  part(6, '1', '0', '0', false),
  part(7, '1', '0', '0', false),
];

const article = (id: number, physical: string, reserved: string, unitCost: string, low: boolean) => ({
  id,
  sku: `A-${id}`,
  name: `Article ${id}`,
  kind: 'finished',
  unit_code: 'C62',
  description: null,
  stock_source: 'own',
  small_part_id: null,
  project_id: null,
  calculation_revision_id: null,
  sale_price: '0',
  unit_cost: unitCost,
  tax_rate: '19',
  minimum_stock: '1',
  is_active: true,
  version: 1,
  has_history: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  balance: { physical, reserved, available: '0', is_low_stock: low },
  locations: [],
});

// 9 active articles, 6 low stock, 3.25 reserved, stock value 5*9 = 45.
const articles = [
  article(1, '5', '1.25', '9', true),
  article(2, '10', '2', '0', true),
  article(3, '1', '0', '0', true),
  article(4, '1', '0', '0', true),
  article(5, '1', '0', '0', true),
  article(6, '1', '0', '0', true),
  article(7, '1', '0', '0', false),
  article(8, '1', '0', '0', false),
  article(9, '1', '0', '0', false),
];

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <WarehousePage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(async () => {
  await i18n.changeLanguage('en');
  i18n.addResourceBundle('en', 'translation', warehousePageBundle, true, true);
  permissions.clear();
  permissions.add('inventory:read');
  server.use(
    http.get('*/api/v1/inventory/spools', () => HttpResponse.json(spools)),
    http.get('*/api/v1/small-parts', ({ request }) => {
      const url = new URL(request.url);
      const lowStock = url.searchParams.get('low_stock') === 'true';
      const offset = Number(url.searchParams.get('offset') ?? '0');
      const limit = Number(url.searchParams.get('limit') ?? '50');
      const matching = lowStock ? parts.filter((item) => item.balance.is_low_stock) : parts;
      return HttpResponse.json({ items: matching.slice(offset, offset + limit), total: matching.length, limit, offset });
    }),
    http.get('*/api/v1/warehouse-articles', ({ request }) => {
      const url = new URL(request.url);
      const lowStock = url.searchParams.get('low_stock') === 'true';
      const offset = Number(url.searchParams.get('offset') ?? '0');
      const limit = Number(url.searchParams.get('limit') ?? '50');
      const matching = lowStock ? articles.filter((item) => item.balance.is_low_stock) : articles;
      return HttpResponse.json({ items: matching.slice(offset, offset + limit), total: matching.length, limit, offset });
    }),
  );
});

afterEach(() => vi.restoreAllMocks());

describe('WarehousePage overview', () => {
  it('shows live filament, parts and stock metrics without planned badges and links to reorder', async () => {
    mount();

    // No "planned" badge anywhere (en + de label).
    expect(screen.queryByText('Planned')).not.toBeInTheDocument();
    expect(screen.queryByText('Geplant')).not.toBeInTheDocument();

    // All three area tiles are rendered with their updated body copy.
    expect(screen.getByRole('heading', { name: 'Filament stock' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Material' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Stock position' })).toBeInTheDocument();
    expect(await screen.findByText(/live stock, reservations and reorder points/)).toBeInTheDocument();
    expect(screen.getByText(/stock movements, reservations and reorder needs/)).toBeInTheDocument();

    // Filament metric cards: 5 active spools, 2 low stock, 2 kg remaining.
    expect(await screen.findByText('Active spools')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('Remaining filament')).toBeInTheDocument();
    expect(screen.getByText('2 kg')).toBeInTheDocument();

    // "Low stock" labels: filament metric card plus both area tiles.
    expect(screen.getAllByText('Low stock')).toHaveLength(3);
    expect(screen.getByText('2')).toBeInTheDocument();

    // Material tile: 7 active, 4 low stock, 6.5 reserved, €123.40 stock value.
    expect((await screen.findAllByText('Active items')).length).toBe(2);
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('6.5')).toBeInTheDocument();
    expect(await screen.findByText('€123.40')).toBeInTheDocument();

    // Warenlager tile: 9 active, 6 low stock, 3.25 reserved, €45.00 stock value.
    expect(screen.getAllByText('Reserved')).toHaveLength(2);
    expect(screen.getAllByText('Stock value')).toHaveLength(2);
    expect(screen.getByText('9')).toBeInTheDocument();
    expect(screen.getByText('6')).toBeInTheDocument();
    expect(screen.getByText('3.25')).toBeInTheDocument();
    expect(await screen.findByText('€45.00')).toBeInTheDocument();

    // Prominent reorder tile links to /warehouse/reorder with the combined
    // low-stock total (4 parts + 6 articles = 10).
    const reorder = screen.getByRole('link', { name: /reorder needs/i });
    expect(reorder).toHaveAttribute('href', '/warehouse/reorder');
    expect(await within(reorder).findByText('10')).toBeInTheDocument();
    expect(within(reorder).getByText(/items below reorder point/)).toBeInTheDocument();
  });

  it('does not fetch parts or articles without inventory:read and hides their stats', async () => {
    permissions.clear();
    let partsRequested = false;
    let articlesRequested = false;
    server.use(
      http.get('*/api/v1/small-parts', () => {
        partsRequested = true;
        return HttpResponse.json({ items: [], total: 0, limit: 200, offset: 0 });
      }),
      http.get('*/api/v1/warehouse-articles', () => {
        articlesRequested = true;
        return HttpResponse.json({ items: [], total: 0, limit: 200, offset: 0 });
      }),
    );
    mount();

    // Spool metrics still load without inventory:read.
    expect(await screen.findByText('Active spools')).toBeInTheDocument();
    expect(await screen.findByText('5')).toBeInTheDocument();

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(partsRequested).toBe(false);
    expect(articlesRequested).toBe(false);

    // Parts/articles mini stats are not rendered; reorder total shows a placeholder.
    expect(screen.queryByText('Active items')).not.toBeInTheDocument();
    const reorder = screen.getByRole('link', { name: /reorder needs/i });
    expect(reorder).toHaveAttribute('href', '/warehouse/reorder');
    expect(within(reorder).getByText('–')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('Planned')).not.toBeInTheDocument());
  });
});
