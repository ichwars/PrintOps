import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CalculationList } from '../../components/orders/CalculationList';
import type { CalculationDetail } from '../../api/calculations';

const base: CalculationDetail = {
  id: 12, business_profile_id: 2, customer_id: 3, customer_display_name: 'Example GmbH', business_profile_name: 'Main profile',
  title: 'Housing', status: 'approved', currency: 'EUR', notes: null, version: 2,
  created_at: '2026-07-12T08:00:00Z', updated_at: '2026-07-12T09:00:00Z',
  variants: [{ name: 'Standard', is_preferred: true, sort_order: 0, price_method: 'target_margin', price_rate: '0.35', lines: [], operations: [] }],
  current_revision: 1, production_cost: '10.00', selling_price: '20.00',
};

describe('CalculationList', () => {
  it('renders business details, commercial values, statuses, and opens a row', () => {
    const onOpen = vi.fn();
    render(<CalculationList items={[base, { ...base, id: 13, title: 'Archived', status: 'archived', customer_id: null, customer_display_name: null, current_revision: null, production_cost: null, selling_price: null, variants: [] }]} locale="en-US" onOpen={onOpen} />);

    expect(screen.getByText('Example GmbH')).toBeInTheDocument();
    expect(screen.getAllByText('Main profile')).toHaveLength(2);
    expect(screen.getByText('Standard')).toBeInTheDocument();
    expect(screen.getByText('R1')).toBeInTheDocument();
    expect(screen.getByText('No customer assigned')).toBeInTheDocument();
    expect(screen.getAllByText('Archived')).toHaveLength(2);
    fireEvent.click(screen.getAllByLabelText('Open calculation')[0]);
    expect(onOpen).toHaveBeenCalledWith(base);
  });
});
