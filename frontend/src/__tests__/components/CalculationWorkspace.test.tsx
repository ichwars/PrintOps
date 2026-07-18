import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CalculationWorkspace } from '../../components/orders/CalculationWorkspace';
import { api } from '../../api/client';
import { calculationsApi } from '../../api/calculations';

vi.mock('../../api/client', () => ({
  ApiError: class ApiError extends Error { status = 409; },
  api: {
    getBusinessProfileOptions: vi.fn(), getSettings: vi.fn(), getPrinters: vi.fn(), getEquipment: vi.fn(), getCustomers: vi.fn(), getProjects: vi.fn(), getSpools: vi.fn(),
  },
}));

vi.mock('../../api/calculations', () => ({
  calculationsApi: { previewBatch: vi.fn(), create: vi.fn(), revisions: vi.fn(), effectiveDefaults: vi.fn() },
}));

describe('CalculationWorkspace', () => {
  it('initializes a new calculation from profiles, settings, and managed devices', async () => {
    vi.mocked(api.getBusinessProfileOptions).mockResolvedValue([{ id: 2, name: 'Main', legal_name: 'Main GmbH', country_code: 'DE', default_currency: 'EUR', is_active: true, is_default: true, version: 1 }]);
    vi.mocked(api.getSettings).mockResolvedValue({ calculation_defaults: '{invalid', default_filament_cost: 25, energy_cost_per_kwh: 0.3 } as never);
    vi.mocked(api.getPrinters).mockResolvedValue([]);
    vi.mocked(api.getEquipment).mockResolvedValue([]);
    vi.mocked(api.getCustomers).mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 });
    vi.mocked(api.getProjects).mockResolvedValue([]);
    vi.mocked(api.getSpools).mockResolvedValue([]);
    vi.mocked(calculationsApi.effectiveDefaults).mockResolvedValue({ setup_hours: { value: '0.3', source: 'setting' } });
    vi.mocked(calculationsApi.previewBatch).mockResolvedValue({ total_runs: 1, material_cost: '0', material_markup: '0', machine_cost: '0', energy_cost: '0', labor_cost: '0', consumables: '0', packaging: '0', additional_costs: '0', additive_materials: '0', scrap_cost: '0', risk_cost: '0', production_cost: '0', shipping: '0', selling_price: '0', net_price: '0', contribution: '0', effective_margin: '0', tax: '0', gross_price: '0', unit_price: '0', breakdown: [] });

    const onSaved = vi.fn();
    vi.mocked(calculationsApi.create).mockResolvedValue({} as never);
    render(<CalculationWorkspace calculation={null} locale="en-US" onClose={vi.fn()} onSaved={onSaved} />);
    expect(screen.getByText('Add calculation')).toBeInTheDocument();
    const dialog = screen.getByRole('dialog', { name: 'Add calculation' });
    expect(dialog).toHaveClass('flex', 'max-h-full', 'overflow-hidden');
    expect(dialog.parentElement).toHaveClass('flex', 'items-center', 'overflow-hidden');
    expect(screen.getByTestId('calculation-scroll-viewport')).toHaveClass(
      'min-h-0',
      'flex-1',
      'overflow-y-auto',
    );
    expect(dialog.querySelector('header')).toHaveClass('shrink-0');
    expect(dialog.querySelector('header')).not.toHaveClass('sticky');
    await waitFor(() => expect(api.getCustomers).toHaveBeenCalledWith({ businessProfileId: 2, status: 'active', limit: 200, offset: 0 }));
    expect(screen.getByRole('heading', { name: '1. Request' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '3. Project file' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '4. Small parts' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '5. Labor & post-processing' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '6. Costs & prices' })).toBeInTheDocument();
    expect(screen.getByText('Project')).toBeInTheDocument();
    expect(screen.getByText('No small parts selected.')).toBeInTheDocument();
    expect(screen.getByText('Cost breakdown')).toBeInTheDocument();
    expect(screen.getByText('Price decision')).toBeInTheDocument();
    expect(screen.getByLabelText('Create offer draft')).toBeDisabled();
    expect(screen.getByLabelText('Create print order')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(calculationsApi.create).toHaveBeenCalled());
    expect(onSaved).toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText(/Material markup %/), { target: { value: '12' } });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
    expect(confirm).toHaveBeenCalled();
    expect(calculationsApi.previewBatch).not.toHaveBeenCalled();
  });
});
