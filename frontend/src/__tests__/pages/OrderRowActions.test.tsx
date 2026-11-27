import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { offersApi, ordersApi, type CustomerOrder, type OfferDetail, type OfferListItem } from '../../api/offers';
import i18n from '../../i18n';
import { OffersPage } from '../../pages/OffersPage';
import { OrdersOverviewPage } from '../../pages/OrdersOverviewPage';

const auth = vi.hoisted(() => ({ permissions: new Set<string>() }));
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ hasPermission: (permission: string) => auth.permissions.has(permission) }),
}));

const offer: OfferDetail = {
  id: 4, number: 'OFFER-4', business_profile_id: 7, customer_id: 11, calculation_revision_id: 22,
  order_id: null, quotation_document_id: null, status: 'draft', preferred_variant_sort_order: 0,
  snapshot: { calculation: { id: 8, title: 'Bracket' }, revision: { selling_price: '24.00', currency: 'EUR', revision_number: 1 } },
  sent_at: null, accepted_at: null, rejected_at: null, version: 2,
  created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-01T00:00:00Z',
  customer_display_name: null, quotation: null,
};
const order: CustomerOrder = {
  id: 8, number: 'ORDER-8', business_profile_id: 7, customer_id: 11, offer_id: 4, project_id: 9,
  status: 'active', accepted_snapshot: {}, reservations: [], created_at: offer.created_at, updated_at: offer.updated_at,
};

function LocationProbe() {
  const location = useLocation();
  return <output>{location.pathname}{location.search}</output>;
}

function mount(ui: React.ReactNode, path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter initialEntries={[path]}><QueryClientProvider client={client}>
    {ui}<LocationProbe />
  </QueryClientProvider></MemoryRouter>);
}

function offerPage(items: OfferListItem[]) {
  return { items, total: items.length, offset: 0, limit: 25 };
}

describe('Order table row actions', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en');
    auth.permissions = new Set(['commercial_documents:read', 'orders:read']);
  });

  afterEach(() => vi.restoreAllMocks());

  it('shows the names and sorts alphabetically in both directions with unassigned offers last', async () => {
    const zeta = { ...offer, id: 1, number: 'OFFER-1', customer_id: 2, customer_display_name: 'Zeta Works' };
    const unassigned = { ...offer, id: 2, number: 'OFFER-2', customer_id: null, customer_display_name: null };
    const alpha = { ...offer, id: 3, number: 'OFFER-3', customer_id: 19, customer_display_name: 'Alpha Studio' };
    const page = vi.spyOn(offersApi, 'page')
      .mockResolvedValueOnce(offerPage([zeta, unassigned, alpha]))
      .mockResolvedValueOnce(offerPage([alpha, zeta, unassigned]))
      .mockResolvedValueOnce(offerPage([zeta, alpha, unassigned]));
    const user = userEvent.setup();
    mount(<OffersPage />, '/orders/offers');
    expect(await screen.findByRole('cell', { name: 'Alpha Studio' })).toBeVisible();
    expect(screen.getByRole('cell', { name: 'Zeta Works' })).toBeVisible();
    const header = screen.getByRole('columnheader', { name: 'Customer' });
    const sort = within(header).getByRole('button');
    const rowOrder = () => screen.getAllByRole('row').slice(1).map(row => within(row).getAllByRole('cell')[0].textContent);

    await user.click(sort);
    expect(header).toHaveAttribute('aria-sort', 'ascending');
    expect(page).toHaveBeenLastCalledWith(expect.objectContaining({ sort_by: 'customer', sort_dir: 'asc' }));
    await waitFor(() => expect(rowOrder()).toEqual(['OFFER-3', 'OFFER-1', 'OFFER-2']));
    await user.click(sort);
    expect(header).toHaveAttribute('aria-sort', 'descending');
    expect(page).toHaveBeenLastCalledWith(expect.objectContaining({ sort_by: 'customer', sort_dir: 'desc' }));
    await waitFor(() => expect(rowOrder()).toEqual(['OFFER-1', 'OFFER-3', 'OFFER-2']));
  });

  it('finds the displayed customer and only accepts an offer after confirmation', async () => {
    auth.permissions.add('commercial_documents:approve');
    const sent = { ...offer, status: 'sent' as const, customer_display_name: 'Alpha Studio' };
    const page = vi.spyOn(offersApi, 'page').mockImplementation(async ({ q }) => (
      offerPage(q === 'alpha studio' ? [sent] : [sent, { ...offer, id: 5, number: 'OFFER-5' }])
    ));
    const accept = vi.spyOn(offersApi, 'accept').mockImplementation(async () => { throw new Error('Reservation unavailable'); });
    const user = userEvent.setup();
    mount(<OffersPage />, '/orders/offers?customer=11');

    await user.type(await screen.findByRole('searchbox'), 'alpha studio');
    expect(await screen.findByText('Alpha Studio')).toBeVisible();
    await waitFor(() => expect(screen.queryByText('OFFER-5')).not.toBeInTheDocument());
    expect(page).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'alpha studio', customer_id: 11 }));
    await user.click(screen.getByRole('button', { name: 'Actions: OFFER-4' }));
    await user.click(screen.getByRole('menuitem', { name: 'Accept offer' }));

    const dialog = await screen.findByRole('dialog', { name: 'Accept offer?' });
    expect(accept).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(accept).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Actions: OFFER-4' }));
    await user.click(screen.getByRole('menuitem', { name: 'Accept offer' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Accept offer' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Reservation unavailable');
    expect(accept).toHaveBeenCalledTimes(1);
    expect(accept).toHaveBeenCalledWith(sent.id, sent.version, expect.stringMatching(/^accept-4-/));
    expect(screen.getByText('/orders/offers?customer=11')).toBeInTheDocument();
  });

  it('opens the offer from its data cells, preserves filters and restores focus to the row', async () => {
    const secondOffer = { ...offer, id: 5, number: 'OFFER-5' };
    vi.spyOn(offersApi, 'page').mockResolvedValue(offerPage([offer, secondOffer]));
    const detail = vi.spyOn(offersApi, 'get').mockResolvedValue(secondOffer);
    const user = userEvent.setup();
    mount(<OffersPage />, '/orders/offers?customer=11&profile=7');
    const row = await screen.findByRole('row', { name: /OFFER-5/ });
    const cell = within(row).getByRole('cell', { name: 'OFFER-5' });
    const selection = document.getSelection()!;
    const range = document.createRange();
    range.selectNodeContents(cell);
    selection.removeAllRanges();
    selection.addRange(range);
    fireEvent.click(cell);
    selection.removeAllRanges();
    expect(detail).not.toHaveBeenCalled();

    await user.click(within(row).getByRole('cell', { name: 'Bracket' }));
    expect(await screen.findByRole('dialog', { name: 'OFFER-5' })).toBeInTheDocument();
    expect(screen.getByText('/orders/offers?customer=11&profile=7&offer=5')).toBeInTheDocument();
    expect(detail).toHaveBeenCalledWith(5);
    await user.keyboard('{Escape}');
    expect(row).toHaveFocus();
    expect(screen.getByText('/orders/offers?customer=11&profile=7')).toBeInTheDocument();

    await user.keyboard('[Space]');
    expect(await screen.findByRole('dialog', { name: 'OFFER-5' })).toBeInTheDocument();
  });

  it('opens offer details for a reader and hides write actions', async () => {
    vi.spyOn(offersApi, 'page').mockResolvedValue(offerPage([offer]));
    const detail = vi.spyOn(offersApi, 'get').mockResolvedValue(offer);
    const user = userEvent.setup();
    mount(<OffersPage />, '/orders/offers');
    await user.click(await screen.findByRole('button', { name: 'Actions: OFFER-4' }));
    expect(detail).not.toHaveBeenCalled();
    const menu = screen.getByRole('menu');
    expect(within(menu).getAllByRole('menuitem')).toHaveLength(1);
    await user.click(within(menu).getByRole('menuitem', { name: 'Open offer' }));
    expect(await screen.findByRole('dialog', { name: 'OFFER-4' })).toHaveTextContent('Bracket');
    expect(screen.getByText('No document lines available.')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toHaveTextContent('€24.00');
    expect(within(screen.getByRole('dialog')).queryByText('Gross')).not.toBeInTheDocument();
    expect(detail).toHaveBeenCalledWith(4);
  });

  it('shows the quotation recipient, quantities and exact stored net and gross amounts', async () => {
    vi.spyOn(offersApi, 'page').mockResolvedValue(offerPage([offer]));
    vi.spyOn(offersApi, 'get').mockResolvedValue({
      ...offer,
      customer_display_name: 'Ada Example',
      quotation: {
        customer_id: 11, currency: 'EUR', subtotal_amount: '25.00', tax_amount: '1.75', total_amount: '26.75',
        lines: [{
          id: 1, position: 1, description: 'Mounting bracket', quantity: '2', unit_code: 'C62',
          unit_price: '11.125', net_amount: '22.25', tax_category_code: 'S', tax_rate: '7', product_identifier: 'BR-1',
        }, {
          id: 2, position: 2, description: 'Hardware', quantity: '0.5', unit_code: 'KGM',
          unit_price: '5.50', net_amount: '2.75', tax_category_code: 'S', tax_rate: '7', product_identifier: null,
        }],
      },
    });
    const user = userEvent.setup();
    mount(<OffersPage />, '/orders/offers');
    await user.click(await screen.findByText('OFFER-4'));
    const dialog = within(await screen.findByRole('dialog', { name: 'OFFER-4' }));
    expect(dialog.getByText('Ada Example')).toBeVisible();
    const lines = within(dialog.getByRole('region', { name: 'Offer lines' })).getAllByRole('listitem');
    expect(lines).toHaveLength(2);
    expect(lines[0]).toHaveTextContent('Mounting bracket');
    expect(lines[0]).toHaveTextContent('€11.125');
    expect(lines[0]).toHaveTextContent('€22.25');
    expect(lines[1]).toHaveTextContent('0.5 kg');
    expect(lines[1]).toHaveTextContent('€2.75');
    for (const total of ['€25.00', '€1.75', '€26.75']) expect(dialog.getByText(total)).toBeVisible();
    expect(dialog.queryByText('€24.00')).not.toBeInTheDocument();
  });

  it('opens the order with Enter and lets the project link navigate independently', async () => {
    auth.permissions.add('projects:read');
    vi.spyOn(ordersApi, 'list').mockResolvedValue([order]);
    const user = userEvent.setup();
    mount(<OrdersOverviewPage />, '/orders');
    const row = await screen.findByRole('row', { name: /ORDER-8/ });
    await user.click(within(row).getByRole('link', { name: '#9' }));
    expect(screen.getByText('/projects/9')).toBeInTheDocument();
    row.focus();
    await user.keyboard('{Enter}');
    expect(screen.getByText('/orders/8')).toBeInTheDocument();
  });

  it('filters by customer and company profile and calls the existing send command', async () => {
    auth.permissions.add('commercial_documents:issue');
    const page = vi.spyOn(offersApi, 'page').mockResolvedValue(offerPage([offer]));
    const send = vi.spyOn(offersApi, 'send').mockResolvedValue({ ...offer, status: 'sent' });
    const user = userEvent.setup();
    mount(<OffersPage />, '/orders/offers?customer=11&profile=7');
    await user.click(await screen.findByRole('button', { name: 'Actions: OFFER-4' }));
    expect(page).toHaveBeenLastCalledWith(expect.objectContaining({ customer_id: 11, business_profile_id: 7 }));
    await user.click(screen.getByRole('menuitem', { name: 'Send offer' }));
    await waitFor(() => expect(send).toHaveBeenCalledWith(4, 2));
  });

  it('links from the order to the source offer and requires confirmation to cancel', async () => {
    auth.permissions.add('orders:cancel');
    vi.spyOn(ordersApi, 'list').mockResolvedValue([order]);
    const cancel = vi.spyOn(ordersApi, 'cancel').mockResolvedValue({ ...order, status: 'cancelled' });
    const user = userEvent.setup();
    mount(<OrdersOverviewPage />, '/orders');
    const trigger = await screen.findByRole('button', { name: 'Actions: ORDER-8' });
    await user.click(trigger);
    expect(screen.queryByRole('menuitem', { name: 'Open project' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('menuitem', { name: 'Open offer' }));
    expect(screen.getByText('/orders/offers?offer=4')).toBeInTheDocument();
    await user.click(trigger);
    await user.click(screen.getByRole('menuitem', { name: 'Cancel order' }));
    expect(cancel).not.toHaveBeenCalled();
    const dialog = screen.getByRole('dialog', { name: 'Cancel order' });
    await user.click(within(dialog).getByRole('button', { name: 'Cancel order' }));
    await waitFor(() => expect(cancel).toHaveBeenCalledWith(8, expect.any(String)));
    await user.click(trigger);
    expect(screen.queryByRole('menuitem', { name: 'Cancel order' })).not.toBeInTheDocument();
  });
});
