import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { offersApi, type Offer } from '../../api/offers';
import { OffersPage } from '../../pages/OffersPage';

vi.mock('../../api/offers', () => ({ offersApi: { list: vi.fn(), send: vi.fn(), reject: vi.fn(), accept: vi.fn() } }));

const offer: Offer = {
  id: 1, business_profile_id: 1, customer_id: null, calculation_revision_id: 4, order_id: null,
  number: 'ANG-2026-00001', status: 'draft', preferred_variant_sort_order: 0,
  snapshot: { calculation: { title: 'Mounting set', currency: 'EUR' }, revision: { revision_number: 1, selling_price: '25', currency: 'EUR' } },
  sent_at: null, accepted_at: null, rejected_at: null, version: 1,
  created_at: '2026-07-18T12:00:00Z', updated_at: '2026-07-18T12:00:00Z',
};

describe('OffersPage', () => {
  it('loads offers and sends a draft without creating an order', async () => {
    vi.mocked(offersApi.list).mockResolvedValue([offer]);
    vi.mocked(offersApi.send).mockResolvedValue({ ...offer, status: 'sent', version: 2 });
    render(<MemoryRouter><OffersPage /></MemoryRouter>);

    expect(await screen.findByText('ANG-2026-00001')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Send offer|Angebot versenden/ }));
    await waitFor(() => expect(offersApi.send).toHaveBeenCalledWith(1, 1));
    expect(offersApi.accept).not.toHaveBeenCalled();
  });
});
