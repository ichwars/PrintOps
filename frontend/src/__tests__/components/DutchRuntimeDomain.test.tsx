import { smallPartsApi } from '../../api/smallParts';
import { MaterialCsvImportModal } from '../../components/MaterialCsvImportModal';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ordersApi, type CustomerOrder } from '../../api/offers';
import { readinessFindingText } from '../../components/settings/documents/readinessMessages';
import { LexwarePreviewValue } from '../../components/settings/lexware/LexwarePreviewValue';
import i18n from '../../i18n';
import { OrdersOverviewPage } from '../../pages/OrdersOverviewPage';
import { OrderDetailPage } from '../../pages/OrderDetailPage';

const order: CustomerOrder = {
  id: 9, business_profile_id: 1, customer_id: null, offer_id: 7, project_id: 5,
  number: 'ORD-9', status: 'active', accepted_snapshot: {}, created_at: '2026-08-01', updated_at: '2026-08-01',
  reservations: [{ id: 3, source_key: 'material:4', resource_kind: 'small_part', material_code: null,
    requested_quantity: '12', unit_code: 'C62', status: 'active', released_at: null,
    allocations: [{ id: 11, inventory_backend: 'local', spool_id: null, external_spool_id: null,
      small_part_id: 4, allocated_quantity: '12', consumed_quantity: '2' }] }],
};

beforeEach(async () => { await i18n.changeLanguage('nl'); });

describe('Dutch commerce runtime', () => {
  it('shows translated readiness rules for a regional Dutch locale and retains unknown findings', () => {
    expect(readinessFindingText('nl-NL', 'installments_total_invalid', 'server title', 'server correction')).toEqual({
      title: 'De aandelen van de deelbetalingen zijn samen geen 100%',
      correction: 'Pas de aandelen van de deelbetalingen aan zodat ze samen precies 100% vormen.',
    });
    expect(readinessFindingText('nl', 'einvoice_ruleset_unavailable', '', '').correction)
      .toBe('Selecteer EN 16931 1.3.16 en XRechnung 3.0.2.');
    expect(readinessFindingText('nl', 'future_server_code', 'Provider finding', 'Provider correction'))
      .toEqual({ title: 'Provider finding', correction: 'Provider correction' });
    expect(readinessFindingText('de-DE', 'default_bank_multiple', '', '').title)
      .toBe('Mehrere Standardbankverbindungen festgelegt');
  });

  it('translates nested Lexware preview labels while preserving names, addresses and unknown fields', async () => {
    render(<LexwarePreviewValue value={{ display_name: 'Customer BV', kind: 'company',
      addresses: [{ kind: 'delivery', postal_code: '1234 AB', city: 'Amsterdam', is_default: true }],
      validation_status: 'valid', provider_field: 'Original value' }} />);
    expect(screen.getAllByText('Customer BV')).toHaveLength(2);
    expect(screen.getByText('Alle velden weergeven')).toBeInTheDocument();
    expect(screen.getByText('Weergavenaam')).toBeInTheDocument();
    expect(screen.getByText('Bezorgadres')).toBeInTheDocument();
    expect(screen.getByText('Geldig')).toBeInTheDocument();
    expect(screen.getByText('provider_field')).toBeInTheDocument();
    expect(screen.getByText('Original value')).toBeInTheDocument();
    await act(async () => { await i18n.changeLanguage('en'); });
    expect(screen.getByText('Show all fields')).toBeInTheDocument();
    expect(screen.getByText('Delivery address')).toBeInTheDocument();
    expect(screen.getAllByText('Customer BV')).toHaveLength(2);
  });

  it('renders the Dutch order overview and reservations and submits the original issue command', async () => {
    vi.spyOn(ordersApi, 'list').mockResolvedValue([order]);
    vi.spyOn(ordersApi, 'get').mockResolvedValue(order);
    const issue = vi.spyOn(ordersApi, 'issueSmallPart').mockResolvedValue(order);
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={['/orders']}><Routes>
      <Route path="/orders" element={<OrdersOverviewPage />} />
      <Route path="/orders/:id" element={<OrderDetailPage />} />
    </Routes></MemoryRouter>);
    expect(await screen.findByText('ORD-9')).toBeInTheDocument();
    expect(screen.getByText('Geaccepteerde offertes, projecten en gereserveerde voorraad.')).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Openen' }));
    expect(await screen.findByRole('heading', { name: 'Reserveringen' })).toBeInTheDocument();
    expect(screen.getByText('Materiaal #4')).toBeInTheDocument();
    expect(screen.getByText(/Resterend: 10 C62/)).toBeInTheDocument();
    await user.type(screen.getByRole('spinbutton', { name: 'Hoeveelheid' }), '3');
    await user.click(screen.getByRole('button', { name: 'Uitgeven' }));
    await waitFor(() => expect(issue).toHaveBeenCalledWith(9, 11, '3', expect.stringMatching(/^issue-9-11-/)));
  });
});

it('renders Dutch CSV preview feedback and sends the selected file unchanged', async () => {
  const file = new File(['Artikelnummer,Bezeichnung,Eenheid\nNL-1,Bout,C62'], 'material.csv', { type: 'text/csv' });
  vi.spyOn(smallPartsApi, 'importCsvPreview').mockResolvedValue({
    valid_count: 1, error_count: 0, skipped_count: 0, warnings: [],
    rows: [{ row_number: 2, status: 'valid', action: 'create', sku: 'NL-1', name: 'Bout',
      unit_code: 'C62', opening_quantity: '5', reason: null, warnings: [] }],
  });
  const importCsv = vi.spyOn(smallPartsApi, 'importCsv').mockResolvedValue({ created: 1, updated: 0, skipped: 0, errors: 0, error_rows: [] });
  const onImported = vi.fn();
  const user = userEvent.setup();
  render(<MaterialCsvImportModal onClose={() => {}} onImported={onImported} />);
  expect(screen.getByRole('heading', { name: 'Materiaal uit CSV importeren' })).toBeInTheDocument();
  await user.upload(screen.getByLabelText('CSV-bestand'), file);
  expect(await screen.findByText('1 geldig')).toBeInTheDocument();
  expect(screen.getByText('Aanmaken')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '1 rij importeren' }));
  await waitFor(() => expect(importCsv).toHaveBeenCalledWith(file));
  expect(onImported).toHaveBeenCalledWith(1, 0);
});
