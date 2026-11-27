import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { warehouseArticlesApi, type WarehouseArticle } from '../../api/client/warehouse-articles';
import { WarehouseGoodsPage } from '../../pages/WarehouseGoodsPage';
import { WarehouseStockPanel } from '../../components/warehouse/WarehouseStockPanel';
import { WarehouseArticleEditor } from '../../components/warehouse/WarehouseArticleEditor';
import { WarehouseArticleDetail } from '../../components/warehouse/WarehouseArticleDetail';
import { warehouseQuantity } from '../../components/warehouse/warehouseGoodsCopy';
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function mount(children: React.ReactNode, client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })) {
  return { ...render(<MemoryRouter><QueryClientProvider client={client}>{children}</QueryClientProvider></MemoryRouter>), client };
}

// The global setup replaces localStorage with no-op vi.fn()s; back them with a
// real map so persistence (sort state, column config, page size) can be asserted.
const storage = new Map<string, string>();

beforeEach(async () => {
  await i18n.changeLanguage('en');
  storage.clear();
  vi.mocked(localStorage.getItem).mockImplementation((key) => storage.get(key) ?? null);
  vi.mocked(localStorage.setItem).mockImplementation((key, value) => { storage.set(key, String(value)); });
  vi.mocked(localStorage.removeItem).mockImplementation((key) => { storage.delete(key); });
  vi.mocked(localStorage.clear).mockImplementation(() => storage.clear());
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

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
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

  it('retains the booking command and idempotency key after an uncertain error and remount', async () => {
    const user = userEvent.setup();
    const addLedger = vi.spyOn(warehouseArticlesApi, 'addLedger')
      .mockRejectedValueOnce(new Error('Response lost'))
      .mockResolvedValueOnce({ id: 8 } as never);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const first = mount(<WarehouseStockPanel article={item} canBook />, client);
    await user.click(await screen.findByRole('combobox', { name: 'Location' }));
    await user.click(await screen.findByRole('option', { name: 'Rack A' }));
    await user.type(screen.getByLabelText(/Quantity \(C62\)/), '2');
    await user.type(screen.getByLabelText(/Reason/), 'Received after timeout');
    await user.click(screen.getByRole('button', { name: 'Post movement' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Response lost');
    const firstKey = addLedger.mock.calls[0][1].idempotency_key;
    first.unmount();

    mount(<WarehouseStockPanel article={item} canBook />, client);
    expect(await screen.findByLabelText(/Quantity \(C62\)/)).toHaveValue(2);
    expect(screen.getByLabelText(/Reason/)).toHaveValue('Received after timeout');
    expect(screen.getByLabelText(/Quantity \(C62\)/)).toBeDisabled();
    expect(screen.getByLabelText(/Reason/)).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Post movement' }));
    await waitFor(() => expect(addLedger).toHaveBeenCalledTimes(2));
    expect(addLedger.mock.calls[1][1].idempotency_key).toBe(firstKey);
  });

  it('can retry an uncertain release after the reservation disappears from the open list', async () => {
    const user = userEvent.setup();
    let released = false;
    server.use(http.get('*/api/v1/warehouse-articles/1/reservations', () => HttpResponse.json(
      released ? [] : [{ id: 9, location_id: 1, remaining: '2', order_id: null }],
    )));
    const addLedger = vi.spyOn(warehouseArticlesApi, 'addLedger')
      .mockImplementationOnce(async () => { released = true; throw new Error('Response lost'); })
      .mockResolvedValueOnce({ id: 10 } as never);
    const first = mount(<WarehouseStockPanel article={item} canBook />);
    await user.click(screen.getByRole('combobox', { name: 'Stock movement' }));
    await user.click(screen.getByRole('option', { name: 'Release reservation', exact: true }));
    await user.click(screen.getByRole('combobox', { name: 'Open reservation' }));
    await user.click(await screen.findByRole('option', { name: /#9/ }));
    await user.type(screen.getByLabelText(/Quantity/), '2');
    await user.type(screen.getByLabelText(/Reason/), 'Release completed order');
    await user.click(screen.getByRole('button', { name: 'Post movement' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Response lost');
    const submitted = addLedger.mock.calls[0][1];
    first.unmount();
    await first.client.invalidateQueries({ queryKey: ['warehouse-articles', 1, 'reservations'] });
    mount(<WarehouseStockPanel article={item} canBook />, first.client);
    await waitFor(() => expect(first.client.getQueryData(['warehouse-articles', 1, 'reservations'])).toEqual([]));
    expect(screen.getByRole('button', { name: 'Post movement' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Post movement' }));
    await waitFor(() => expect(addLedger).toHaveBeenCalledTimes(2));
    expect(addLedger.mock.calls[1][1]).toEqual(submitted);
  });

  it('blocks stock-dialog closing, edits, and duplicate submission while a movement is pending', async () => {
    const user = userEvent.setup();
    const response = deferred<never>();
    const addLedger = vi.spyOn(warehouseArticlesApi, 'addLedger').mockReturnValue(response.promise);
    const onClose = vi.fn();
    mount(<WarehouseArticleDetail id={1} onClose={onClose} />);
    await user.click(await screen.findByRole('combobox', { name: 'Location' }));
    await user.click(await screen.findByRole('option', { name: 'Rack A' }));
    await user.type(screen.getByLabelText(/Quantity \(C62\)/), '2');
    await user.type(screen.getByLabelText(/Reason/), 'Delayed receipt');
    await user.click(screen.getByRole('button', { name: 'Post movement' }));

    const dialog = screen.getByRole('dialog');
    expect(screen.getByRole('button', { name: 'Close' })).toBeDisabled();
    expect(screen.getByLabelText(/Quantity \(C62\)/)).toBeDisabled();
    fireEvent.keyDown(dialog, { key: 'Escape' });
    fireEvent.pointerDown(dialog.parentElement!);
    fireEvent.submit(screen.getByLabelText(/Reason/).closest('form')!);
    expect(onClose).not.toHaveBeenCalled();
    expect(addLedger).toHaveBeenCalledTimes(1);
  });

  it('blocks every editor close path, edits, and duplicate submission while saving', async () => {
    const user = userEvent.setup();
    const response = deferred<WarehouseArticle>();
    const create = vi.spyOn(warehouseArticlesApi, 'create').mockReturnValue(response.promise);
    const onClose = vi.fn();
    mount(<WarehouseArticleEditor article={null} onClose={onClose} />);
    await user.type(screen.getByLabelText(/Article number/), 'DELAYED-1');
    await user.type(screen.getByLabelText(/^Name/), 'Delayed article');
    await user.click(screen.getByRole('combobox', { name: 'Local unit' }));
    await user.click(await screen.findByRole('option', { name: 'Piece (C62)' }));
    await user.click(screen.getByRole('button', { name: 'Save', exact: true }));

    const dialog = screen.getByRole('dialog');
    expect(screen.getByLabelText(/Article number/)).toBeDisabled();
    fireEvent.keyDown(dialog, { key: 'Escape' });
    fireEvent.pointerDown(dialog.parentElement!);
    fireEvent.submit(screen.getByLabelText(/Article number/).closest('form')!);
    expect(onClose).not.toHaveBeenCalled();
    expect(create).toHaveBeenCalledTimes(1);
    await act(async () => response.resolve(item));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it('formats maximal Decimal quantities without Number precision loss', () => {
    expect(warehouseQuantity('999999999999.999999', 'en-US')).toBe('999,999,999,999.999999');
    expect(warehouseQuantity('-123456789012.123456', 'de-DE')).toBe('-123.456.789.012,123456');
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

describe('Warehouse goods list controls', () => {
  function captureListParams() {
    const seen: Array<{ q: string | null; sort_by: string | null; sort_dir: string | null; limit: string | null }> = [];
    server.use(http.get('*/api/v1/warehouse-articles', ({ request }) => {
      const url = new URL(request.url);
      seen.push({
        q: url.searchParams.get('q'),
        sort_by: url.searchParams.get('sort_by'),
        sort_dir: url.searchParams.get('sort_dir'),
        limit: url.searchParams.get('limit'),
      });
      return HttpResponse.json({ items: [item], total: 1, offset: 0, limit: Number(url.searchParams.get('limit') ?? 50) });
    }));
    return seen;
  }

  it('toggles aria-sort and sends sort_by/sort_dir when clicking a sortable header', async () => {
    const seen = captureListParams();
    const user = userEvent.setup();
    mount(<WarehouseGoodsPage />);
    // Re-query before every interaction: the header node is re-created on each render.
    const skuHeader = () => screen.getByRole('columnheader', { name: /Article number/ });
    expect(await screen.findByRole('columnheader', { name: /Article number/ })).toHaveAttribute('aria-sort', 'none');
    expect(seen.at(-1)).toMatchObject({ sort_by: null, sort_dir: null });
    await user.click(within(skuHeader()).getByRole('button'));
    await waitFor(() => expect(seen.at(-1)).toMatchObject({ sort_by: 'sku', sort_dir: 'asc' }));
    expect(skuHeader()).toHaveAttribute('aria-sort', 'ascending');
    await user.click(within(skuHeader()).getByRole('button'));
    await waitFor(() => expect(seen.at(-1)).toMatchObject({ sort_by: 'sku', sort_dir: 'desc' }));
    expect(skuHeader()).toHaveAttribute('aria-sort', 'descending');
    // Third click clears the sort again.
    await user.click(within(skuHeader()).getByRole('button'));
    await waitFor(() => expect(seen.at(-1)?.sort_by).toBeNull());
    expect(skuHeader()).toHaveAttribute('aria-sort', 'none');
    expect(localStorage.getItem('printops-warehouse-goods-sort')).toBeNull();
  });

  it('maps the minimum column to the minimum_stock sort parameter', async () => {
    const seen = captureListParams();
    const user = userEvent.setup();
    mount(<WarehouseGoodsPage />);
    const header = await screen.findByRole('columnheader', { name: /Minimum stock/ });
    await user.click(within(header).getByRole('button'));
    await waitFor(() => expect(seen.at(-1)).toMatchObject({ sort_by: 'minimum_stock', sort_dir: 'asc' }));
  });

  it('debounces search typing into one request with the final query and clears via the X button', async () => {
    const seen = captureListParams();
    mount(<WarehouseGoodsPage />);
    await screen.findByRole('button', { name: 'GOOD-1' });
    expect(seen.map((entry) => entry.q)).toEqual(['']);
    vi.useFakeTimers();
    try {
      const field = screen.getByLabelText(/Search articles/);
      fireEvent.change(field, { target: { value: 'b' } });
      fireEvent.change(field, { target: { value: 'br' } });
      fireEvent.change(field, { target: { value: 'bracket' } });
      // No request per keystroke while the debounce timer is pending.
      expect(seen).toHaveLength(1);
      await act(async () => { vi.advanceTimersByTime(400); });
      await act(async () => {});
      expect(seen.map((entry) => entry.q)).toEqual(['', 'bracket']);
      fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
      await act(async () => {});
      expect(seen.at(-1)?.q).toBe('');
      expect(field).toHaveValue('');
    } finally {
      vi.useRealTimers();
    }
  });

  it('opens the column config modal, hides a column and persists the choice', async () => {
    const user = userEvent.setup();
    mount(<WarehouseGoodsPage />);
    await screen.findByRole('button', { name: 'GOOD-1' });
    await user.click(screen.getByRole('button', { name: 'Columns' }));
    expect(await screen.findByText('Configure Columns')).toBeInTheDocument();
    const reservedLabel = screen.getAllByText('Reserved').find((element) => element.tagName === 'SPAN')!;
    await user.click(within(reservedLabel.closest('div')!).getByRole('button', { name: 'Hide column' }));
    await user.click(screen.getByRole('button', { name: 'Apply Changes' }));
    const stored = JSON.parse(localStorage.getItem('printops-warehouse-goods-columns') ?? '[]') as Array<{ id: string; visible: boolean }>;
    expect(stored).toEqual(expect.arrayContaining([expect.objectContaining({ id: 'reserved', visible: false })]));
    expect(screen.queryByRole('columnheader', { name: /Reserved/ })).not.toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Article number/ })).toBeInTheDocument();
  });

  it('sends the selected page size as limit and persists it', async () => {
    const seen = captureListParams();
    const user = userEvent.setup();
    mount(<WarehouseGoodsPage />);
    await screen.findByRole('button', { name: 'GOOD-1' });
    expect(seen.at(-1)?.limit).toBe('50');
    await user.click(screen.getByRole('combobox', { name: /Rows/ }));
    await user.click(await screen.findByRole('option', { name: '100' }));
    await waitFor(() => expect(seen.at(-1)?.limit).toBe('100'));
    expect(localStorage.getItem('printops-warehouse-goods-pageSize')).toBe('100');
  });
});

it('renders Dutch warehouse booking labels and posts the unchanged ledger quantity', async () => {
  await i18n.changeLanguage('nl');
  const posted = vi.spyOn(warehouseArticlesApi, 'addLedger').mockResolvedValue({ id: 8 } as never);
  const user = userEvent.setup();
  mount(<WarehouseStockPanel article={item} canBook />);
  await user.click(await screen.findByRole('combobox', { name: 'Locatie' }));
  await user.click(await screen.findByRole('option', { name: 'Rack A' }));
  await user.type(screen.getByLabelText(/Hoeveelheid/), '2');
  await user.type(screen.getByLabelText(/Reden/), 'Ontvangen levering');
  await user.click(screen.getByRole('button', { name: 'Mutatie boeken' }));
  await waitFor(() => expect(posted).toHaveBeenCalledWith(1, expect.objectContaining({
    quantity: '2', reason: 'Ontvangen levering', entry_kind: 'receipt', location_id: 1,
  })));
});
