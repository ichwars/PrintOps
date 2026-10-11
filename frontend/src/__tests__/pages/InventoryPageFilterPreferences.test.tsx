import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, screen, waitFor, within } from '@testing-library/react';
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import InventoryPageRouter from '../../pages/InventoryPage';
import i18n from '../../i18n';
import { defaultInventoryFilters } from '../../utils/inventoryFilterPreferences';

const saved = new Map<string, string>();
const originalURL = window.location.href;
const spools = ['AlphaBrand', 'BetaBrand'].map((brand, index) => ({
  id: index + 1, brand, material: 'PLA', color_name: index ? 'Blue spool' : 'Red spool',
  rgba: index ? '0000FFFF' : 'FF0000FF', label_weight: 1000, core_weight: 250,
  weight_used: 0, archived_at: null, k_profiles: [], created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z', cost_per_kg: null,
}));

beforeEach(() => {
  saved.clear();
  window.history.replaceState({}, '', '/inventory');
  vi.mocked(localStorage.getItem).mockImplementation(key => saved.get(key) ?? null);
  vi.mocked(localStorage.setItem).mockImplementation((key, value) => { saved.set(key, value); });
  vi.mocked(localStorage.removeItem).mockImplementation(key => { saved.delete(key); });
  server.use(
    http.get('/api/v1/settings/spoolman', () => HttpResponse.json({ spoolman_enabled: 'false' })),
    http.get('/api/v1/inventory/spools', () => HttpResponse.json(spools)),
    http.get('/api/v1/inventory/assignments', () => HttpResponse.json([])),
    http.get('/api/v1/inventory/catalog', () => HttpResponse.json([])),
    http.get('/api/v1/inventory/spool-catalog', () => HttpResponse.json([])),
  );
});

afterEach(async () => {
  await i18n.changeLanguage('en');
  window.history.replaceState({}, '', originalURL);
  vi.mocked(localStorage.getItem).mockReset();
  vi.mocked(localStorage.setItem).mockReset();
  vi.mocked(localStorage.removeItem).mockReset();
});

describe('inventory filter preferences', () => {
  const scope = 'printops-inventory-filters:v1:local:appliance';
  function saveOrdinaryFilters() {
    saved.set(scope, JSON.stringify({ version: 1, filters: { ...defaultInventoryFilters, search: 'AlphaBrand' } }));
  }

  it.each(['?focus=unknown', '?location_id=abc', '?spool=0', '?focus=&location_id=0&spool=-2'])(
    'keeps ordinary filters and persists later edits for invalid URL overrides: %s', async (query) => {
      saveOrdinaryFilters();
      window.history.replaceState({}, '', `/inventory${query}`);
      const user = userEvent.setup();
      const first = render(<InventoryPageRouter />);
      await screen.findByRole('table');
      expect(screen.getByPlaceholderText(/search/i)).toHaveValue('AlphaBrand');
      expect(screen.queryByText('BetaBrand')).not.toBeInTheDocument();
      await user.clear(screen.getByPlaceholderText(/search/i));
      await user.type(screen.getByPlaceholderText(/search/i), 'BetaBrand');
      await waitFor(() => expect(JSON.parse(saved.get(scope)!).filters.search).toBe('BetaBrand'));
      first.unmount();
      window.history.replaceState({}, '', '/inventory');
      render(<InventoryPageRouter />);
      await screen.findByRole('table');
      expect(screen.getByPlaceholderText(/search/i)).toHaveValue('BetaBrand');
    },
  );

  it.each(['?focus=missing-cost', '?location_id=__none__', '?focus=missing-cost&location_id=abc'])(
    'gives a valid override precedence and keeps later edits transient: %s', async (query) => {
      saveOrdinaryFilters();
      window.history.replaceState({}, '', `/inventory${query}`);
      const user = userEvent.setup();
      const first = render(<InventoryPageRouter />);
      await screen.findByRole('table');
      expect(screen.getByPlaceholderText(/search/i)).toHaveValue('');
      expect(screen.getByText('BetaBrand')).toBeInTheDocument();
      await user.type(screen.getByPlaceholderText(/search/i), 'BetaBrand');
      expect(JSON.parse(saved.get(scope)!).filters.search).toBe('AlphaBrand');
      first.unmount();
      window.history.replaceState({}, '', '/inventory');
      render(<InventoryPageRouter />);
      await screen.findByRole('table');
      expect(screen.getByPlaceholderText(/search/i)).toHaveValue('AlphaBrand');
    },
  );

  it('keeps Dutch labels when resetting the actual inventory column configuration', async () => {
    await i18n.changeLanguage('nl');
    const user = userEvent.setup();
    render(<InventoryPageRouter />);
    await screen.findByRole('table');
    await user.click(screen.getByRole('button', { name: 'Kolommen' }));
    const modal = screen.getByRole('heading', { name: 'Kolommen configureren' }).closest('.card-shadow') as HTMLElement;
    await user.click(within(modal).getByRole('button', { name: 'Resetten' }));
    expect(within(modal).getByText('Toegevoegd')).toBeInTheDocument();
    expect(within(modal).getByText('Locatie')).toBeInTheDocument();
    expect(within(modal).queryByText('Added')).not.toBeInTheDocument();
    await user.click(within(modal).getByRole('button', { name: 'Wijzigingen toepassen' }));
    expect(screen.getByRole('columnheader', { name: /Toegevoegd/ })).toBeInTheDocument();
  });

  it('preserves unsaved inventory column visibility and order through a query update and language change', async () => {
    let queryClient!: QueryClient;
    function PageWithQueryContext() {
      queryClient = useQueryClient();
      return <InventoryPageRouter />;
    }
    const user = userEvent.setup();
    render(<PageWithQueryContext />);
    await screen.findByRole('table');
    await user.click(screen.getByRole('button', { name: 'Columns' }));
    const modal = screen.getByRole('heading', { name: 'Configure Columns' }).closest('.card-shadow') as HTMLElement;
    const brand = within(modal).getByText('Brand').closest('[draggable="true"]') as HTMLElement;
    await user.click(within(brand).getByTitle('Hide column'));
    await user.click(within(brand).getByTitle('Move up'));
    const order = () => Array.from(modal.querySelectorAll('[draggable="true"] span')).map(element => element.textContent);
    const draftOrder = order();
    act(() => queryClient.setQueryData(['inventory-spools'], spools.map(spool => ({ ...spool, brand: `${spool.brand} Updated` }))));
    await screen.findByText('AlphaBrand Updated');
    expect(within(brand).getByTitle('Show column')).toBeInTheDocument();
    expect(order()).toEqual(draftOrder);
    await act(() => i18n.changeLanguage('nl'));
    const translatedBrand = within(modal).getByText('Merk').closest('[draggable="true"]') as HTMLElement;
    expect(within(translatedBrand).getByTitle('Kolom tonen')).toBeInTheDocument();
    expect(Array.from(modal.querySelectorAll('[draggable="true"]')).indexOf(translatedBrand)).toBe(draftOrder.indexOf('Brand'));
    await user.click(within(modal).getByRole('button', { name: 'Wijzigingen toepassen' }));
    const applied = JSON.parse(saved.get('printops-inventory-columns')!);
    expect(applied.find((column: { id: string }) => column.id === 'brand').visible).toBe(false);
    expect(applied.findIndex((column: { id: string }) => column.id === 'brand')).toBe(draftOrder.indexOf('Brand'));
  });

  it('renders Dutch inventory column labels with the actual table', async () => {
    await i18n.changeLanguage('nl');
    render(<InventoryPageRouter />);

    await screen.findByRole('table');
    expect(screen.getByRole('columnheader', { name: /Toegevoegd/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Locatie/ })).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: /Added/ })).not.toBeInTheDocument();
  });

  it('restores the visible search after returning and clearing filters removes the saved preference', async () => {
    const user = userEvent.setup();
    const first = render(<InventoryPageRouter />);
    await screen.findByRole('table');
    await user.type(screen.getByPlaceholderText(/search/i), 'AlphaBrand');
    await waitFor(() => expect(screen.queryByText('BetaBrand')).not.toBeInTheDocument());
    first.unmount();

    render(<InventoryPageRouter />);
    await screen.findByRole('table');
    expect(screen.getByPlaceholderText(/search/i)).toHaveValue('AlphaBrand');
    expect(screen.queryByText('BetaBrand')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await screen.findByText('BetaBrand');
    expect(screen.getByPlaceholderText(/search/i)).toHaveValue('');
    expect([...saved.keys()].filter(key => key.startsWith('printops-inventory-filters:'))).toEqual([]);
  });
});
