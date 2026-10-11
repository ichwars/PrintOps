import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { BusinessProfile } from '../../api/client';
import { NumberSequenceSettings } from '../../components/settings/NumberSequenceSettings';
import { WarehouseNumberSequenceSettings } from '../../components/settings/WarehouseNumberSequenceSettings';
import i18n from '../../i18n';
import { server } from '../mocks/server';
import { render } from '../utils';

const profile: BusinessProfile = {
  id: 7,
  name: 'EU Operations',
  legal_name: 'EU Operations GmbH',
  trading_name: null,
  country_code: 'DE',
  default_currency: 'EUR',
  timezone: 'Europe/Berlin',
  default_locale: 'de',
  billing_mode: 'hybrid',
  tax_mode: 'standard',
  default_tax_rate: '19',
  cash_accounting: false,
  input_tax_deductible: true,
  show_offer_qr: true,
  paypal_me_url: null,
  is_active: true,
  is_default: true,
  version: 4,
  created_at: '2026-07-01T10:00:00Z',
  updated_at: '2026-07-01T10:00:00Z',
  logo_media_type: null,
  logo_version: null,
  addresses: [],
  tax_identifiers: [],
  bank_accounts: [],
};

function useEmptySequences() {
  server.use(
    http.get('/api/v1/business-profiles/7/number-sequences', () => HttpResponse.json([])),
    http.get('/api/v1/inventory/number-sequences', () => HttpResponse.json([])),
  );
}

afterEach(async () => {
  cleanup();
  await i18n.changeLanguage('en');
});

describe('translated number sequence settings', () => {
  it.each([
    ['en', 'Invoice number sequence', 'Invoice prefix', 'Create invoice number sequence', 'Warehouse number sequences', 'Create Purchase order number sequence'],
    ['de', 'Rechnungsnummernkreis', 'Rechnungs-Präfix', 'Rechnungsnummernkreis anlegen', 'Nummernkreise der Lagerverwaltung', 'Bestellnummernkreis anlegen'],
    ['nl', 'Factuurnummerreeks', 'Factuurvoorvoegsel', 'factuurnummerreeks aanmaken', 'Nummerreeksen voor magazijnbeheer', 'inkoopordernummerreeks aanmaken'],
  ])('renders localized labels and actions for %s', async (language, invoiceTitle, prefixLabel, createInvoice, warehouseTitle, createPurchaseOrder) => {
    useEmptySequences();
    await i18n.changeLanguage(language);
    render(<>
      <NumberSequenceSettings profiles={[profile]} canManage />
      <WarehouseNumberSequenceSettings />
    </>);

    expect(await screen.findByRole('heading', { name: invoiceTitle })).toBeInTheDocument();
    expect(screen.getByLabelText(prefixLabel)).toHaveValue('RE');
    expect(screen.getByRole('button', { name: createInvoice })).toBeEnabled();
    expect(screen.getByRole('heading', { name: warehouseTitle })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: createPurchaseOrder })).toBeEnabled();
  });

  it('saves a Dutch invoice form with the unchanged sequence contract', async () => {
    useEmptySequences();
    let submitted: Record<string, unknown> | undefined;
    server.use(http.post('/api/v1/business-profiles/7/number-sequences', async ({ request }) => {
      submitted = await request.json() as Record<string, unknown>;
      return HttpResponse.json({ ...submitted, id: 1, business_profile_id: 7, version: 1 }, { status: 201 });
    }));
    await i18n.changeLanguage('nl');
    const user = userEvent.setup();
    render(<NumberSequenceSettings profiles={[profile]} canManage />);

    const prefix = await screen.findByLabelText('Factuurvoorvoegsel');
    await user.clear(prefix);
    await user.type(prefix, 'FACT');
    const nextNumber = screen.getByLabelText('Volgend factuurnummer');
    await user.clear(nextNumber);
    await user.type(nextNumber, '17');
    await user.click(screen.getByRole('button', { name: 'factuurnummerreeks aanmaken' }));

    await waitFor(() => expect(submitted).toEqual({
      key: 'invoice', prefix: 'FACT', pattern: '{PREFIX}-{YYYY}-{#####}', next_value: 17, reset_policy: 'yearly',
    }));
    expect(await screen.findByRole('status')).toHaveTextContent('Nummerreeks opgeslagen.');
  });

  it('keeps the monthly uniqueness guard visible and effective in Dutch', async () => {
    useEmptySequences();
    await i18n.changeLanguage('nl');
    const user = userEvent.setup();
    render(<NumberSequenceSettings profiles={[profile]} canManage />);

    const format = await screen.findByLabelText('Offertenummerformaat');
    await user.clear(format);
    fireEvent.change(format, { target: { value: '{PREFIX}-{####}' } });

    expect(screen.getByRole('alert')).toHaveTextContent('Maandelijks opnieuw beginnen vereist {YYMM}, zodat nummers per maand uniek blijven.');
    expect(screen.getByRole('button', { name: 'offertenummerreeks aanmaken' })).toBeDisabled();
  });

  it('saves Dutch warehouse settings with the existing annual reset defaults', async () => {
    useEmptySequences();
    let submitted: Record<string, unknown> | undefined;
    server.use(http.post('/api/v1/inventory/number-sequences', async ({ request }) => {
      submitted = await request.json() as Record<string, unknown>;
      return HttpResponse.json({ ...submitted, id: 1, version: 1 }, { status: 201 });
    }));
    await i18n.changeLanguage('nl');
    const user = userEvent.setup();
    render(<WarehouseNumberSequenceSettings />);

    expect(await screen.findByRole('heading', { name: 'Materiaalnummerreeks' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Spoelnummerreeks' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Goederenontvangstnummerreeks' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Inkoopordernummer jaarlijks opnieuw laten beginnen' })).toBeChecked();
    await user.click(screen.getByRole('button', { name: 'inkoopordernummerreeks aanmaken' }));

    await waitFor(() => expect(submitted).toEqual({
      key: 'purchase_order', prefix: 'BE', pattern: '{PREFIX}-{YYYY}-{#####}', next_value: 1, reset_policy: 'yearly',
    }));
    expect(await screen.findByRole('status')).toHaveTextContent('Nummerreeks opgeslagen.');
  });
});
