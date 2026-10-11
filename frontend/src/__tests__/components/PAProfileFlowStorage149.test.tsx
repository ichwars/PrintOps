import { useState } from 'react';
import { fireEvent, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { render } from '../utils';
import { PAProfileSection } from '../../components/spool-form/PAProfileSection';
import { defaultFormData, type PrinterWithCalibrations } from '../../components/spool-form/types';

const printers = [{
  printer: { id: 1, name: 'P2S', model: 'P2S', connected: true },
  calibrations: ['HS', 'HH'].map((flow, i) => ({
    cali_idx: 5, extruder_id: 0, nozzle_diameter: '0.4', nozzle_id: `${flow}00_0.4`,
    name: `PLA ${flow}`, filament_id: 'GFL99', setting_id: `P${flow}`, k_value: 0.02 + i * 0.02, n_coef: 0,
  })),
}] as PrinterWithCalibrations[];

function Editor() {
  const [selected, setSelected] = useState(new Set<string>());
  return <PAProfileSection formData={{ ...defaultFormData, material: 'PLA', slicer_filament: 'GFL99' }}
    updateField={vi.fn()} printersWithCalibrations={printers} selectedProfiles={selected}
    setSelectedProfiles={setSelected} expandedPrinters={new Set(['1'])} setExpandedPrinters={vi.fn()} />;
}

it('selects and removes HS/HH independently at one diameter and reused index', () => {
  render(<Editor />);
  const [standard, high] = screen.getAllByRole('checkbox');
  fireEvent.click(standard);
  fireEvent.click(high);
  expect(standard).toBeChecked();
  expect(high).toBeChecked();
  fireEvent.click(standard);
  expect(standard).not.toBeChecked();
  expect(high).toBeChecked();
});

it('auto-selects one best profile for each explicitly reported flow', () => {
  render(<Editor />);
  fireEvent.click(screen.getByRole('button', { name: /Auto-Select/i }));
  for (const control of screen.getAllByRole('checkbox')) expect(control).toBeChecked();
});
