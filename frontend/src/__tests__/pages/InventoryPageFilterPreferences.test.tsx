import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import InventoryPageRouter from '../../pages/InventoryPage';
import i18n from '../../i18n';

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
