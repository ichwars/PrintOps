import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { offersApi, type AcceptanceResult, type CustomerOrder, type Offer } from '../../api/offers';
import { OffersPage } from '../../pages/OffersPage';

vi.mock('../../api/offers', () => ({ offersApi: { list: vi.fn(), send: vi.fn(), reject: vi.fn(), accept: vi.fn() } }));

const draftOffer: Offer = {
  id: 1, business_profile_id: 1, customer_id: null, calculation_revision_id: 4, order_id: null, quotation_document_id: 17,
  number: 'ANG-2026-00001', status: 'draft', preferred_variant_sort_order: 0,
  snapshot: { calculation: { title: 'Mounting set', currency: 'EUR' }, revision: { revision_number: 1, selling_price: '25', currency: 'EUR' } },
  sent_at: null, accepted_at: null, rejected_at: null, version: 1,
  created_at: '2026-07-18T12:00:00Z', updated_at: '2026-07-18T12:00:00Z',
};

const sentOffer: Offer = {
  id: 2, business_profile_id: 1, customer_id: 7, calculation_revision_id: 5, order_id: null, quotation_document_id: null,
  number: 'ANG-2026-00002', status: 'sent', preferred_variant_sort_order: 0,
  snapshot: { calculation: { title: 'Wall hook', currency: 'EUR' }, revision: { revision_number: 2, selling_price: '40', currency: 'EUR' } },
  sent_at: '2026-07-19T09:00:00Z', accepted_at: null, rejected_at: null, version: 3,
  created_at: '2026-07-18T12:00:00Z', updated_at: '2026-07-19T09:00:00Z',
};

function acceptanceResult(offer: Offer): AcceptanceResult {
  return {
    offer,
    order: { id: 9, business_profile_id: 1, customer_id: offer.customer_id, offer_id: offer.id, project_id: 3, number: 'AUF-2026-00009', status: 'active', accepted_snapshot: offer.snapshot, created_at: offer.created_at, updated_at: offer.updated_at, reservations: [] } as CustomerOrder,
    project_id: 3,
  };
}

function mount() {
  return render(<MemoryRouter><OffersPage /></MemoryRouter>);
}

describe('OffersPage', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it('loads offers and sends a draft without creating an order', async () => {
    const user = userEvent.setup();
    vi.mocked(offersApi.list).mockResolvedValue([draftOffer]);
    vi.mocked(offersApi.send).mockResolvedValue({ ...draftOffer, status: 'sent', version: 2 });
    mount();

    expect(await screen.findByText('ANG-2026-00001')).toBeInTheDocument();
    expect(screen.getByText('Document #17')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Send offer|Angebot versenden/ }));
    await waitFor(() => expect(offersApi.send).toHaveBeenCalledWith(1, 1));
    expect(offersApi.accept).not.toHaveBeenCalled();
  });

  it('renders text action buttons with accessible names', async () => {
    vi.mocked(offersApi.list).mockResolvedValue([draftOffer, sentOffer]);
    mount();

    await screen.findByText('ANG-2026-00001');
    expect(screen.getByRole('button', { name: 'Send offer' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Accept offer' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject offer' })).toBeInTheDocument();
  });

  it('opens a ConfirmModal instead of window.confirm when accepting an offer', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => true);
    vi.mocked(offersApi.list).mockResolvedValue([sentOffer]);
    vi.mocked(offersApi.accept).mockResolvedValue(acceptanceResult({ ...sentOffer, status: 'accepted', version: 4 }));
    mount();

    await screen.findByText('ANG-2026-00002');
    await user.click(screen.getByRole('button', { name: 'Accept offer' }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('Accept offer and reserve stock?');
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(offersApi.accept).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole('button', { name: 'Accept offer' }));
    await waitFor(() => expect(offersApi.accept).toHaveBeenCalledWith(2, 3, expect.stringMatching(/^accept-2-/)));
    expect(confirmSpy).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('closes the ConfirmModal on cancel without accepting', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockImplementation(() => true);
    vi.mocked(offersApi.list).mockResolvedValue([sentOffer]);
    mount();

    await screen.findByText('ANG-2026-00002');
    await user.click(screen.getByRole('button', { name: 'Accept offer' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(offersApi.accept).not.toHaveBeenCalled();
  });

  it('rejects a sent offer directly without a confirmation dialog', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockImplementation(() => true);
    vi.mocked(offersApi.list).mockResolvedValue([sentOffer]);
    vi.mocked(offersApi.reject).mockResolvedValue({ ...sentOffer, status: 'rejected', version: 4 });
    mount();

    await screen.findByText('ANG-2026-00002');
    await user.click(screen.getByRole('button', { name: 'Reject offer' }));

    await waitFor(() => expect(offersApi.reject).toHaveBeenCalledWith(2, 3));
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('filters the loaded offers client-side via the search input', async () => {
    const user = userEvent.setup();
    vi.mocked(offersApi.list).mockResolvedValue([draftOffer, sentOffer]);
    mount();

    await screen.findByText('ANG-2026-00001');
    const searchbox = screen.getByRole('searchbox', { name: /searchOffers|Search offers/i });

    // Matches the snapshot calculation title of the sent offer only.
    await user.type(searchbox, 'wall hook');
    expect(screen.queryByText('ANG-2026-00001')).not.toBeInTheDocument();
    expect(screen.getByText('ANG-2026-00002')).toBeInTheDocument();

    // Clear button restores the full list.
    await user.click(screen.getByRole('button', { name: /clearSearch|Clear search/i }));
    expect(screen.getByText('ANG-2026-00001')).toBeInTheDocument();
    expect(screen.getByText('ANG-2026-00002')).toBeInTheDocument();

    // Matches the customer id of the sent offer.
    await user.type(searchbox, '#7');
    expect(screen.queryByText('ANG-2026-00001')).not.toBeInTheDocument();
    expect(screen.getByText('ANG-2026-00002')).toBeInTheDocument();

    // No match shows the filtered empty state.
    await user.clear(searchbox);
    await user.type(searchbox, 'no-such-offer');
    expect(screen.queryByText('ANG-2026-00001')).not.toBeInTheDocument();
    expect(screen.queryByText('ANG-2026-00002')).not.toBeInTheDocument();
    expect(screen.getByText(/noOffersMatchSearch|No offers match/i)).toBeInTheDocument();
  });
});
