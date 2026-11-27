import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SmallPart } from '../../api/smallParts';
import type { WarehouseArticle } from '../../api/client/warehouse-articles';
import { WarehouseReorderPage } from '../../pages/WarehouseReorderPage';
import i18n from '../../i18n';
import { server } from '../mocks/server';

const permissions = vi.hoisted(() => new Set(['inventory:read']));
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ hasPermission: (permission: string) => permissions.has(permission) }) }));

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
  minimum_stock: '6', balance: { physical: '5', reserved: '0', available: '5', is_low_stock: true },
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

function CurrentPath() {
  const location = useLocation();
  return <>
    <output data-testid="current-path">{location.pathname}{location.search}</output>
    <output data-testid="route-state">{JSON.stringify(location.state)}</output>
  </>;
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return { ...render(<MemoryRouter><QueryClientProvider client={client}><WarehouseReorderPage /><CurrentPath /></QueryClientProvider></MemoryRouter>), client };
}

beforeEach(async () => {
  await i18n.changeLanguage('en');
  permissions.clear();
  permissions.add('inventory:read');
  permissions.add('commercial_documents:read');
  server.use(
    http.get('*/api/v1/warehouse-articles', () => HttpResponse.json({ items: [article], total: 1, limit: 200, offset: 0 })),
    http.get('*/api/v1/small-parts', () => HttpResponse.json({ items: [part], total: 1, limit: 200, offset: 0 })),
    http.get('*/api/v1/warehouse-shopping-list', () => HttpResponse.json([])),
  );
});

afterEach(() => vi.restoreAllMocks());

describe('WarehouseReorderPage', () => {
  it('separates production and purchasing shortages and keeps their warehouse links', async () => {
    permissions.add('inventory:update');
    mount();

    expect(await screen.findByRole('heading', { name: 'Reorder needs' })).toBeInTheDocument();
    const production = await screen.findByRole('table', { name: 'Production demand' });
    const purchasing = screen.getByRole('table', { name: 'Purchasing demand' });
    expect(within(production).getByRole('columnheader', { name: 'Quantity to produce' })).toBeInTheDocument();
    expect(within(production).getByText('GOOD-1')).toBeInTheDocument();
    expect(within(production).queryByText('M3-INSERT')).not.toBeInTheDocument();
    expect(within(purchasing).getByText('M3-INSERT')).toBeInTheDocument();
    expect(within(purchasing).queryByText('GOOD-1')).not.toBeInTheDocument();
    expect(within(production).getByText(/^7 (pcs|pc|piece)$/i)).toBeInTheDocument();
    expect(within(purchasing).getByText(/^16 (pcs|pc|piece)$/i)).toBeInTheDocument();
    expect(within(production).getByText(/^3 (pcs|pc|piece)$/i)).toBeInTheDocument();
    expect(within(purchasing).getByText(/^4 (pcs|pc|piece)$/i)).toBeInTheDocument();

    expect(screen.getByText('Finished goods to produce').parentElement).toHaveTextContent('1');
    expect(screen.getByText('Materials to purchase').parentElement).toHaveTextContent('1');
    expect(screen.getByText('Total').parentElement).toHaveTextContent('2');

    const user = userEvent.setup();
    for (const [sku, path] of [['GOOD-1', '/warehouse/stock?focus=1'], ['M3-INSERT', '/warehouse/parts?focus=7']]) {
      const actions = screen.getByRole('button', { name: `Actions: ${sku}` });
      expect(within(actions.closest('td')!).getAllByRole('button')).toEqual([actions]);
      await user.click(actions);
      if (sku === 'GOOD-1') expect(screen.queryByRole('menuitem', { name: /shopping list/ })).not.toBeInTheDocument();
      await user.click(await screen.findByRole('menuitem', { name: 'Open' }));
      expect(screen.getByTestId('current-path')).toHaveTextContent(path);
    }

    expect(screen.getByRole('link', { name: 'Suppliers' })).toHaveAttribute('href', '/warehouse/suppliers');
    expect(screen.queryByRole('link', { name: 'Offers' })).not.toBeInTheDocument();
    expect(within(production).getByRole('link', { name: 'Printed bracket' })).toHaveAttribute('href', '/warehouse/stock?focus=1');
    await user.click(within(production).getByText(/^7 (pcs|pc|piece)$/i));
    expect(screen.getByTestId('current-path')).toHaveTextContent('/warehouse/stock?focus=1');
  });

  it('prepares a production project with the shortage and leaves the material menu separate', async () => {
    permissions.add('inventory:update');
    permissions.add('projects:read');
    permissions.add('projects:create');
    server.use(http.get('*/api/v1/warehouse-articles', () => HttpResponse.json({
      items: [{ ...article, project_id: 41 }], total: 1, limit: 200, offset: 0,
    })));
    const user = userEvent.setup();
    mount();
    await user.click(await screen.findByRole('button', { name: 'Actions: M3-INSERT' }));
    expect(screen.queryByRole('menuitem', { name: 'Produce more' })).not.toBeInTheDocument();
    await user.keyboard('{Escape}');
    await user.click(screen.getByRole('button', { name: 'Actions: GOOD-1' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Produce more' }));
    expect(screen.getByTestId('current-path')).toHaveTextContent('/projects');
    expect(JSON.parse(screen.getByTestId('route-state').textContent!)).toEqual({
      productionDraft: {
        name: 'Replenishment · Printed bracket',
        description: expect.stringMatching(/GOOD-1.*7\s+pc/s),
        target_parts_count: 7,
        productionArticleId: 1,
        parent_id: 41,
      },
    });
  });

  it('sorts exact shortages independently in both tables', async () => {
    const second = { ...article2, minimum_stock: '999999999999.000003', balance: { ...article2.balance, available: '999999999999' } };
    const first = { ...article, minimum_stock: '999999999999.000002', balance: { ...article.balance, available: '999999999999' } };
    server.use(http.get('*/api/v1/warehouse-articles', () => HttpResponse.json({
      items: [first, second], total: 2, limit: 200, offset: 0,
    })));
    const user = userEvent.setup();
    mount();
    const production = await screen.findByRole('table', { name: 'Production demand' });
    const purchasing = screen.getByRole('table', { name: 'Purchasing demand' });
    const sort = within(production).getByRole('button', { name: 'Quantity to produce' });
    await user.click(sort);
    expect(within(production).getAllByRole('row')[1]).toHaveTextContent('GOOD-1');
    await user.click(sort);
    expect(within(production).getAllByRole('row')[1]).toHaveTextContent('GOOD-2');
    expect(sort.closest('th')).toHaveAttribute('aria-sort', 'descending');
    expect(within(purchasing).getByRole('columnheader', { name: 'Suggested purchase quantity' })).toHaveAttribute('aria-sort', 'none');
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
    expect(articleRequests.every(query => query.includes('kind=finished') && query.includes('stock_source=own'))).toBe(true);
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

  it('uses only the material minimum and keeps production rows out of the shopping list even when IDs match', async () => {
    permissions.add('inventory:update');
    const linkedArticle: WarehouseArticle = {
      ...article, id: 2, name: 'Linked warehouse cable', kind: 'trade', unit_code: 'MTR', stock_source: 'material', small_part_id: 7, minimum_stock: '7.250001',
      balance: { physical: '5', reserved: '2', available: '3', is_low_stock: true },
    };
    const material: SmallPart = {
      ...part, name: 'Cable', unit_code: 'MTR', minimum_stock: '6.125',
      unit: { code: 'MTR', label: 'Metre', decimal_places: 6, is_active: true },
      balance: linkedArticle.balance,
    };
    const item = { id: 123, resource_kind: 'material', resource_id: 7, sku: part.sku, name: 'Cable', quantity: '3.125', unit_code: 'MTR', unit_label: 'Metre' };
    let saved = false;
    server.use(
      http.get('*/api/v1/warehouse-articles', () => HttpResponse.json({ items: [{ ...article, id: part.id }, linkedArticle], total: 2, limit: 200, offset: 0 })),
      http.get('*/api/v1/small-parts', () => HttpResponse.json({ items: [material], total: 1, limit: 200, offset: 0 })),
      http.get('*/api/v1/warehouse-shopping-list', () => HttpResponse.json(saved ? [item] : [])),
      http.put('*/api/v1/warehouse-shopping-list/material/7', () => {
        saved = true;
        return HttpResponse.json(item);
      }),
      http.delete('*/api/v1/warehouse-shopping-list/123', () => {
        saved = false;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    const firstPage = mount();

    expect(await screen.findByText('3.125 m')).toBeInTheDocument();
    expect(screen.queryByText('Linked warehouse cable')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Actions: M3-INSERT' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Add Cable to the shopping list' }));
    expect(await screen.findByText('Cable was added to the shopping list.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Actions: GOOD-1' }));
    expect(await screen.findByRole('menuitem', { name: 'Open' })).toBeEnabled();
    expect(screen.queryByRole('menuitem', { name: /shopping list/ })).not.toBeInTheDocument();
    await user.keyboard('{Escape}');
    firstPage.unmount();

    mount();
    await user.click(screen.getByRole('button', { name: /Shopping list/ }));
    const dialog = screen.getByRole('dialog', { name: 'Shopping list' });
    expect(await within(dialog).findByText('3.125 m')).toBeInTheDocument();
    expect(within(dialog).getByText('Cable')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Remove Cable from the shopping list' }));
    expect(await within(dialog).findByText('The shopping list is empty.')).toBeInTheDocument();
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  });

  it('shows the exact production shortage when large decimal stock values are nearly equal', async () => {
    permissions.add('inventory:update');
    permissions.add('projects:read');
    permissions.add('projects:create');
    server.use(
      http.get('*/api/v1/warehouse-articles', () => HttpResponse.json({
        items: [{ ...article, unit_code: 'MTR', minimum_stock: '999999999999.000001', balance: { ...article.balance, available: '999999999999' } }],
        total: 1, limit: 200, offset: 0,
      })),
    );
    mount();

    expect(await screen.findByText('0.000001 m')).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Actions: GOOD-1' }));
    expect(await screen.findByRole('menuitem', { name: 'Open' })).toBeEnabled();
    expect(screen.queryByRole('menuitem', { name: /shopping list/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole('menuitem', { name: 'Produce more' }));
    const draft = JSON.parse(screen.getByTestId('route-state').textContent!).productionDraft;
    expect(draft.description).toContain('0.000001 m');
    expect(draft).not.toHaveProperty('target_parts_count');
  });

  it('allows a reader to open the shopping list without offering purchase actions', async () => {
    const user = userEvent.setup();
    mount();

    await screen.findByText('M3-INSERT');
    await user.click(screen.getByRole('button', { name: 'Actions: M3-INSERT' }));
    expect(await screen.findByRole('menuitem', { name: 'Open' })).toBeEnabled();
    expect(screen.queryByRole('menuitem', { name: /Add .* to the shopping list/ })).not.toBeInTheDocument();
    await user.keyboard('{Escape}');
    await user.click(screen.getByRole('button', { name: /Shopping list/ }));
    expect(await within(screen.getByRole('dialog')).findByText('The shopping list is empty.')).toBeInTheDocument();
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
    let shoppingListRequested = false;
    server.use(
      http.get('*/api/v1/warehouse-articles', () => { articlesRequested = true; return HttpResponse.json({ items: [], total: 0 }); }),
      http.get('*/api/v1/small-parts', () => { partsRequested = true; return HttpResponse.json({ items: [], total: 0 }); }),
      http.get('*/api/v1/warehouse-shopping-list', () => { shoppingListRequested = true; return HttpResponse.json([]); }),
    );
    mount();

    expect(screen.getByRole('alert')).toHaveTextContent('You do not have permission to read warehouse articles.');
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(articlesRequested).toBe(false);
    expect(partsRequested).toBe(false);
    expect(shoppingListRequested).toBe(false);
  });
});
