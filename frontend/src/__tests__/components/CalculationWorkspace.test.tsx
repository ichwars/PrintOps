import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CalculationWorkspace } from '../../components/orders/CalculationWorkspace';
import { api } from '../../api/client';
import { calculationsApi, type CalculationDetail } from '../../api/calculations';

vi.mock('../../api/client', () => ({
  ApiError: class ApiError extends Error { status = 409; },
  api: {
    getBusinessProfileOptions: vi.fn(), getSettings: vi.fn(), getPrinters: vi.fn(), getEquipment: vi.fn(), getCustomers: vi.fn(), getProjects: vi.fn(), getSpools: vi.fn(),
  },
}));

vi.mock('../../api/calculations', () => ({
  calculationsApi: {
    previewBatch: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(),
    revisions: vi.fn(), effectiveDefaults: vi.fn(), availabilityPreview: vi.fn(),
    uploadProjectFile: vi.fn(), projectFiles: vi.fn(),
  },
}));

const existingDraft: CalculationDetail = {
  id: 42,
  business_profile_id: 2,
  customer_id: null,
  project_id: null,
  request_kind: 'single',
  quantity: 1,
  position_description: null,
  special_terms: null,
  commercial_overrides: {},
  customer_display_name: null,
  business_profile_name: 'Main',
  title: 'bracket',
  status: 'draft',
  currency: 'EUR',
  notes: null,
  version: 1,
  created_at: '2026-07-18T12:00:00Z',
  updated_at: '2026-07-18T12:00:00Z',
  variants: [{
    name: 'Standard', is_preferred: true, sort_order: 0,
    price_method: 'target_margin', price_rate: '0.35',
    lines: [], operations: [], plates: [], small_parts: [],
  }],
  current_revision: null,
  production_cost: null,
  selling_price: null,
};

const uploadedProjectFile = {
  id: 7, calculation_id: 42, revision_number: 1, original_filename: 'bracket.3mf',
  sha256: 'abc', size_bytes: 3, analysis_status: 'completed' as const, analysis_error: null,
  printer_metadata: {}, created_at: '2026-07-18T12:00:00Z', plates: [],
};

function mockWorkspaceDependencies() {
  vi.clearAllMocks();
  vi.mocked(api.getBusinessProfileOptions).mockResolvedValue([{ id: 2, name: 'Main', legal_name: 'Main GmbH', country_code: 'DE', default_currency: 'EUR', is_active: true, is_default: true, version: 1 }]);
  vi.mocked(api.getSettings).mockResolvedValue({ calculation_defaults: '{}', default_filament_cost: 25, energy_cost_per_kwh: 0.3 } as never);
  vi.mocked(api.getPrinters).mockResolvedValue([]);
  vi.mocked(api.getEquipment).mockResolvedValue([]);
  vi.mocked(api.getCustomers).mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 });
  vi.mocked(api.getProjects).mockResolvedValue([]);
  vi.mocked(api.getSpools).mockResolvedValue([]);
  vi.mocked(calculationsApi.effectiveDefaults).mockResolvedValue({});
  vi.mocked(calculationsApi.availabilityPreview).mockResolvedValue({ lines: [], reservation_state: 'not_reserved', checked_at: '2026-07-18T12:00:00Z' });
  vi.mocked(calculationsApi.projectFiles).mockResolvedValue([]);
  vi.mocked(calculationsApi.revisions).mockResolvedValue([]);
  vi.mocked(calculationsApi.previewBatch).mockResolvedValue({ total_runs: 0, material_cost: '0', material_markup: '0', machine_cost: '0', energy_cost: '0', labor_cost: '0', consumables: '0', packaging: '0', additional_costs: '0', additive_materials: '0', scrap_cost: '0', risk_cost: '0', production_cost: '0', shipping: '0', selling_price: '0', net_price: '0', contribution: '0', effective_margin: '0', tax: '0', gross_price: '0', unit_price: '0', breakdown: [] });
}

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
    vi.mocked(calculationsApi.availabilityPreview).mockResolvedValue({ lines: [], reservation_state: 'not_reserved', checked_at: '2026-07-18T12:00:00Z' });
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
    expect(screen.getByRole('heading', { name: '4. Materials' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '5. Labor & post-processing' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '6. Costs & prices' })).toBeInTheDocument();
    expect(screen.getByText('Project')).toBeInTheDocument();
    expect(screen.getByText('No materials selected.')).toBeInTheDocument();
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

  it('auto-saves a new draft before uploading its first 3MF project file', async () => {
    vi.mocked(api.getBusinessProfileOptions).mockResolvedValue([{ id: 2, name: 'Main', legal_name: 'Main GmbH', country_code: 'DE', default_currency: 'EUR', is_active: true, is_default: true, version: 1 }]);
    vi.mocked(api.getSettings).mockResolvedValue({ calculation_defaults: '{}', default_filament_cost: 25, energy_cost_per_kwh: 0.3 } as never);
    vi.mocked(api.getPrinters).mockResolvedValue([]);
    vi.mocked(api.getEquipment).mockResolvedValue([]);
    vi.mocked(api.getCustomers).mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 });
    vi.mocked(api.getProjects).mockResolvedValue([]);
    vi.mocked(api.getSpools).mockResolvedValue([]);
    vi.mocked(calculationsApi.effectiveDefaults).mockResolvedValue({});
    vi.mocked(calculationsApi.availabilityPreview).mockResolvedValue({ lines: [], reservation_state: 'not_reserved', checked_at: '2026-07-18T12:00:00Z' });
    vi.mocked(calculationsApi.projectFiles).mockResolvedValue([]);
    vi.mocked(calculationsApi.revisions).mockResolvedValue([]);
    vi.mocked(calculationsApi.create).mockResolvedValue({ id: 42, status: 'draft', version: 1, title: 'bracket' } as never);
    vi.mocked(calculationsApi.uploadProjectFile).mockResolvedValue({ id: 7, calculation_id: 42, revision_number: 1, original_filename: 'bracket.3mf', sha256: 'abc', size_bytes: 3, analysis_status: 'completed', analysis_error: null, printer_metadata: {}, created_at: '2026-07-18T12:00:00Z', plates: [] });

    render(<CalculationWorkspace calculation={null} locale="en-US" onClose={vi.fn()} onSaved={vi.fn()} />);
    await waitFor(() => expect(api.getCustomers).toHaveBeenCalledWith({ businessProfileId: 2, status: 'active', limit: 200, offset: 0 }));

    expect(screen.getByRole('button', { name: 'Choose file' })).toBeEnabled();
    const file = new File(['3mf'], 'bracket.3mf', { type: 'model/3mf' });
    const input = document.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    fireEvent.change(input!, { target: { files: [file] } });

    await waitFor(() => expect(calculationsApi.create).toHaveBeenCalledWith(expect.objectContaining({ business_profile_id: 2, title: 'bracket' })));
    expect(calculationsApi.uploadProjectFile).toHaveBeenCalledWith(42, file);
  });

  it.each([
    ['Cancel', () => screen.getByRole('button', { name: 'Cancel' })],
    ['Close', () => screen.getByRole('button', { name: 'Close' })],
  ])('discards an upload-only draft through %s without confirmation', async (_label, closeControl) => {
    mockWorkspaceDependencies();
    vi.mocked(calculationsApi.create).mockResolvedValue(existingDraft);
    vi.mocked(calculationsApi.uploadProjectFile).mockResolvedValue(uploadedProjectFile);
    vi.mocked(calculationsApi.remove).mockResolvedValue(undefined);
    const confirm = vi.spyOn(window, 'confirm');
    const onSaved = vi.fn();
    render(<CalculationWorkspace calculation={null} locale="en-US" onClose={vi.fn()} onSaved={onSaved} />);
    await waitFor(() => expect(api.getCustomers).toHaveBeenCalled());

    const file = new File(['3mf'], 'bracket.3mf', { type: 'model/3mf' });
    fireEvent.change(document.querySelector<HTMLInputElement>('input[type="file"]')!, { target: { files: [file] } });
    await waitFor(() => expect(calculationsApi.uploadProjectFile).toHaveBeenCalledWith(42, file));
    fireEvent.click(closeControl());

    await waitFor(() => expect(calculationsApi.remove).toHaveBeenCalledWith(42, 1));
    expect(confirm).not.toHaveBeenCalled();
    expect(onSaved).toHaveBeenCalledTimes(1);
    confirm.mockRestore();
  });

  it('keeps the upload-only draft open when automatic deletion fails', async () => {
    mockWorkspaceDependencies();
    vi.mocked(calculationsApi.create).mockResolvedValue(existingDraft);
    vi.mocked(calculationsApi.uploadProjectFile).mockResolvedValue(uploadedProjectFile);
    vi.mocked(calculationsApi.remove).mockRejectedValue(new Error('Delete failed'));
    const onSaved = vi.fn();
    render(<CalculationWorkspace calculation={null} locale="en-US" onClose={vi.fn()} onSaved={onSaved} />);
    await waitFor(() => expect(api.getCustomers).toHaveBeenCalled());
    fireEvent.change(document.querySelector<HTMLInputElement>('input[type="file"]')!, { target: { files: [new File(['3mf'], 'bracket.3mf')] } });
    await waitFor(() => expect(calculationsApi.uploadProjectFile).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(await screen.findByText('Delete failed')).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'bracket' })).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('stops treating an upload-only draft as temporary after explicit save', async () => {
    mockWorkspaceDependencies();
    vi.mocked(calculationsApi.create).mockResolvedValue(existingDraft);
    vi.mocked(calculationsApi.update).mockResolvedValue(existingDraft);
    vi.mocked(calculationsApi.uploadProjectFile).mockResolvedValue(uploadedProjectFile);
    const onClose = vi.fn();
    const onSaved = vi.fn();
    render(<CalculationWorkspace calculation={null} locale="en-US" onClose={onClose} onSaved={onSaved} />);
    await waitFor(() => expect(api.getCustomers).toHaveBeenCalled());
    fireEvent.change(document.querySelector<HTMLInputElement>('input[type="file"]')!, { target: { files: [new File(['3mf'], 'bracket.3mf')] } });
    await waitFor(() => expect(calculationsApi.uploadProjectFile).toHaveBeenCalled());

    fireEvent.click(screen.getAllByRole('button', { name: 'Save' }).at(-1)!);
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(calculationsApi.remove).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes an existing draft without deleting it', () => {
    mockWorkspaceDependencies();
    const onClose = vi.fn();
    render(<CalculationWorkspace calculation={existingDraft} locale="en-US" onClose={onClose} onSaved={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(calculationsApi.remove).not.toHaveBeenCalled();
  });

  it('confirms deletion for an existing draft and hides delete for approved calculations', async () => {
    mockWorkspaceDependencies();
    vi.mocked(calculationsApi.remove).mockResolvedValue(undefined);
    const onSaved = vi.fn();
    const view = render(<CalculationWorkspace calculation={existingDraft} locale="en-US" onClose={vi.fn()} onSaved={onSaved} />);

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    const confirmation = screen.getByRole('dialog', { name: 'Delete calculation?' });
    expect(confirmation).toHaveTextContent('project files will be permanently removed');
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(calculationsApi.remove).toHaveBeenCalledWith(42, 1));
    expect(onSaved).toHaveBeenCalledTimes(1);

    view.unmount();
    mockWorkspaceDependencies();
    render(<CalculationWorkspace calculation={{ ...existingDraft, status: 'approved', version: 2 }} locale="en-US" onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Archive' })).toBeInTheDocument();
  });

  it('keeps manual deletion retryable after an API error', async () => {
    mockWorkspaceDependencies();
    vi.mocked(calculationsApi.remove).mockRejectedValueOnce(new Error('Delete failed')).mockResolvedValueOnce(undefined);
    const onSaved = vi.fn();
    render(<CalculationWorkspace calculation={existingDraft} locale="en-US" onClose={vi.fn()} onSaved={onSaved} />);

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    let confirmation = screen.getByRole('dialog', { name: 'Delete calculation?' });
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('Delete failed')).toBeInTheDocument();
    confirmation = screen.getByRole('dialog', { name: 'Delete calculation?' });
    await waitFor(() => expect(within(confirmation).getByRole('button', { name: 'Delete' })).toBeEnabled());

    fireEvent.click(within(confirmation).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(calculationsApi.remove).toHaveBeenCalledTimes(2));
    expect(onSaved).toHaveBeenCalledTimes(1);
  });
});
