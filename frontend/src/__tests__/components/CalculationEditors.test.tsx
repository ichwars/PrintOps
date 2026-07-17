import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { CalculationCreate, CalculationPreview } from '../../api/calculations';
import { CommercialOverridesEditor } from '../../components/orders/calculation/CommercialOverridesEditor';
import { CostBreakdown } from '../../components/orders/calculation/CostBreakdown';
import { DeviceAssignmentEditor } from '../../components/orders/calculation/DeviceAssignmentEditor';
import { MaterialsEditor } from '../../components/orders/calculation/MaterialsEditor';
import { PriceDecision } from '../../components/orders/calculation/PriceDecision';
import { RequestEditor } from '../../components/orders/calculation/RequestEditor';
import { selectComboboxOption } from '../utils';

const draft = {
  business_profile_id: 1,
  customer_id: null,
  project_id: null,
  request_kind: 'single',
  quantity: 1,
  title: 'Test print',
  position_description: null,
  special_terms: null,
  currency: 'EUR',
  commercial_overrides: {},
  lines: [],
  variants: [],
} satisfies CalculationCreate;

const preview = {
  total_runs: 1,
  material_cost: '10', material_markup: '1', machine_cost: '2', energy_cost: '3', labor_cost: '4',
  consumables: '5', packaging: '6', additional_costs: '7', additive_materials: '8', scrap_cost: '9',
  risk_cost: '10', production_cost: '58', shipping: '11', selling_price: '80', net_price: '80',
  contribution: '22', effective_margin: '0.275', tax: '15.2', gross_price: '95.2', unit_price: '80',
  breakdown: [{ code: 'machine', label: 'Machine', basis: '2 h × €1', amount: '2' }],
} satisfies CalculationPreview;

describe('calculation editors', () => {
  it('updates request metadata through all select and text controls', () => {
    const onChange = vi.fn();
    const { rerender } = render(<RequestEditor draft={draft} profiles={[{ id: 1, name: 'Main', legal_name: 'Main GmbH', country_code: 'DE', default_currency: 'EUR', is_active: true, is_default: true, version: 1 }]} customers={[{ id: 2, display_name: 'Customer', account_number: 'C-2' } as never]} projects={[{ id: 3, name: 'Project' } as never]} locale="de-DE" onChange={onChange} />);
    selectComboboxOption(screen.getByLabelText('Kunde'), /C-2 · Customer/);
    selectComboboxOption(screen.getByLabelText('Projektbezug'), 'Project');
    selectComboboxOption(screen.getByLabelText('Druckart'), 'Serie');
    fireEvent.change(screen.getByLabelText('Gesamtstückzahl'), { target: { value: '4' } });
    fireEvent.change(screen.getByLabelText('Positionstitel'), { target: { value: 'Series' } });
    fireEvent.change(screen.getByLabelText('Positionsbeschreibung'), { target: { value: 'Description' } });
    fireEvent.change(screen.getByLabelText('Notizen / gesonderte Absprachen'), { target: { value: 'Terms' } });
    expect(onChange).toHaveBeenCalledTimes(7);
    rerender(<RequestEditor draft={{ ...draft, customer_id: 2, project_id: 3 }} profiles={[]} customers={[]} projects={[]} locale="en-US" onChange={onChange} />);
    selectComboboxOption(screen.getByLabelText('Customer'), 'No customer');
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: '' } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ position_description: null }));
  });

  it('adds, updates, selects, and removes additional material', () => {
    const onChange = vi.fn();
    const { rerender } = render(<MaterialsEditor lines={[]} spools={[]} locale="en-US" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'Material' }));
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ kind: 'material' })]);
    const lines = [{ kind: 'material', description: 'Manual', quantity: '1', unit_code: 'C62', unit_price: '2', sort_order: 0 }] as CalculationCreate['lines'];
    rerender(<MaterialsEditor lines={lines} spools={[{ id: 9, brand: 'ACME', material: 'PLA', color_name: 'Black', cost_per_kg: 20 } as never]} locale="en-US" onChange={onChange} />);
    selectComboboxOption(screen.getByLabelText('Inventory material'), 'ACME · PLA · Black');
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ description: 'ACME · PLA · Black', unit_code: 'GRM', unit_price: '0.02' })]);
    fireEvent.change(screen.getByLabelText('Material description'), { target: { value: 'Screw' } });
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('Unit cost'), { target: { value: '0.5' } });
    fireEvent.click(screen.getByLabelText('Remove material'));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it('converts percentage overrides, resets values, and renders pricing details', () => {
    const onChange = vi.fn(); const onReset = vi.fn();
    render(<><CommercialOverridesEditor values={{ material_markup_rate: '0.1' }} locale="en-US" onChange={onChange} onReset={onReset} /><CostBreakdown preview={preview} locale="en-US" currency="EUR" /><PriceDecision preview={preview} locale="en-US" currency="EUR" /></>);
    fireEvent.change(screen.getByLabelText('Material markup %'), { target: { value: '25' } });
    expect(onChange).toHaveBeenCalledWith({ material_markup_rate: '0.25' });
    fireEvent.change(screen.getByLabelText('Material markup %'), { target: { value: '' } });
    expect(onChange).toHaveBeenLastCalledWith({});
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
    expect(onReset).toHaveBeenCalled();
    expect(screen.getByText('2 h × €1')).toBeInTheDocument();
    expect(screen.getByText('27.5 %')).toBeInTheDocument();
    expect(screen.getByText('€95.20')).toBeInTheDocument();
  });

  it('shows empty calculation states without a preview', () => {
    render(<><CostBreakdown preview={null} locale="de-DE" currency="EUR" /><PriceDecision preview={null} locale="de-DE" currency="EUR" /></>);
    expect(screen.getByText('Vollständige Produktionswerte eingeben.')).toBeInTheDocument();
    expect(screen.getAllByText('–')).toHaveLength(6);
  });

  it('keeps an explicit no-device assignment instead of restoring defaults', () => {
    const onChange = vi.fn();
    const operation = { kind: 'printing', title: 'Print', good_parts: 1, parts_per_run: 1, scrap_runs: 0, material_grams_per_run: '1', print_hours_per_run: '1', provenance: { printer_id: null, dryer_id: null }, sort_order: 0, labor: [] } as never;
    render(<DeviceAssignmentEditor operation={operation} printers={[{ id: 7, name: 'Default', is_active: true } as never]} dryers={[{ id: 8, name: 'Dryer', is_active: true } as never]} defaultPrinterId={7} defaultDryerId={8} locale="en-US" onChange={onChange} />);
    expect(screen.getByLabelText('Printer')).toHaveTextContent('No printer');
    expect(screen.getByLabelText('Dryer')).toHaveTextContent('No dryer');
  });
});
