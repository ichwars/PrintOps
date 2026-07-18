import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CalculationProjectPlate, CalculationVariant } from '../../api/calculations';
import { setStreamToken } from '../../api/client';
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
  afterEach(() => setStreamToken(null));

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
});
