import { render, screen, fireEvent } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ModelPresetSection } from '../../components/spool-form/ModelPresetSection';

const saved = [
  { printer_model: 'P2S', slicer_filament: 'GFA02', slicer_filament_name: 'Saved P2S preset' },
  { printer_model: 'X1C', slicer_filament: null, slicer_filament_name: null },
];

it('keeps unavailable presets and distinguishes generic from inherit', () => {
  const change = vi.fn();
  render(<ModelPresetSection models={['P2S', 'X1C']} presets={saved} printers={[]} filamentOptions={[]}
    loading={false} error={false} retry={vi.fn()} onChange={change} />);
  expect(screen.getByRole('combobox', { name: 'P2S' })).toHaveTextContent('Saved P2S preset');
  expect(screen.getByRole('combobox', { name: 'X1C' })).toHaveTextContent('Generic material preset');
  fireEvent.click(screen.getByRole('combobox', { name: 'P2S' }));
  fireEvent.click(screen.getByRole('option', { name: 'Generic material preset' }));
  expect(change).toHaveBeenLastCalledWith([
    { printer_model: 'P2S', slicer_filament: null, slicer_filament_name: null }, saved[1],
  ]);
  fireEvent.click(screen.getByRole('combobox', { name: 'P2S' }));
  fireEvent.click(screen.getByRole('option', { name: 'Use general preset' }));
  expect(change).toHaveBeenLastCalledWith([saved[1]]);
});

it('blocks changes until a saved map has loaded', () => {
  render(<ModelPresetSection models={['P2S', 'X1C']} presets={saved} printers={[]} filamentOptions={[]}
    loading error={false} retry={vi.fn()} onChange={vi.fn()} />);
  for (const control of screen.getAllByRole('combobox')) expect(control).toBeDisabled();
});
