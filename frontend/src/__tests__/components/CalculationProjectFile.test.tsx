import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { calculationsApi, type CalculationProjectPlate, type CalculationVariant } from '../../api/calculations';
import { setStreamToken } from '../../api/client';
import { ProjectFileSection } from '../../components/orders/calculation/ProjectFileSection';
import { ProjectPlateGrid } from '../../components/orders/calculation/ProjectPlateGrid';
import { VariantStrip } from '../../components/orders/calculation/VariantStrip';

const variant = (name: string, preferred = false): CalculationVariant => ({
  name,
  is_preferred: preferred,
  sort_order: 0,
  price_method: 'target_margin',
  price_rate: '0.35',
  lines: [],
  operations: [],
  plates: [],
  small_parts: [],
});

const plate = (id: number): CalculationProjectPlate => ({
  id,
  plate_index: id,
  stable_key: `plate-${id}`,
  name: `Platte ${id}`,
  object_count: id,
  detected_materials: [],
  detected_grams: '10.000000',
  detected_hours: '4.500000',
  geometry: {},
  thumbnail_url: null,
});

describe('calculation project-file controls', () => {
  afterEach(() => {
    setStreamToken(null);
    vi.restoreAllMocks();
  });

  const renderProjectFileSection = () => {
    const projectPlate = { ...plate(1), detected_grams: '14.070000', detected_hours: '0.8780555555555555555555555556' };
    vi.spyOn(calculationsApi, 'projectFiles').mockResolvedValue([{
      id: 7,
      calculation_id: 42,
      revision_number: 1,
      original_filename: 'part.3mf',
      sha256: 'abc',
      size_bytes: 100,
      analysis_status: 'completed',
      analysis_error: null,
      printer_metadata: {},
      created_at: '2026-07-18T12:00:00Z',
      plates: [projectPlate],
    }]);
    render(<ProjectFileSection
      calculationId={42}
      plates={[{
        project_plate_id: 1,
        good_parts: 1,
        parts_per_print: 1,
        scrap_prints: 0,
        material_code: 'PETG',
        grams_per_print: '14.070000',
        hours_per_print: '0.8780555555555555555555555556',
        overrides: {},
        provenance: { source: '3mf' },
        sort_order: 0,
      }]}
      printers={[]}
      dryers={[]}
      spools={[]}
      locale="de-DE"
      onEnsureCalculation={vi.fn()}
      onChange={vi.fn()}
    />);
  };

  it('separates active variant editing from preferred variant selection', () => {
    const onActiveChange = vi.fn();
    const onPreferredChange = vi.fn();
    render(<VariantStrip variants={[variant('A', true), variant('B')]} activeIndex={0} locale="de-DE" onActiveChange={onActiveChange} onPreferredChange={onPreferredChange} onClone={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: 'Variante B bearbeiten' }));
    expect(onActiveChange).toHaveBeenCalledWith(1);
    expect(onPreferredChange).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'B als bevorzugt markieren' }));
    expect(onPreferredChange).toHaveBeenCalledWith(1);
  });

  it('supports independent multi-selection and focused plate details', () => {
    const onSelectionChange = vi.fn();
    const onFocusChange = vi.fn();
    render(<ProjectPlateGrid plates={[plate(1), plate(2)]} selectedIds={new Set([1])} focusedId={1} locale="de-DE" onSelectionChange={onSelectionChange} onFocusChange={onFocusChange} />);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Platte 2 auswählen' }));
    expect(onSelectionChange).toHaveBeenCalledWith(new Set([1, 2]));
    fireEvent.click(screen.getByRole('button', { name: 'Details von Platte 2 öffnen' }));
    expect(onFocusChange).toHaveBeenCalledWith(2);
  });

  it('adds the stream token to project plate thumbnail URLs', () => {
    setStreamToken('preview-token');
    render(<ProjectPlateGrid plates={[{ ...plate(1), thumbnail_url: '/api/v1/calculations/project-files/7/plates/11/thumbnail' }]} selectedIds={new Set([1])} focusedId={1} locale="de-DE" onSelectionChange={vi.fn()} onFocusChange={vi.fn()} />);

    const image = document.querySelector<HTMLImageElement>('img');
    expect(image).not.toBeNull();
    expect(new URL(image!.src).searchParams.get('token')).toBe('preview-token');
  });

  it('shows plate quantities with step-matched precision', async () => {
    renderProjectFileSection();

    expect(await screen.findByRole('spinbutton', { name: 'g je Druck' })).toHaveValue(14.1);
    expect(screen.getByRole('spinbutton', { name: 'h je Druck' })).toHaveValue(0.88);
  });

  it('uses a three-column detail layout at standard desktop widths', async () => {
    renderProjectFileSection();

    const details = await screen.findByRole('group', { name: 'Details für Platte 1' });
    await waitFor(() => expect(details).toHaveClass('lg:grid-cols-3'));
    expect(details).not.toHaveClass('lg:grid-cols-6');
  });
});
