import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CalculationWorkspace } from '../../components/orders/CalculationWorkspace';
import { api } from '../../api/client';
import { calculationsApi } from '../../api/calculations';

vi.mock('../../api/client', () => ({
  ApiError: class ApiError extends Error { status = 409; },
  api: {
    getBusinessProfileOptions: vi.fn(), getSettings: vi.fn(), getPrinters: vi.fn(), getEquipment: vi.fn(), getCustomers: vi.fn(),
  },
}));

vi.mock('../../api/calculations', () => ({
  calculationsApi: { previewBatch: vi.fn(), create: vi.fn(), revisions: vi.fn() },
}));

describe('CalculationWorkspace', () => {
  it('initializes a new calculation from profiles, settings, and managed devices', async () => {
    vi.mocked(api.getBusinessProfileOptions).mockResolvedValue([{ id: 2, name: 'Main', legal_name: 'Main GmbH', country_code: 'DE', default_currency: 'EUR', is_active: true, is_default: true, version: 1 }]);
    vi.mocked(api.getSettings).mockResolvedValue({ calculation_defaults: '{}', default_filament_cost: 25, energy_cost_per_kwh: 0.3 } as never);
    vi.mocked(api.getPrinters).mockResolvedValue([]);
    vi.mocked(api.getEquipment).mockResolvedValue([]);
    vi.mocked(api.getCustomers).mockResolvedValue({ items: [], total: 0, limit: 250, offset: 0 });
    vi.mocked(calculationsApi.previewBatch).mockResolvedValue({ total_runs: 1, material_cost: '0', machine_cost: '0', energy_cost: '0', labor_cost: '0', consumables: '0', packaging: '0', additional_costs: '0', risk_cost: '0', production_cost: '0', shipping: '0', selling_price: '0', net_price: '0', contribution: '0', effective_margin: '0', tax: '0', gross_price: '0', unit_price: '0' });

    render(<CalculationWorkspace calculation={null} locale="en-US" onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByText('Add calculation')).toBeInTheDocument();
    await waitFor(() => expect(api.getCustomers).toHaveBeenCalledWith({ businessProfileId: 2, status: 'active', limit: 250, offset: 0 }));
    expect(screen.getByText(/Request/)).toBeInTheDocument();
    expect(screen.getByText(/Cost & price/)).toBeInTheDocument();
    await waitFor(() => expect(calculationsApi.previewBatch).toHaveBeenCalled());
  });
});
