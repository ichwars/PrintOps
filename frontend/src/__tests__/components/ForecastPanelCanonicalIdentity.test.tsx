import { afterEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ForecastPanel } from '../../components/ForecastPanel';
import { setAuthToken, type InventorySpool } from '../../api/client';
import { server } from '../mocks/server';
import { render } from '../utils';

const policy = {
  id: 41, material: 'PLA', subtype: null, brand: 'Poly', color_name: 'Black',
  material_number: 'MAT00017', default_supplier_id: null,
  lead_time_days: 21, safety_margin_value: 500, safety_margin_unit: 'g', alerts_snoozed: true,
};

function setup(brand: string, identity: Partial<InventorySpool> = {}) {
  const spool = {
    id: 1, material: 'PLA', subtype: null, brand, color_name: 'Black', rgba: '111111FF',
    material_number: 'MAT00017', label_weight: 1000, core_weight: 250, weight_used: 200,
    weight_used_baseline: 0, archived_at: null, created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z', category: 'Active', k_profiles: [], ...identity,
  } as InventorySpool;
  let loaded = false;
  setAuthToken('test-token', 'session');
  server.use(
    http.get('*/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
    http.get('*/api/v1/auth/me', () => HttpResponse.json({ id: 1, username: 'reviewer', is_admin: false,
      permissions: ['inventory:forecast_read', 'inventory:forecast_write'] })),
    http.get('*/api/v1/settings/', () => HttpResponse.json({ forecast_global_lead_time_days: 7 })),
    http.get('*/api/v1/inventory/sku-settings', () => { loaded = true; return HttpResponse.json([policy]); }),
    http.get(/\/api\/v1\/inventory\/usage/, () => HttpResponse.json([])),
    http.get('*/api/v1/inventory/shopping-list', () => HttpResponse.json([])),
  );
  render(<ForecastPanel spools={[spool]} />);
  return async () => {
    await waitFor(() => expect(loaded).toBe(true));
    await userEvent.setup().click(await screen.findByRole('button', { name: /expand$/ }));
    return screen.getByRole('textbox', { name: 'Material number' });
  };
}

afterEach(() => { server.resetHandlers(); setAuthToken(null); });

describe('ForecastPanel canonical filament identity', () => {
  it.each(['Poly', ' Poly '])('retains configured identity and policy for brand %s', async (brand) => {
    const expand = setup(brand);
    const number = await expand();
    await waitFor(() => expect(number).toHaveValue('MAT00017'));
    expect(screen.getByText('21d')).toBeInTheDocument();
  });

  it('matches trimmed material/color and empty subtype to the canonical policy', async () => {
    const number = await setup(' Poly ', { material: ' PLA ', subtype: '', color_name: ' Black ' })();
    await waitFor(() => expect(number).toHaveValue('MAT00017'));
    expect(screen.getByText('21d')).toBeInTheDocument();
  });

  it('preserves the canonical policy when changing only a material number', async () => {
    let saved: unknown;
    server.use(http.post('*/api/v1/inventory/sku-settings', async ({ request }) => {
      saved = await request.json();
      return HttpResponse.json({ ...policy, material_number: 'MAT00099' });
    }));
    const number = await setup(' Poly ')();
    fireEvent.change(number, { target: { value: 'MAT00099' } });
    fireEvent.blur(number);
    await waitFor(() => expect(saved).toBeDefined());
    expect(saved).toMatchObject({
      lead_time_days: 21, safety_margin_value: 500, safety_margin_unit: 'g', alerts_snoozed: true,
    });
  });
});
