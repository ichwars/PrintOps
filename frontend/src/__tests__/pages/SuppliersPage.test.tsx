import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { SuppliersPage } from '../../pages/SuppliersPage';
import { server } from '../mocks/server';
import { render, selectComboboxOption } from '../utils';

const authState = vi.hoisted(() => ({ permissions: new Set<string>() }));

vi.mock('../../contexts/AuthContext', async () => {
  const actual = await vi.importActual<typeof import('../../contexts/AuthContext')>('../../contexts/AuthContext');
  return {
    ...actual,
    useAuth: () => ({
      authEnabled: true,
      user: null,
      loading: false,
      hasPermission: (permission: string) => authState.permissions.has(permission),
    }),
  };
});

const supplier = {
  id: 1,
  name: 'Filament World',
  contact_name: 'Ada Supply',
  email: 'orders@example.test',
  phone: null,
  website: null,
  address_line1: null,
  address_line2: null,
  postal_code: null,
  city: 'Berlin',
  country_code: 'DE',
  customer_number: null,
  payment_terms: null,
  default_lead_time_days: 4,
  internal_notes: null,
  is_active: true,
  created_at: '2026-07-01T10:00:00Z',
  updated_at: '2026-07-01T10:00:00Z',
};

describe('SuppliersPage', () => {
  beforeEach(() => {
    authState.permissions = new Set([
      'inventory:read',
      'inventory:create',
      'inventory:update',
      'inventory:delete',
    ]);
    server.use(http.get('/api/v1/suppliers', () =>
      HttpResponse.json({ items: [supplier], total: 1, limit: 100, offset: 0 }),
    ));
  });

  afterEach(cleanup);

  it('serializes search text and the inactive filter', async () => {
    const user = userEvent.setup();
    const requests: URL[] = [];
    server.use(http.get('/api/v1/suppliers', ({ request }) => {
      requests.push(new URL(request.url));
      return HttpResponse.json({ items: [supplier], total: 1, limit: 100, offset: 0 });
    }));

    render(<SuppliersPage />);

    expect(await screen.findByRole('heading', { name: 'Suppliers' })).toBeInTheDocument();
    expect(await screen.findByText('Filament World')).toBeInTheDocument();

    await user.type(screen.getByRole('searchbox', { name: 'Search suppliers' }), 'Filament World');
    await waitFor(() => expect(requests.some((url) => url.searchParams.get('q') === 'Filament World')).toBe(true));

    selectComboboxOption(screen.getByRole('combobox', { name: 'Status' }), 'Inactive');
    await waitFor(() => expect(requests.some((url) => url.searchParams.get('active') === 'false')).toBe(true));
  });

  it('loads suppliers beyond the first API page', async () => {
    const offsets: number[] = [];
    const firstPage = Array.from({ length: 50 }, (_, index) => ({
      ...supplier,
      id: index + 1,
      name: `Supplier ${index + 1}`,
    }));
    const lastSupplier = { ...supplier, id: 51, name: 'Supplier 51' };
    server.use(http.get('/api/v1/suppliers', ({ request }) => {
      const offset = Number(new URL(request.url).searchParams.get('offset') ?? 0);
      offsets.push(offset);
      return HttpResponse.json({
        items: offset === 0 ? firstPage : [lastSupplier],
        total: 51,
        limit: 50,
        offset,
      });
    }));

    render(<SuppliersPage />);

    expect(await screen.findByText('Supplier 51')).toBeInTheDocument();
    expect(offsets).toEqual([0, 50]);
  });

  it('opens the create editor when create permission is present', async () => {
    const user = userEvent.setup();
    render(<SuppliersPage />);

    await screen.findByText('Filament World');
    await user.click(screen.getByRole('button', { name: 'Add supplier' }));
    expect(screen.getByRole('dialog', { name: 'Add supplier' })).toBeInTheDocument();
  });

  it.each([
    { permissions: ['inventory:read'], create: false, edit: false, remove: false },
    { permissions: ['inventory:read', 'inventory:create'], create: true, edit: false, remove: false },
    { permissions: ['inventory:read', 'inventory:update'], create: false, edit: true, remove: false },
    { permissions: ['inventory:read', 'inventory:delete'], create: false, edit: false, remove: true },
  ])('ties supplier actions to independent permissions: $permissions', async ({ permissions, create, edit, remove }) => {
    authState.permissions = new Set(permissions);
    render(<SuppliersPage />);

    await screen.findByText('Filament World');
    expect(Boolean(screen.queryByRole('button', { name: 'Add supplier' }))).toBe(create);
    expect(Boolean(screen.queryByRole('button', { name: 'Edit Filament World' }))).toBe(edit);
    expect(Boolean(screen.queryByRole('button', { name: 'Delete supplier: Filament World' }))).toBe(remove);
  });

  it('opens delete-only users into a read-only supplier context', async () => {
    authState.permissions = new Set(['inventory:read', 'inventory:delete']);
    const user = userEvent.setup();
    render(<SuppliersPage />);

    await screen.findByText('Filament World');
    expect(screen.queryByRole('button', { name: 'Edit Filament World' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Delete supplier: Filament World' }));

    const dialog = screen.getByRole('dialog', { name: 'Delete supplier' });
    expect(within(dialog).getByRole('textbox', { name: /Company/ })).toBeDisabled();
    expect(within(dialog).queryByRole('button', { name: 'Save supplier' })).not.toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Delete supplier' })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });
});
