import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api } from '../../api/client';
import { procurementOffersApi, suppliersApi } from '../../api/procurement';
import { smallPartsApi, type SmallPart } from '../../api/smallParts';
import { SmallPartEditor } from '../../components/warehouse/SmallPartEditor';

vi.mock('../../api/client', () => ({
  api: {
    getLocations: vi.fn(),
    getSettings: vi.fn(),
  },
}));

vi.mock('../../api/smallParts', () => ({
  smallPartsApi: {
    categories: { list: vi.fn() },
    units: { list: vi.fn() },
    create: vi.fn(),
    update: vi.fn(),
  },
}));

vi.mock('../../api/procurement', () => ({
  suppliersApi: { list: vi.fn() },
  procurementOffersApi: { list: vi.fn(), replace: vi.fn() },
}));

const part: SmallPart = {
  id: 7,
  sku: 'MAT-0001',
  name: 'M3 Schraube',
  description: 'Edelstahl',
  search_terms: 'M3 DIN',
  category_id: null,
  unit_code: 'C62',
  location_id: null,
  minimum_stock: '10',
  unit_cost: '0.15',
  supplier_reference: 'ALT-4711',
  default_consumption_reason: 'Montage',
  internal_notes: 'Trocken lagern',
  is_active: true,
  preferred_offer: null,
  category: null,
  unit: { code: 'C62', label: 'Stück', decimal_places: 0, is_active: true },
  balance: { physical: '20', reserved: '0', available: '20', is_low_stock: false },
  created_at: '2026-07-18T10:00:00Z',
  updated_at: '2026-07-18T10:00:00Z',
};

const supplier = {
  id: 3,
  name: 'Schrauben GmbH',
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
  default_lead_time_days: 4,
  internal_notes: null,
  is_active: true,
  created_at: '2026-07-18T10:00:00Z',
  updated_at: '2026-07-18T10:00:00Z',
};

function renderEditor(editorPart: SmallPart | null, onClose = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    onClose,
    ...render(
      <QueryClientProvider client={client}>
        <SmallPartEditor part={editorPart} onClose={onClose} />
      </QueryClientProvider>,
    ),
  };
}

async function chooseUnit(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('combobox', { name: /^Einheit/ }));
  await user.click(screen.getByRole('option', { name: 'Stück' }));
}

describe('SmallPartEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getLocations).mockResolvedValue([]);
    vi.mocked(api.getSettings).mockResolvedValue({ small_parts_default_minimum_stock: '12.5' } as never);
    vi.mocked(smallPartsApi.categories.list).mockResolvedValue([]);
    vi.mocked(smallPartsApi.units.list).mockResolvedValue([
      { code: 'C62', label: 'Stück', decimal_places: 0, is_active: true },
    ]);
    vi.mocked(suppliersApi.list).mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
    vi.mocked(procurementOffersApi.list).mockResolvedValue([]);
    vi.mocked(procurementOffersApi.replace).mockResolvedValue([]);
  });

  it('renders the ForgeDesk-derived material sections with shared controls', async () => {
    renderEditor(null);

    expect(screen.getByRole('dialog', { name: 'Material hinzufügen' })).toHaveClass('max-w-3xl');
    for (const heading of ['Artikel', 'Bestand', 'Beschaffung', 'Verbrauchsgrund', 'Notiz intern']) {
      expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByLabelText('Anfangsmenge')).toBeInTheDocument();
    expect(screen.getByLabelText('Beschreibung')).toBeInTheDocument();
    expect(screen.getByLabelText('Interne Notiz')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Material speichern' })).toBeInTheDocument();
  });

  it('uses the configured default minimum stock for new material', async () => {
    renderEditor(null);

    await waitFor(() => expect(screen.getByLabelText('Mindestbestand')).toHaveValue(12.5));
    expect(screen.getByLabelText(/^Standard-Verbrauchsgrund/)).toHaveValue('Produktion');
  });

  it('preserves manual unit-cost editing without supplier offers', async () => {
    vi.mocked(smallPartsApi.update).mockResolvedValue(part);
    renderEditor(part);
    const user = userEvent.setup();

    const unitCost = screen.getByLabelText('Einzelpreis €');
    expect(unitCost).toHaveValue(0.15);
    await user.clear(unitCost);
    await user.type(unitCost, '0.42');
    await user.click(screen.getByRole('button', { name: 'Material speichern' }));

    await waitFor(() => expect(smallPartsApi.update).toHaveBeenCalledWith(
      part.id,
      expect.objectContaining({ unit_cost: '0.42' }),
    ));
  });

  it('creates material with opening stock and then persists offers', async () => {
    const created = { ...part, id: 42, sku: 'MAT-0042', supplier_reference: null };
    vi.mocked(smallPartsApi.create).mockResolvedValue(created);
    vi.mocked(suppliersApi.list).mockResolvedValue({ items: [supplier], total: 1, limit: 100, offset: 0 });
    const { onClose } = renderEditor(null);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/^Artikelnummer/), 'MAT-0042');
    await user.type(screen.getByLabelText(/^Bezeichnung/), 'Unterlegscheibe');
    await chooseUnit(user);
    await user.clear(screen.getByLabelText('Anfangsmenge'));
    await user.type(screen.getByLabelText('Anfangsmenge'), '25');
    await user.click(await screen.findByRole('button', { name: 'Bezugsquelle hinzufügen' }));
    await user.click(screen.getByRole('combobox', { name: 'Lieferant' }));
    await user.click(screen.getByRole('option', { name: 'Schrauben GmbH' }));
    await user.click(screen.getByRole('button', { name: 'Material speichern' }));

    await waitFor(() => expect(smallPartsApi.create).toHaveBeenCalledWith(expect.objectContaining({
      opening_quantity: '25',
      default_consumption_reason: 'Produktion',
    })));
    expect(procurementOffersApi.replace).toHaveBeenCalledWith(
      { kind: 'material', small_part_id: 42 },
      [expect.objectContaining({ supplier_id: 3, is_preferred: true, lead_time_days: 4 })],
    );
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(vi.mocked(smallPartsApi.create).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(procurementOffersApi.replace).mock.invocationCallOrder[0],
    );
  });

  it('keeps the dialog open and does not create twice when offer persistence fails', async () => {
    vi.mocked(smallPartsApi.create).mockResolvedValue({ ...part, id: 42, supplier_reference: null });
    vi.mocked(procurementOffersApi.replace)
      .mockRejectedValueOnce(new Error('Bezugsquellen konnten nicht gespeichert werden'))
      .mockResolvedValueOnce([]);
    const { onClose } = renderEditor(null);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/^Artikelnummer/), 'MAT-0042');
    await user.type(screen.getByLabelText(/^Bezeichnung/), 'Unterlegscheibe');
    await chooseUnit(user);
    await user.click(screen.getByRole('button', { name: 'Material speichern' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Bezugsquellen konnten nicht gespeichert werden');
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Material speichern' }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(smallPartsApi.create).toHaveBeenCalledTimes(1);
    expect(smallPartsApi.update).toHaveBeenCalledWith(42, expect.not.objectContaining({ opening_quantity: expect.anything() }));
  });

  it('loads existing offers for editing and preserves the legacy supplier reference read-only', async () => {
    const offer = {
      id: 9,
      supplier_id: 3,
      small_part_id: 7,
      filament_sku_settings_id: null,
      resource_key: 'material:7',
      supplier_sku: 'NEU-7',
      purchase_url: '',
      package_quantity: '1',
      package_unit_code: 'C62',
      minimum_order_quantity: '1',
      lead_time_days: 4,
      net_price: '1.2',
      gross_price: '1.43',
      is_preferred: true,
      is_active: true,
      created_at: '2026-07-18T10:00:00Z',
      updated_at: '2026-07-18T10:00:00Z',
      supplier,
    };
    vi.mocked(suppliersApi.list).mockResolvedValue({ items: [offer.supplier], total: 1, limit: 100, offset: 0 });
    vi.mocked(procurementOffersApi.list).mockResolvedValue([offer]);
    renderEditor(part);

    expect(screen.queryByLabelText('Anfangsmenge')).not.toBeInTheDocument();
    const legacy = screen.getByLabelText('Bisherige Lieferantenreferenz');
    expect(legacy).toHaveValue('ALT-4711');
    expect(legacy).toHaveAttribute('readonly');
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Lieferant' })).toHaveTextContent('Schrauben GmbH'));
    expect(procurementOffersApi.list).toHaveBeenCalledWith({ kind: 'material', small_part_id: 7 });
  });

  it('saves core material without replacing loaded offers when suppliers are unavailable', async () => {
    const existingOffer = {
      id: 9,
      supplier_id: supplier.id,
      small_part_id: part.id,
      filament_sku_settings_id: null,
      resource_key: `material:${part.id}`,
      supplier_sku: 'NEU-7',
      purchase_url: '',
      package_quantity: '1',
      package_unit_code: 'C62',
      minimum_order_quantity: '1',
      lead_time_days: 4,
      net_price: '1.2',
      gross_price: '1.43',
      is_preferred: true,
      is_active: true,
      created_at: '2026-07-18T10:00:00Z',
      updated_at: '2026-07-18T10:00:00Z',
      supplier,
    };
    vi.mocked(suppliersApi.list).mockRejectedValue(new Error('Lieferanten offline'));
    vi.mocked(procurementOffersApi.list).mockResolvedValue([existingOffer]);
    vi.mocked(smallPartsApi.update).mockResolvedValue(part);
    const { onClose } = renderEditor(part);
    const user = userEvent.setup();

    expect(await screen.findByText('Schrauben GmbH')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Lieferanten erneut laden' })).toBeInTheDocument();
    await user.clear(screen.getByLabelText(/^Bezeichnung/));
    await user.type(screen.getByLabelText(/^Bezeichnung/), 'M3 Schraube offline');
    await user.click(screen.getByRole('button', { name: 'Material speichern' }));

    await waitFor(() => expect(smallPartsApi.update).toHaveBeenCalledWith(7, expect.objectContaining({ name: 'M3 Schraube offline' })));
    expect(procurementOffersApi.replace).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('loads every supplier page so suppliers beyond the first 50 remain selectable', async () => {
    const firstPage = Array.from({ length: 50 }, (_, index) => ({
      ...supplier,
      id: index + 1,
      name: `Lieferant ${index + 1}`,
    }));
    const lastSupplier = { ...supplier, id: 51, name: 'Lieferant 51' };
    vi.mocked(suppliersApi.list)
      .mockResolvedValueOnce({ items: firstPage, total: 51, limit: 50, offset: 0 })
      .mockResolvedValueOnce({ items: [lastSupplier], total: 51, limit: 50, offset: 50 });
    renderEditor(null);
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Bezugsquelle hinzufügen' }));
    await user.click(screen.getByRole('combobox', { name: 'Lieferant' }));

    expect(screen.getByRole('option', { name: 'Lieferant 51' })).toBeInTheDocument();
    expect(suppliersApi.list).toHaveBeenNthCalledWith(1, { limit: 50, offset: 0 });
    expect(suppliersApi.list).toHaveBeenNthCalledWith(2, { limit: 50, offset: 50 });
  });

  it('updates the material before replacing its edited offers', async () => {
    vi.mocked(smallPartsApi.update).mockResolvedValue(part);
    renderEditor(part);
    const user = userEvent.setup();

    await user.clear(screen.getByLabelText(/^Bezeichnung/));
    await user.type(screen.getByLabelText(/^Bezeichnung/), 'M3 Schraube A2');
    await user.click(screen.getByRole('button', { name: 'Material speichern' }));

    await waitFor(() => expect(smallPartsApi.update).toHaveBeenCalledWith(7, expect.objectContaining({
      name: 'M3 Schraube A2',
      supplier_reference: 'ALT-4711',
    })));
    expect(smallPartsApi.update).toHaveBeenCalledWith(7, expect.not.objectContaining({ opening_quantity: expect.anything() }));
    expect(procurementOffersApi.replace).toHaveBeenCalledWith({ kind: 'material', small_part_id: 7 }, []);
  });
});
