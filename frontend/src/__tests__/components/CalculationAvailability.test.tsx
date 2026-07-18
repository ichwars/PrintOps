import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { calculationsApi, type CalculationVariant } from '../../api/calculations';
import { AvailabilityPanel } from '../../components/orders/calculation/AvailabilityPanel';

vi.mock('../../api/calculations', () => ({ calculationsApi: { availabilityPreview: vi.fn() } }));

const variant: CalculationVariant = { name: 'Standard', is_preferred: true, sort_order: 0, price_method: 'target_margin', price_rate: '0.35', lines: [], operations: [], plates: [], small_parts: [] };

describe('Calculation availability', () => {
  it('shows physical, reserved, available and required stock without implying a reservation', async () => {
    vi.mocked(calculationsApi.availabilityPreview).mockResolvedValue({
      reservation_state: 'not_reserved',
      checked_at: '2026-07-18T12:00:00Z',
      lines: [{ source_key: 'small-part:1', resource_kind: 'small_part', description: 'M3 screw', material_code: null, small_part_id: 1, unit_code: 'C62', required: '8', physical: '10', reserved: '4', available: '6', shortage: '2', status: 'short', allocations: [] }],
    });

    render(<AvailabilityPanel calculationId={null} variant={variant} locale="de-DE" />);

    expect(screen.getByText('Prüfung ohne Reservierung')).toBeInTheDocument();
    expect(await screen.findByText('M3 screw')).toBeInTheDocument();
    expect(screen.getByText(/Bestand 10/)).toBeInTheDocument();
    expect(screen.getByText(/Reserviert 4/)).toBeInTheDocument();
    expect(screen.getByText(/Verfügbar 6/)).toBeInTheDocument();
    expect(screen.getByText(/Bedarf 8/)).toBeInTheDocument();
    await waitFor(() => expect(calculationsApi.availabilityPreview).toHaveBeenCalled());
  });
});
