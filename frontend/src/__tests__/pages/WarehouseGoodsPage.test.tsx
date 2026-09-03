import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { WarehouseArticle } from '../../api/client/warehouse-articles';
import { WarehouseGoodsPage } from '../../pages/WarehouseGoodsPage';
import { WarehouseStockPanel } from '../../components/warehouse/WarehouseStockPanel';
import { WarehouseArticleEditor } from '../../components/warehouse/WarehouseArticleEditor';
import i18n from '../../i18n';
import { server } from '../mocks/server';

const permissions = vi.hoisted(() => new Set(['inventory:read', 'inventory:create', 'inventory:update', 'inventory:delete']));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ hasPermission: (permission: string) => permissions.has(permission) }) }));
const item: WarehouseArticle = {
  id: 1, sku: 'GOOD-1', name: 'Printed bracket', kind: 'finished', unit_code: 'C62', description: null,
  stock_source: 'own', small_part_id: null, project_id: null, calculation_revision_id: null,
  sale_price: '12.5', unit_cost: '0', tax_rate: '19', minimum_stock: '5', is_active: true,
  version: 1, has_history: true, created_at: '2026-08-31T10:00:00Z', updated_at: '2026-08-31T10:00:00Z',
  balance: { physical: '10', reserved: '7', available: '3', is_low_stock: true },
  locations: [{ location_id: 1, location_name: 'Rack A', physical: '10', reserved: '7', available: '3', is_low_stock: false }],
};

function mount(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<MemoryRouter><QueryClientProvider client={client}>{children}</QueryClientProvider></MemoryRouter>);
}

beforeEach(async () => {
  await i18n.changeLanguage('en');
  permissions.clear();
  ['inventory:read', 'inventory:create', 'inventory:update', 'inventory:delete'].forEach((permission) => permissions.add(permission));
  server.use(
    http.get('*/api/v1/warehouse-articles', () => HttpResponse.json({ items: [item], total: 1, offset: 0, limit: 50 })),
    http.get('*/api/v1/warehouse-articles/1', () => HttpResponse.json(item)),
    http.get('*/api/v1/warehouse-articles/1/ledger', () => HttpResponse.json([])),
    http.get('*/api/v1/warehouse-articles/1/reservations', () => HttpResponse.json([])),
    http.get('*/api/v1/inventory/locations', () => HttpResponse.json([{ id: 1, name: 'Rack A' }, { id: 2, name: 'Rack B' }])),
    http.get('*/api/v1/small-parts/settings/units', () => HttpResponse.json([{ code: 'C62', label: 'Piece', decimal_places: 0, is_active: true }])),
  );
});

describe('Warehouse goods', () => {
  it('shows stock, opens detail and prevents archiving remaining stock', async () => {
    const user = userEvent.setup();
    mount(<WarehouseGoodsPage />);
    await user.click(await screen.findByRole('button', { name: 'GOOD-1' }));
    expect(await screen.findByRole('dialog')).toHaveTextContent('Printed bracket');
    expect(screen.getByRole('button', { name: 'Archive article' })).toBeDisabled();
    expect(screen.getByText('Below minimum stock · Minimum stock: 5 C62')).toBeInTheDocument();
  });

  it('hides mutations for readers and refuses to fetch without read permission', async () => {
    permissions.clear(); permissions.add('inventory:read');
    const first = mount(<WarehouseGoodsPage />);
    expect(await screen.findByRole('button', { name: 'GOOD-1' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'New article' })).not.toBeInTheDocument();
    first.unmount();
    permissions.clear();
    let requested = false;
    server.use(http.get('*/api/v1/warehouse-articles', () => { requested = true; return HttpResponse.json({ items: [] }); }));
    mount(<WarehouseGoodsPage />);
    expect(screen.getByRole('alert')).toHaveTextContent('permission');
    expect(requested).toBe(false);
  });

  it('shows fetch failures distinctly from an empty list', async () => {
    server.use(http.get('*/api/v1/warehouse-articles', () => HttpResponse.json({ detail: 'Unavailable' }, { status: 503 })));
    mount(<WarehouseGoodsPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load');
    expect(screen.queryByText('No articles match these filters.')).not.toBeInTheDocument();
  });

  it('retains the same booking key when retrying an uncertain request', async () => {
    const user = userEvent.setup();
    const keys: string[] = [];
    server.use(http.post('*/api/v1/warehouse-articles/1/ledger', async ({ request }) => {
      const payload = await request.json() as { idempotency_key: string; quantity: string };
      keys.push(payload.idempotency_key);
      expect(payload.quantity).toBe('2');
      if (keys.length === 1) return HttpResponse.json({ detail: 'Retry this request' }, { status: 503 });
      return HttpResponse.json({ id: 8 });
    }));
    mount(<WarehouseStockPanel article={item} canBook />);
    await user.click(await screen.findByRole('combobox', { name: 'Location' }));
    await user.click(await screen.findByRole('option', { name: 'Rack A' }));
    await user.type(screen.getByLabelText(/Quantity \(C62\)/), '2');
    await user.type(screen.getByLabelText(/Reason/), 'Received');
    await user.click(screen.getByRole('button', { name: 'Post movement' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Retry this request');
    await user.click(screen.getByRole('button', { name: 'Post movement' }));
    await waitFor(() => expect(keys).toHaveLength(2));
    expect(keys[0]).toBe(keys[1]);
    await waitFor(() => expect(screen.getByLabelText(/Reason/)).toHaveValue(''));
  });

  it('creates services with no stock and does not copy selling price to cost', async () => {
    const user = userEvent.setup();
    let submitted: Record<string, unknown> | null = null;
    server.use(http.post('*/api/v1/warehouse-articles', async ({ request }) => { submitted = await request.json() as Record<string, unknown>; return HttpResponse.json(item); }));
    mount(<WarehouseArticleEditor article={null} onClose={vi.fn()} />);
    await user.type(screen.getByLabelText(/Article number/), 'SVC-1');
    await user.type(screen.getByLabelText(/Name/), 'Consultation');
    await user.click(screen.getByRole('combobox', { name: 'Article kind' }));
    await user.click(screen.getByRole('option', { name: 'Service' }));
    await user.click(screen.getByRole('combobox', { name: 'Local unit' }));
    await user.click(await screen.findByRole('option', { name: 'Piece (C62)' }));
    await user.clear(screen.getByLabelText(/Net selling price \(EUR\)/));
    await user.type(screen.getByLabelText(/Net selling price \(EUR\)/), '50');
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }));
    await waitFor(() => expect(submitted).toMatchObject({ kind: 'service', stock_source: 'none', sale_price: '50', unit_cost: '0', minimum_stock: '0' }));
  });

  it('routes material articles to the existing stock manager without warehouse booking controls', async () => {
    const user = userEvent.setup();
    server.use(http.get('*/api/v1/warehouse-articles/1', () => HttpResponse.json({ ...item, kind: 'trade', stock_source: 'material', small_part_id: 42 })));
    mount(<WarehouseGoodsPage />);
    await user.click(await screen.findByRole('button', { name: 'GOOD-1' }));
    expect(await screen.findByRole('link', { name: 'Open material management' })).toHaveAttribute('href', '/warehouse/parts?part=42');
    expect(screen.queryByRole('button', { name: 'Post movement' })).not.toBeInTheDocument();
  });
});
