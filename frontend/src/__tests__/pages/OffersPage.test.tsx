import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { offersApi, type OfferListItem } from '../../api/offers';
import i18n from '../../i18n';
import { OffersPage } from '../../pages/OffersPage';

vi.mock('../../api/offers', () => ({ offersApi: { page: vi.fn(), send: vi.fn(), reject: vi.fn(), accept: vi.fn() } }));
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ hasPermission: () => true }),
}));

function mount(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter initialEntries={[path]}><QueryClientProvider client={client}>
    <OffersPage />
  </QueryClientProvider></MemoryRouter>);
}

const offer: OfferListItem = {
  id: 1, business_profile_id: 1, customer_id: null, calculation_revision_id: 4, order_id: null, quotation_document_id: 17,
  number: 'ANG-2026-00001', status: 'draft', preferred_variant_sort_order: 0,
  snapshot: { calculation: { title: 'Mounting set', currency: 'EUR' }, revision: { revision_number: 1, selling_price: '25', currency: 'EUR' } },
  sent_at: null, accepted_at: null, rejected_at: null, version: 1,
  created_at: '2026-07-18T12:00:00Z', updated_at: '2026-07-18T12:00:00Z',
  customer_display_name: null,
};

describe('OffersPage', () => {
  beforeEach(async () => {
    vi.resetAllMocks();
    await i18n.changeLanguage('en');
  });

  it('loads offers and sends a draft without creating an order', async () => {
    vi.mocked(offersApi.page).mockResolvedValue({ items: [offer], total: 1, offset: 0, limit: 25 });
    vi.mocked(offersApi.send).mockResolvedValue({ ...offer, status: 'sent', version: 2 });
    mount('/orders/offers');

    expect(await screen.findByText('ANG-2026-00001')).toBeInTheDocument();
    expect(screen.getByText('Document #17')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Actions: ANG-2026-00001' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Send offer' }));
    await waitFor(() => expect(offersApi.send).toHaveBeenCalledWith(1, 1));
    expect(offersApi.accept).not.toHaveBeenCalled();
  });

  it('keeps the customer and calculation filters when paging and starts at page one after searching', async () => {
    vi.mocked(offersApi.page).mockImplementation(async ({ offset, limit, q }) => ({
      items: [{ ...offer, number: q ? 'Searched result' : offset ? 'Second page' : 'First page' }],
      total: q ? 1 : limit + 1,
      offset,
      limit,
    }));
    mount('/orders/offers?customer=3&profile=2&calculation=4');

    expect(await screen.findByText('First page')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(await screen.findByText('Second page')).toBeInTheDocument();
    expect(offersApi.page).toHaveBeenLastCalledWith(expect.objectContaining({
      customer_id: 3, business_profile_id: 2, calculation_id: 4, limit: 25, offset: 25,
    }));

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Mounting' } });
    expect(await screen.findByText('Searched result')).toBeInTheDocument();
    expect(offersApi.page).toHaveBeenLastCalledWith(expect.objectContaining({
      customer_id: 3, business_profile_id: 2, calculation_id: 4, q: 'Mounting', offset: 0,
    }));
  });
});
