import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CalculationSettings } from '../../components/orders/calculation/CalculationSettings';

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: [] }),
}));

vi.mock('../../api/calculations', () => ({
  calculationsApi: { preview: vi.fn(() => new Promise(() => {})) },
}));

describe('CalculationSettings number field layout', () => {
  it('keeps number controls on the shared height without input-only offsets', () => {
    render(
      <CalculationSettings
        locale="de-DE"
        onChange={vi.fn()}
        settings={{
          currency: 'EUR',
          default_filament_cost: 20,
          energy_cost_per_kwh: 0.3,
          energy_tracking_mode: 'total',
          calculation_defaults: '{}',
        }}
      />,
    );

    const input = screen.getByRole('spinbutton', { name: 'Standard-Trocknungszeit h' });
    expect(input).toHaveClass('h-[38px]');
    expect(input).not.toHaveClass('mt-1', 'h-10');
  });
});
