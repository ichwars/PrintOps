import { useState } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  procurementOffersApi,
  suppliersApi,
  type ProcurementOffer,
  type ProcurementOfferDraft,
  type Supplier,
} from '../../api/procurement';
import { ProcurementOffersEditor } from '../../components/warehouse/ProcurementOffersEditor';

const supplier = (overrides: Partial<Supplier> = {}): Supplier => ({
  id: 1,
  name: 'Alpha Supply',
  contact_name: null,
  email: null,
  phone: null,
  website: null,
  address_line1: null,
  address_line2: null,
  postal_code: null,
  city: null,
  country_code: null,
  customer_number: null,
  payment_terms: null,
  default_lead_time_days: 6,
  internal_notes: null,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  ...overrides,
});

const supplierA = supplier();
const supplierB = supplier({ id: 2, name: 'Beta Supply', default_lead_time_days: 12 });

const draft = (overrides: Partial<ProcurementOfferDraft> = {}): ProcurementOfferDraft => ({
  supplier_id: supplierA.id,
  supplier_sku: 'ALPHA-1',
  purchase_url: 'https://alpha.example/items/1',
  package_quantity: '10',
  package_unit_code: 'C62',
  minimum_order_quantity: '1',
  lead_time_days: 6,
  net_price: '4.20',
  gross_price: '4.99',
  is_preferred: true,
  is_active: true,
  ...overrides,
});

const readOffer = (
  overrides: Partial<ProcurementOffer> = {},
): ProcurementOffer => ({
  ...draft(),
  id: 41,
  small_part_id: 5,
  filament_sku_settings_id: null,
  resource_key: 'material:5',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  supplier: supplierA,
  ...overrides,
});

function Harness({ initial }: { initial: ProcurementOfferDraft[] }) {
  const [offers, setOffers] = useState(initial);
  return (
    <>
      <ProcurementOffersEditor
        suppliers={[supplierA, supplierB]}
        offers={offers}
        onChange={setOffers}
      />
      <output data-testid="offers-value">{JSON.stringify(offers)}</output>
    </>
  );
}

const currentOffers = () =>
  JSON.parse(screen.getByTestId('offers-value').textContent ?? '[]') as ProcurementOfferDraft[];

describe('ProcurementOffersEditor', () => {
  it('keeps one preferred offer and supports an alternative', async () => {
    const onChange = vi.fn();
    render(
      <ProcurementOffersEditor
        suppliers={[supplierA, supplierB]}
        offers={[]}
        onChange={onChange}
      />,
    );
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: 'Bezugsquelle hinzufügen' }));
    expect(screen.getByRole('heading', { name: 'Bevorzugte Bezugsquelle' })).toBeInTheDocument();
    expect(onChange).toHaveBeenLastCalledWith([
      expect.objectContaining({ is_preferred: true, is_active: true }),
    ]);

    await user.click(
      screen.getByRole('button', { name: 'Alternative Bezugsquelle hinzufügen' }),
    );
    expect(screen.getByRole('heading', { name: 'Alternative Bezugsquelle' })).toBeInTheDocument();
    expect(onChange).toHaveBeenLastCalledWith([
      expect.objectContaining({ is_preferred: true }),
      expect.objectContaining({ is_preferred: false }),
    ]);
  });

  it('promotes an alternative and demotes the old preferred offer', async () => {
    render(
      <Harness
        initial={[
          draft(),
          draft({ supplier_id: supplierB.id, supplier_sku: 'BETA-1', is_preferred: false }),
        ]}
      />,
    );
    const user = userEvent.setup();
    const alternative = screen.getByRole('region', { name: 'Alternative Bezugsquelle' });

    await user.click(
      within(alternative).getByRole('button', { name: 'Als bevorzugt festlegen' }),
    );

    expect(currentOffers()).toEqual([
      expect.objectContaining({ supplier_id: supplierA.id, is_preferred: false }),
      expect.objectContaining({ supplier_id: supplierB.id, is_preferred: true }),
    ]);
  });

  it('keeps more than two offers usable as further sources', async () => {
    render(<Harness initial={[]} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: 'Bezugsquelle hinzufügen' }));
    await user.click(
      screen.getByRole('button', { name: 'Alternative Bezugsquelle hinzufügen' }),
    );
    await user.click(screen.getByRole('button', { name: 'Weitere Bezugsquelle hinzufügen' }));

    expect(screen.getByRole('heading', { name: 'Weitere Bezugsquellen' })).toBeInTheDocument();
    expect(screen.getAllByRole('combobox', { name: 'Lieferant' })).toHaveLength(3);
    expect(currentOffers()).toHaveLength(3);
  });

  it('uses the selected supplier default lead time', async () => {
    render(<Harness initial={[]} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: 'Bezugsquelle hinzufügen' }));
    await user.click(screen.getByRole('combobox', { name: 'Lieferant' }));
    await user.click(screen.getByRole('option', { name: 'Beta Supply' }));

    expect(screen.getByLabelText('Lieferzeit (Tage)')).toHaveValue(12);
    expect(currentOffers()[0]).toEqual(
      expect.objectContaining({ supplier_id: supplierB.id, lead_time_days: 12 }),
    );
  });

  it('keeps an existing inactive supplier snapshot visible', () => {
    const inactiveSupplier = supplier({ id: 9, name: 'Legacy Parts', is_active: false });
    const offer = readOffer({ supplier_id: inactiveSupplier.id, supplier: inactiveSupplier });

    render(
      <ProcurementOffersEditor
        suppliers={[supplierA, supplierB]}
        offers={[offer]}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByRole('combobox', { name: 'Lieferant' })).toHaveTextContent('Legacy Parts');
    expect(screen.getByText('Lieferant deaktiviert')).toBeInTheDocument();
  });

  it('emits immutable controlled changes and preserves the supplier snapshot', async () => {
    const offer = readOffer();
    const onChange = vi.fn();
    render(
      <ProcurementOffersEditor
        suppliers={[supplierA, supplierB]}
        offers={[offer]}
        onChange={onChange}
      />,
    );
    const user = userEvent.setup();

    const sku = screen.getByLabelText('Lieferantenartikelnummer');
    await user.clear(sku);
    await user.type(sku, 'UPDATED');

    const emitted = onChange.mock.calls.at(-1)?.[0] as ProcurementOffer[];
    expect(emitted[0]).not.toBe(offer);
    expect(emitted[0].supplier).toBe(offer.supplier);
    expect(emitted[0].supplier_sku).toBe('UPDATED');
    expect(offer.supplier_sku).toBe('ALPHA-1');
  });

  it('removes new offers and deactivates persisted offers', async () => {
    const user = userEvent.setup();
    const firstRender = render(<Harness initial={[draft({ supplier_id: null })]} />);

    await user.click(screen.getByRole('button', { name: 'Entfernen' }));
    expect(currentOffers()).toEqual([]);

    firstRender.unmount();
    render(<Harness initial={[readOffer()]} />);
    await user.click(screen.getByRole('button', { name: 'Deaktivieren' }));
    expect(currentOffers()[0]).toEqual(expect.objectContaining({ id: 41, is_active: false }));
    expect(screen.getByRole('combobox', { name: 'Lieferant' })).toBeInTheDocument();
  });

  it('promotes the active alternative when the preferred offer is disabled', async () => {
    render(
      <Harness
        initial={[
          draft(),
          draft({ supplier_id: supplierB.id, is_preferred: false }),
        ]}
      />,
    );
    const user = userEvent.setup();

    await user.click(
      within(screen.getByRole('region', { name: 'Bevorzugte Bezugsquelle' }))
        .getByRole('checkbox', { name: 'Aktiv' }),
    );

    expect(currentOffers()).toEqual([
      expect.objectContaining({ is_active: false, is_preferred: false }),
      expect.objectContaining({ is_active: true, is_preferred: true }),
    ]);
  });

  it('makes a new offer preferred after the only persisted offer is deactivated', async () => {
    render(<Harness initial={[readOffer()]} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: 'Deaktivieren' }));
    await user.click(screen.getByRole('button', { name: 'Alternative Bezugsquelle hinzufügen' }));

    expect(currentOffers()).toEqual([
      expect.objectContaining({ id: 41, is_active: false, is_preferred: false }),
      expect.objectContaining({ is_active: true, is_preferred: true }),
    ]);
  });

  it('ignores an already-open supplier option after switching to read-only', async () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <ProcurementOffersEditor
        suppliers={[supplierA, supplierB]}
        offers={[draft()]}
        onChange={onChange}
      />,
    );
    const user = userEvent.setup();

    await user.click(screen.getByRole('combobox', { name: 'Lieferant' }));
    const betaOption = screen.getByRole('option', { name: 'Beta Supply' });
    rerender(
      <ProcurementOffersEditor
        suppliers={[supplierA, supplierB]}
        offers={[draft()]}
        onChange={onChange}
        readOnly
      />,
    );
    await user.click(betaOption);

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('combobox', { name: 'Lieferant' })).toHaveTextContent('Alpha Supply');
  });

  it('renders every shared field disabled and hides mutation actions in read-only mode', () => {
    render(
      <ProcurementOffersEditor
        suppliers={[supplierA, supplierB]}
        offers={[readOffer()]}
        onChange={vi.fn()}
        readOnly
      />,
    );

    expect(screen.getByRole('combobox', { name: 'Lieferant' })).toBeDisabled();
    for (const label of [
      'Lieferantenartikelnummer',
      'Bezugs-URL',
      'Packungsmenge',
      'Packungseinheit',
      'Mindestbestellmenge',
      'Lieferzeit (Tage)',
      'Nettopreis',
      'Bruttopreis',
      'Aktiv',
    ]) {
      expect(screen.getByLabelText(label === 'Packungseinheit' ? /^Packungseinheit/ : label)).toBeDisabled();
    }
    expect(screen.queryByRole('button', { name: /hinzufügen/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Entfernen' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Deaktivieren' })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Als bevorzugt festlegen' }),
    ).not.toBeInTheDocument();
  });
});

describe('procurementOffersApi', () => {
  it('serializes supplier pagination parameters', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [], total: 0, limit: 50, offset: 50 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await suppliersApi.list({ q: 'Schraube', active: true, limit: 50, offset: 50 });

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      '/api/v1/suppliers?q=Schraube&active=true&limit=50&offset=50',
    );
    fetchMock.mockRestore();
  });

  it('serializes only writable offer fields for replacement', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await procurementOffersApi.replace(
      { kind: 'material', small_part_id: 5 },
      [readOffer()],
    );

    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)) as {
      offers: Array<Record<string, unknown>>;
    };
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/procurement-offers/resource');
    expect(body.offers[0]).toEqual(draft({ id: 41 }));
    expect(body.offers[0]).not.toHaveProperty('supplier');
    fetchMock.mockRestore();
  });

  it('omits deactivated drafts from a replacement payload', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await procurementOffersApi.replace(
      { kind: 'material', small_part_id: 5 },
      [readOffer({ is_active: false, supplier: supplier({ is_active: false }) })],
    );

    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)) as {
      offers: unknown[];
    };
    expect(body.offers).toEqual([]);
    fetchMock.mockRestore();
  });
});
