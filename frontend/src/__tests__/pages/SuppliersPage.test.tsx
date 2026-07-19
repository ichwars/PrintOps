import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { SuppliersPage } from '../../pages/SuppliersPage';
import { server } from '../mocks/server';
import { render } from '../utils';

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
    server.use(http.get('/api/v1/suppliers', () =>
      HttpResponse.json({ items: [supplier], total: 1, limit: 100, offset: 0 }),
    ));
  });

  afterEach(cleanup);

  it('searches suppliers and opens the supplier editor', async () => {
    const user = userEvent.setup();
    render(<SuppliersPage />);

    expect(await screen.findByRole('heading', { name: 'Suppliers' })).toBeInTheDocument();
    expect(await screen.findByText('Filament World')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Add supplier' }));
    expect(screen.getByRole('dialog', { name: 'Add supplier' })).toBeInTheDocument();
  });
});
