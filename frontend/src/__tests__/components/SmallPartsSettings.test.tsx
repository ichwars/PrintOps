import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { SmallPartsSettings } from '../../components/settings/SmallPartsSettings';
import { server } from '../mocks/server';

describe('SmallPartsSettings', () => {
  it('manages catalogs and exposes calculation defaults', async () => {
    const categoryPost = vi.fn();
    server.use(
      http.get('/api/v1/small-parts/settings/categories', () => HttpResponse.json([])),
      http.get('/api/v1/small-parts/settings/units', () => HttpResponse.json([])),
      http.get('/api/v1/inventory/locations', () => HttpResponse.json([])),
      http.post('/api/v1/small-parts/settings/categories', async ({ request }) => {
        categoryPost(await request.json());
        return HttpResponse.json({ id: 1, name: 'Schrauben', is_active: true }, { status: 201 });
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const onDefaultsChange = vi.fn();
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={client}>
        <SmallPartsSettings defaultMinimumStock="5" lowStockWarning onDefaultsChange={onDefaultsChange} />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('heading', { name: 'Materialkataloge' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Einheiten' })).toBeInTheDocument();
    expect(screen.getByText('Bezeichnung der Materialkategorie')).toBeInTheDocument();
    expect(screen.getByText('Einheitencode, z. B. C62')).toBeInTheDocument();
    expect(screen.getByText('Anzeigename, z. B. Stück')).toBeInTheDocument();
    expect(screen.getByText('Nachkommastellen')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Lagerorte' })).toBeInTheDocument();
    expect(screen.getByText('Lagerorte gelten gemeinsam für Filament und Material.')).toBeInTheDocument();
    expect(screen.getByDisplayValue('5')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Neue Kategorie'), 'Schrauben');
    await user.click(screen.getByRole('button', { name: 'Kategorie hinzufügen' }));
    await waitFor(() => expect(categoryPost).toHaveBeenCalledWith({ name: 'Schrauben' }));
  });
});
