import { afterEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { setAuthToken, type InventorySpool } from '../../api/client';
import { ForecastPanel } from '../../components/ForecastPanel';
import { server } from '../mocks/server';
import { render } from '../utils';

const supplier = {
  id: 7,
  name: 'Filament World',
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
  created_at: '2026-07-19T10:00:00Z',
  updated_at: '2026-07-19T10:00:00Z',
};

const preferredOffer = {
  id: 19,
  supplier_id: supplier.id,
  supplier_sku: 'PLA-MATTE-BLK',
  purchase_url: 'https://example.test/pla-matte-black',
  package_quantity: '1.000000',
  package_unit_code: 'C62',
  minimum_order_quantity: '1.000000',
  lead_time_days: 4,
  net_price: '18.500000',
  gross_price: '22.015000',
  is_preferred: true,
  is_active: true,
  small_part_id: null,
  filament_sku_settings_id: 12,
  resource_key: 'filament:PLA:Matte:Poly:Black',
  created_at: '2026-07-19T10:00:00Z',
  updated_at: '2026-07-19T10:00:00Z',
  supplier,
};

const spool: InventorySpool = {
  id: 1,
  material: 'PLA',
  subtype: 'Matte',
  brand: 'Poly',
  color_name: 'Black',
  rgba: '111111FF',
  label_weight: 1000,
  core_weight: 250,
  core_weight_catalog_id: null,
  weight_used: 200,
  slicer_filament: null,
  slicer_filament_name: null,
  nozzle_temp_min: null,
  nozzle_temp_max: null,
  note: null,
  added_full: null,
  last_used: null,
  encode_time: null,
  tag_uid: null,
  tray_uuid: null,
  data_origin: 'manual',
  tag_type: null,
  archived_at: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
  k_profiles: [],
  cost_per_kg: null,
  last_scale_weight: null,
  last_weighed_at: null,
  weight_locked: false,
  category: 'Active',
  low_stock_threshold_pct: null,
};

function mockForecastApis() {
  server.use(
    http.get('*/api/v1/settings/', () => HttpResponse.json({ forecast_global_lead_time_days: 7 })),
    http.get('*/api/v1/inventory/sku-settings', () => HttpResponse.json([])),
    http.get(/\/api\/v1\/inventory\/usage/, () => HttpResponse.json([])),
    http.get('*/api/v1/inventory/shopping-list', () => HttpResponse.json([])),
  );
}

function mockPermissions(permissions: string[]) {
  setAuthToken('test-token', 'session');
  server.use(
    http.get('*/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
    http.get('*/api/v1/auth/me', () => HttpResponse.json({
      id: 1,
      username: 'viewer',
      is_admin: false,
      permissions,
    })),
  );
}

afterEach(() => {
  server.resetHandlers();
  setAuthToken(null);
});

describe('ForecastPanel filament procurement', () => {
  it('loads and saves offers with the complete four-field SKU identity', async () => {
    mockPermissions(['inventory:forecast_read', 'inventory:read', 'inventory:update']);
    mockForecastApis();
    let listedIdentity: Record<string, string | null> | undefined;
    let replacement: unknown;
    const supplierOffsets: number[] = [];
    const firstSupplierPage = Array.from({ length: 50 }, (_, index) => ({
      ...supplier,
      id: 100 + index,
      name: `Supplier ${index + 1}`,
    }));
    server.use(
      http.get('*/api/v1/procurement-offers', ({ request }) => {
        const url = new URL(request.url);
        listedIdentity = {
          kind: url.searchParams.get('kind'),
          material: url.searchParams.get('material'),
          subtype: url.searchParams.get('subtype'),
          brand: url.searchParams.get('brand'),
          color_name: url.searchParams.get('color_name'),
        };
        return HttpResponse.json([preferredOffer]);
      }),
      http.get('*/api/v1/suppliers', ({ request }) => {
        const offset = Number(new URL(request.url).searchParams.get('offset'));
        supplierOffsets.push(offset);
        return HttpResponse.json({
          items: offset === 0 ? firstSupplierPage : [supplier],
          total: 51,
          limit: 50,
          offset,
        });
      }),
      http.put('*/api/v1/procurement-offers/resource', async ({ request }) => {
        replacement = await request.json();
        return HttpResponse.json([preferredOffer]);
      }),
    );

    const user = userEvent.setup();
    render(<ForecastPanel spools={[spool]} />);
    await user.click(await screen.findByRole('button', { name: 'Poly PLA Matte Black expand' }));

    const procurementHeading = await screen.findByRole('heading', { name: 'Procurement' });
    expect(procurementHeading).toBeInTheDocument();
    const procurementSection = procurementHeading.closest('section');
    expect(procurementSection).not.toHaveClass('border-t');
    expect(procurementSection?.querySelectorAll('.h-px')).toHaveLength(1);
    expect(await screen.findByText('Filament World')).toBeInTheDocument();
    expect(supplierOffsets).toEqual([0, 50]);
    expect(listedIdentity).toEqual({
      kind: 'filament', material: 'PLA', subtype: 'Matte', brand: 'Poly', color_name: 'Black',
    });

    await user.click(screen.getByRole('button', { name: 'Save procurement sources' }));
    await waitFor(() => expect(screen.getByText('Procurement sources saved')).toBeInTheDocument());
    expect(replacement).toMatchObject({
      resource: {
        kind: 'filament', material: 'PLA', subtype: 'Matte', brand: 'Poly', color_name: 'Black',
      },
      offers: [{ id: 19, supplier_id: 7, is_preferred: true }],
    });
  });

  it('shows saved offers without supplier or mutation requests for read-only users', async () => {
    mockPermissions(['inventory:forecast_read', 'inventory:read']);
    mockForecastApis();
    let supplierRequests = 0;
    let replacements = 0;
    server.use(
      http.get('*/api/v1/procurement-offers', () => HttpResponse.json([preferredOffer])),
      http.get('*/api/v1/suppliers', () => {
        supplierRequests += 1;
        return HttpResponse.json({ items: [supplier], total: 1, limit: 50, offset: 0 });
      }),
      http.put('*/api/v1/procurement-offers/resource', () => {
        replacements += 1;
        return HttpResponse.json([preferredOffer]);
      }),
    );

    const user = userEvent.setup();
    render(<ForecastPanel spools={[spool]} />);
    await user.click(await screen.findByRole('button', { name: 'Poly PLA Matte Black expand' }));

    expect(await screen.findByText('Filament World')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save procurement sources' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Bezugsquelle hinzufügen/ })).not.toBeInTheDocument();
    expect(supplierRequests).toBe(0);
    expect(replacements).toBe(0);
  });

  it('keeps loaded offers visible and disables saving while suppliers are unavailable', async () => {
    mockPermissions(['inventory:forecast_read', 'inventory:read', 'inventory:update']);
    mockForecastApis();
    server.use(
      http.get('*/api/v1/procurement-offers', () => HttpResponse.json([preferredOffer])),
      http.get('*/api/v1/suppliers', () => new HttpResponse(null, { status: 503 })),
    );

    const user = userEvent.setup();
    render(<ForecastPanel spools={[spool]} />);
    await user.click(await screen.findByRole('button', { name: 'Poly PLA Matte Black expand' }));

    expect(await screen.findByText('Filament World')).toBeInTheDocument();
    expect(await screen.findByRole('alert')).toHaveTextContent('Suppliers could not be loaded');
    expect(screen.queryByRole('button', { name: 'Save procurement sources' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry suppliers' })).toBeInTheDocument();
  });

  it('does not expose procurement or call its APIs with forecast-write permission alone', async () => {
    mockPermissions(['inventory:forecast_read', 'inventory:forecast_write']);
    mockForecastApis();
    let offerRequests = 0;
    let supplierRequests = 0;
    let replacements = 0;
    server.use(
      http.get('*/api/v1/procurement-offers', () => {
        offerRequests += 1;
        return HttpResponse.json([preferredOffer]);
      }),
      http.get('*/api/v1/suppliers', () => {
        supplierRequests += 1;
        return HttpResponse.json({ items: [supplier], total: 1, limit: 50, offset: 0 });
      }),
      http.put('*/api/v1/procurement-offers/resource', () => {
        replacements += 1;
        return HttpResponse.json([preferredOffer]);
      }),
    );

    const user = userEvent.setup();
    render(<ForecastPanel spools={[spool]} />);
    await user.click(await screen.findByRole('button', { name: 'Poly PLA Matte Black expand' }));
    expect(await screen.findByText('Effective Lead Time')).toBeInTheDocument();

    expect(screen.queryByRole('heading', { name: 'Procurement' })).not.toBeInTheDocument();
    expect(offerRequests).toBe(0);
    expect(supplierRequests).toBe(0);
    expect(replacements).toBe(0);
  });

  it('locks procurement drafts while a replacement is pending', async () => {
    mockPermissions(['inventory:forecast_read', 'inventory:read', 'inventory:update']);
    mockForecastApis();
    let releaseSave: (() => void) | undefined;
    let saveStarted = false;
    const saveGate = new Promise<void>((resolve) => {
      releaseSave = resolve;
    });
    server.use(
      http.get('*/api/v1/procurement-offers', () => HttpResponse.json([preferredOffer])),
      http.get('*/api/v1/suppliers', () => HttpResponse.json({
        items: [supplier], total: 1, limit: 50, offset: 0,
      })),
      http.put('*/api/v1/procurement-offers/resource', async () => {
        saveStarted = true;
        await saveGate;
        return HttpResponse.json([preferredOffer]);
      }),
    );

    const user = userEvent.setup();
    render(<ForecastPanel spools={[spool]} />);
    await user.click(await screen.findByRole('button', { name: 'Poly PLA Matte Black expand' }));
    const supplierSku = await screen.findByRole('textbox', { name: 'Lieferantenartikelnummer' });
    await user.click(screen.getByRole('button', { name: 'Save procurement sources' }));
    await waitFor(() => expect(saveStarted).toBe(true));

    expect(supplierSku).toBeDisabled();
    await user.type(supplierSku, '-CHANGED');
    expect(supplierSku).toHaveValue('PLA-MATTE-BLK');

    releaseSave?.();
    await waitFor(() => expect(screen.getByText('Procurement sources saved')).toBeInTheDocument());
  });
});
