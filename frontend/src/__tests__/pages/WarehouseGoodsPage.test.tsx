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

afterEach(() => vi.restoreAllMocks());

describe('Warehouse goods', () => {
  it('shows stock, opens detail and prevents archiving remaining stock', async () => {
    const user = userEvent.setup();
    mount(<WarehouseGoodsPage />);
    await user.click(await screen.findByRole('button', { name: 'Actions: GOOD-1' }));
    expect(await screen.findByRole('menuitem', { name: 'Edit article' })).toBeEnabled();
    expect(screen.getByRole('menuitem', { name: 'Archive article' })).toBeDisabled();
    expect(screen.getByRole('menuitem', { name: 'Post movement' })).toBeEnabled();
    await user.click(screen.getByRole('menuitem', { name: 'View Details' }));
    expect(await screen.findByRole('dialog')).toHaveTextContent('Printed bracket');
    expect(screen.getByRole('button', { name: 'Archive article' })).toBeDisabled();
    expect(screen.getByText('Below minimum stock · Minimum stock: 5 C62')).toBeInTheDocument();
  });

  it('fetches and focuses the exact linked warehouse article', async () => {
    const request = vi.fn();
    server.use(http.get('*/api/v1/warehouse-articles', ({ request: req }) => {
      request(new URL(req.url).searchParams.get('article_id'));
      return HttpResponse.json({ items: [item], total: 1, offset: 0, limit: 1 });
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<MemoryRouter initialEntries={['/warehouse/stock?focus=1']}>
      <QueryClientProvider client={client}><WarehouseGoodsPage /></QueryClientProvider>
    </MemoryRouter>);
    const row = await screen.findByRole('row', { name: /GOOD-1/ });
    expect(request).toHaveBeenCalledWith('1');
    expect(row).toHaveAttribute('aria-current', 'true');
    expect(row).toHaveFocus();
  });

  it('opens both quick movements from the three-dot menu and books a free issue inline', async () => {
    const user = userEvent.setup();
    const posted = vi.spyOn(warehouseArticlesApi, 'addLedger').mockResolvedValue({ id: 8 } as never);
    mount(<WarehouseGoodsPage />);
    const menu = await screen.findByRole('button', { name: 'Actions: GOOD-1' });
    expect(within(menu.closest('td')!).getAllByRole('button')).toEqual([menu]);
    await user.click(menu);
    const receipt = await screen.findByRole('menuitem', { name: 'Receipt' });
    await user.click(receipt);
    expect(screen.getByRole('heading', { name: 'Receipt · GOOD-1' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(menu).toHaveFocus();

    await user.click(menu);
    await user.click(await screen.findByRole('menuitem', { name: 'Free issue' }));
    const bookingRow = screen.getByLabelText(/Quantity \(C62\)/).closest('tr')!;
    expect(within(bookingRow).getByLabelText(/Quantity/)).toHaveFocus();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await user.type(within(bookingRow).getByLabelText(/Quantity/), '2');
    await user.click(within(bookingRow).getByRole('combobox', { name: 'Location' }));
    await user.click(await screen.findByRole('option', { name: 'Rack A' }));
    await user.type(within(bookingRow).getByLabelText(/Reason/), 'Customer pickup');
    await user.click(within(bookingRow).getByRole('button', { name: 'Post movement' }));
    await waitFor(() => expect(posted).toHaveBeenCalledWith(1, {
      entry_kind: 'issue', quantity: '2', location_id: 1, reason: 'Customer pickup',
      idempotency_key: expect.any(String),
    }));
    expect(await within(bookingRow).findByText('Stock movement saved.')).toBeVisible();
    await user.click(within(bookingRow).getByRole('button', { name: 'Cancel' }));
    expect(menu).toHaveFocus();
    expect(menu).toBeEnabled();
  });

  it('hides mutations for readers and refuses to fetch without read permission', async () => {
    permissions.clear(); permissions.add('inventory:read');
    const first = mount(<WarehouseGoodsPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Actions: GOOD-1' }));
    expect(await screen.findByRole('menuitem', { name: 'View Details' })).toBeEnabled();
    for (const name of ['Edit article', 'Duplicate', 'Post movement', 'Receipt', 'Free issue', 'Archive article']) {
      expect(screen.queryByRole('menuitem', { name })).not.toBeInTheDocument();
    }
    expect(screen.queryByRole('button', { name: 'New article' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Receipt: GOOD-1' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Free issue: GOOD-1' })).not.toBeInTheDocument();
    first.unmount();
    permissions.clear();
    let requested = false;
    server.use(http.get('*/api/v1/warehouse-articles', () => { requested = true; return HttpResponse.json({ items: [] }); }));
    mount(<WarehouseGoodsPage />);
    expect(screen.getByRole('alert')).toHaveTextContent('permission');
    expect(requested).toBe(false);
  });

  it('creates a duplicate with a new SKU and no project references', async () => {
    const create = vi.fn();
    const source = { ...item, project_id: 42, calculation_revision_id: 9 };
    server.use(
      http.get('*/api/v1/warehouse-articles', () => HttpResponse.json({ items: [source], total: 1, offset: 0, limit: 50 })),
      http.post('*/api/v1/warehouse-articles', async ({ request }) => {
        create(await request.json());
        return HttpResponse.json({ ...item, sku: 'GOOD-2', id: 2 }, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    mount(<WarehouseGoodsPage />);
    await user.click(await screen.findByRole('button', { name: 'Actions: GOOD-1' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Duplicate' }));
    const dialog = await screen.findByRole('dialog', { name: 'Duplicate' });
    expect(within(dialog).getByLabelText(/Article number/)).toHaveValue('');
    expect(within(dialog).getByLabelText(/^Name/)).toHaveValue(item.name);
    expect(create).not.toHaveBeenCalled();
    await user.type(within(dialog).getByLabelText(/Article number/), 'GOOD-2');
    await user.click(within(dialog).getByRole('button', { name: 'Save', exact: true }));
    await waitFor(() => expect(create).toHaveBeenCalledWith(expect.objectContaining({
      sku: 'GOOD-2', sale_price: item.sale_price, project_id: null, calculation_revision_id: null,
    })));
    expect(create.mock.calls[0][0]).not.toHaveProperty('balance');
    expect(create.mock.calls[0][0]).not.toHaveProperty('version');
  });

  it('archives and restores a zero-stock article using its current version', async () => {
    let current = { ...item, balance: { physical: '0', reserved: '0', available: '0', is_low_stock: true } };
    const archive = vi.fn();
    const restore = vi.fn();
    server.use(
      http.get('*/api/v1/warehouse-articles', ({ request }) => {
        const active = new URL(request.url).searchParams.get('active');
        const items = !active || (active === 'true') === current.is_active ? [current] : [];
        return HttpResponse.json({ items, total: items.length, offset: 0, limit: 50 });
      }),
      http.delete('*/api/v1/warehouse-articles/1', ({ request }) => {
        archive(new URL(request.url).searchParams.get('version'));
        current = { ...current, is_active: false, version: 2 };
        return HttpResponse.json(current);
      }),
      http.patch('*/api/v1/warehouse-articles/1', async ({ request }) => {
        restore(await request.json());
        current = { ...current, is_active: true, version: 3 };
        return HttpResponse.json(current);
      }),
    );
    const user = userEvent.setup();
    mount(<WarehouseGoodsPage />);
    await user.click(await screen.findByRole('button', { name: 'Actions: GOOD-1' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Archive article' }));
    const confirm = await screen.findByRole('dialog', { name: 'Archive article' });
    expect(archive).not.toHaveBeenCalled();
    await user.click(within(confirm).getByRole('button', { name: 'Archive article' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(archive).toHaveBeenCalledWith('1');
    await user.click(screen.getByRole('button', { name: 'Archived', exact: true }));
    await user.click(await screen.findByRole('button', { name: 'Actions: GOOD-1' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Restore article' }));
    const restoreDialog = await screen.findByRole('dialog', { name: 'Restore article' });
    await user.click(within(restoreDialog).getByRole('button', { name: 'Restore article' }));
    await waitFor(() => expect(restore).toHaveBeenCalledWith({ is_active: true, version: 2 }));
  });

  it('debounces input and starts on the first page after changing the page size', async () => {
    const requests = vi.fn();
    server.use(http.get('*/api/v1/warehouse-articles', ({ request }) => {
      const params = new URL(request.url).searchParams;
      requests(params.get('q'), params.get('limit'), params.get('offset'));
      return HttpResponse.json({ items: [item], total: 70, offset: Number(params.get('offset')), limit: Number(params.get('limit')) });
    }));
    const user = userEvent.setup();
    mount(<WarehouseGoodsPage />);
    await user.click(await screen.findByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(requests).toHaveBeenCalledWith('', '50', '50'));
    await user.click(screen.getByRole('combobox', { name: 'Rows' }));
    await user.click(screen.getByRole('option', { name: '25' }));
    await waitFor(() => expect(requests).toHaveBeenCalledWith('', '25', '0'));
    expect(localStorage.setItem).toHaveBeenCalledWith('printops-warehouse-goods-pageSize', '25');

    requests.mockClear();
    await user.type(screen.getByRole('searchbox'), 'printed');
    expect(requests).not.toHaveBeenCalled();
    await waitFor(() => expect(requests).toHaveBeenCalledExactlyOnceWith('printed', '25', '0'));
    await user.click(screen.getByRole('button', { name: 'Clear search' }));
    expect(screen.getByRole('searchbox')).toHaveValue('');
  });

  it('sorts the server-side result from the first page and cycles the sort direction', async () => {
    const requests = vi.fn();
    const preferenceKey = 'printops-warehouse-goods-sort';
    vi.mocked(localStorage.removeItem).mockClear();
    server.use(http.get('*/api/v1/warehouse-articles', ({ request }) => {
      const params = new URL(request.url).searchParams;
      requests(params.get('offset'), params.get('sort_by'), params.get('sort_dir'));
      return HttpResponse.json({ items: [item], total: 51, offset: Number(params.get('offset')), limit: 50 });
    }));
    const user = userEvent.setup();
    mount(<WarehouseGoodsPage />);
    await user.click(await screen.findByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(requests).toHaveBeenCalledWith('50', null, null));

    const header = await screen.findByRole('columnheader', { name: 'Available' });
    const button = within(header).getByRole('button');
    await user.click(button);
    await waitFor(() => expect(requests).toHaveBeenCalledWith('0', 'available', 'asc'));
    expect(header).toHaveAttribute('aria-sort', 'ascending');
    expect(button).toHaveFocus();
    await user.keyboard('{Enter}');
    await waitFor(() => expect(requests).toHaveBeenCalledWith('0', 'available', 'desc'));
    expect(header).toHaveAttribute('aria-sort', 'descending');
    await user.keyboard('{Enter}');
    await waitFor(() => expect(header).not.toHaveAttribute('aria-sort'));
    expect(localStorage.removeItem).toHaveBeenCalledWith(preferenceKey);
  });

  it('uses warehouse filters before pagination and retains the result when switching to cards', async () => {
    const requests = vi.fn();
    server.use(
      http.get('*/api/v1/inventory/locations', () => HttpResponse.json([{ id: 3, name: 'Rack C' }])),
      http.get('*/api/v1/warehouse-articles', ({ request }) => {
        const params = new URL(request.url).searchParams;
        requests(params.get('usage'), params.get('location_id'), params.get('offset'));
        return HttpResponse.json({ items: [item], total: 5, offset: 0, limit: 50 });
      }),
    );
    const user = userEvent.setup();
    mount(<WarehouseGoodsPage />);
    expect(await screen.findByText('5 articles')).toBeInTheDocument();
    await user.click(within(screen.getByRole('group', { name: 'Used' })).getByRole('button', { name: 'Used', exact: true }));
    await user.click(screen.getByRole('combobox', { name: 'Location' }));
    await user.click(await screen.findByRole('option', { name: 'Rack C' }));
    await waitFor(() => expect(requests).toHaveBeenCalledWith('used', '3', '0'));
    await user.click(screen.getByRole('button', { name: 'Cards' }));
    expect(screen.queryByRole('table')).toBeNull();
    expect(within(screen.getByRole('article')).getByRole('button', { name: 'Actions: GOOD-1' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    await waitFor(() => expect(requests).toHaveBeenCalledWith(null, null, '0'));
  });

  it('opens the editor from a row cell and confirms stock from the separate selection', async () => {
    const user = userEvent.setup();
    const checked = vi.fn();
    server.use(
      http.post('*/api/v1/warehouse-articles/stock-check', async ({ request }) => {
        checked(await request.json());
        return HttpResponse.json({ stock_checked_at: '2026-11-27T10:00:00Z' });
      }),
    );
    mount(<WarehouseGoodsPage />);
    const row = await screen.findByRole('row', { name: /Printed bracket/ });
    await user.click(within(row).getByRole('cell', { name: '1' }));
    expect(await screen.findByRole('dialog', { name: 'Edit article' })).toBeInTheDocument();
    await user.keyboard('{Escape}');

    await user.click(within(row).getByRole('checkbox'));
    expect(screen.queryByRole('dialog')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Confirm stocktake' }));
    await user.click(within(screen.getByRole('dialog', { name: 'Confirm stocktake' })).getByRole('button', { name: 'Confirm', exact: true }));
    await waitFor(() => expect(checked).toHaveBeenCalledWith({ ids: [1] }));
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
    const save = screen.getByRole<HTMLButtonElement>('button', { name: 'Save', exact: true });
    const articleForm = screen.getByLabelText(/Article number/).closest('form');
    expect(save.form).toBe(articleForm);
    expect(articleForm).not.toContainElement(save);
    await user.click(save);

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

  it('uses the material ledger for linked goods and omits bookings for services', async () => {
    const user = userEvent.setup();
    const posted = vi.fn();
    const ownLedger = vi.spyOn(warehouseArticlesApi, 'addLedger');
    const linked = { ...item, kind: 'trade', stock_source: 'material', small_part_id: 42 };
    const service = { ...item, id: 2, sku: 'SERVICE-2', kind: 'service', stock_source: 'none' };
    server.use(
      http.get('*/api/v1/warehouse-articles', () => HttpResponse.json({ items: [linked, service], total: 2, offset: 0, limit: 50 })),
      http.get('*/api/v1/small-parts/42', () => HttpResponse.json({
        id: 42, sku: 'MATERIAL-42', name: 'Material bracket', default_consumption_reason: 'Workshop',
        is_active: true, unit_code: 'C62', unit: { decimal_places: 0, label: 'Piece' },
      })),
      http.post('*/api/v1/small-parts/42/ledger', async ({ request }) => {
        posted(await request.json());
        return HttpResponse.json({ id: 1 }, { status: 201 });
      }),
    );
    mount(<WarehouseGoodsPage />);
    await user.click(await screen.findByRole('button', { name: 'Actions: SERVICE-2' }));
    expect(await screen.findByRole('menuitem', { name: 'View Details' })).toBeEnabled();
    expect(screen.queryByRole('menuitem', { name: /^(Receipt|Free issue)$/ })).not.toBeInTheDocument();
    await user.keyboard('{Escape}');
    await user.click(screen.getByRole('button', { name: 'Actions: GOOD-1' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Free issue' }));
    const dialog = await screen.findByRole('dialog', { name: 'Free issue · MATERIAL-42' });
    await user.type(within(dialog).getByRole('spinbutton', { name: 'Quantity' }), '2');
    await user.click(within(dialog).getByRole('button', { name: 'Save movement' }));
    await waitFor(() => expect(posted).toHaveBeenCalledWith(expect.objectContaining({ entry_kind: 'issue', quantity: '2' })));
    expect(ownLedger).not.toHaveBeenCalled();
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
