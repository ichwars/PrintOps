import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CalculationList } from '../../components/orders/CalculationList';
import type { CalculationDetail } from '../../api/calculations';

const base: CalculationDetail = {
  id: 12, business_profile_id: 2, customer_id: 3, customer_display_name: 'Example GmbH', business_profile_name: 'Main profile',
  title: 'Housing', status: 'approved', currency: 'EUR', notes: null, version: 2,
  created_at: '2026-07-12T08:00:00Z', updated_at: '2026-07-12T09:00:00Z',
  variants: [{ name: 'Standard', is_preferred: true, sort_order: 0, price_method: 'target_margin', price_rate: '0.35', lines: [], operations: [], plates: [], small_parts: [] }],
  current_revision: 1, production_cost: '10.00', selling_price: '20.00',
};

function renderList(items: CalculationDetail[]) {
  const actions = {
    onOpen: vi.fn(),
    onDuplicate: vi.fn(),
    onCreateOffer: vi.fn(),
    onRevise: vi.fn(),
    onArchive: vi.fn(),
    onDelete: vi.fn(),
  };
  render(<CalculationList items={items} locale="en-US" {...actions} />);
  return actions;
}

describe('CalculationList', () => {
  it('renders business details, commercial values, statuses, and opens a row', () => {
    const actions = renderList([base, { ...base, id: 13, title: 'Archived', status: 'archived', customer_id: null, customer_display_name: null, current_revision: null, production_cost: null, selling_price: null, variants: [] }]);

    expect(screen.getByText('Example GmbH')).toBeInTheDocument();
    expect(screen.getAllByText('Main profile')).toHaveLength(2);
    expect(screen.getByText('Standard')).toBeInTheDocument();
    expect(screen.getByText('R1')).toBeInTheDocument();
    expect(screen.getByText('No customer assigned')).toBeInTheDocument();
    expect(screen.getAllByText('Archived')).toHaveLength(2);
    expect(screen.getAllByText('Waiting')).toHaveLength(2);
    fireEvent.click(screen.getAllByLabelText('Edit calculation')[0]);
    expect(actions.onOpen).toHaveBeenCalledWith(base);
  });

  it('sorts by clickable headers and exposes row actions', () => {
    const draft = { ...base, id: 3, title: 'Alpha', status: 'draft' as const, updated_at: '2026-07-12T10:00:00Z', current_revision: null };
    const actions = renderList([base, draft]);

    expect(screen.getAllByText(/^K-/)[0]).toHaveTextContent('K-000003');
    fireEvent.click(screen.getByText(/Calculation/));
    expect(screen.getAllByText(/^K-/)[0]).toHaveTextContent('K-000003');
    fireEvent.click(screen.getByText(/Calculation/));
    expect(screen.getAllByText(/^K-/)[0]).toHaveTextContent('K-000012');

    fireEvent.click(screen.getAllByLabelText('Duplicate calculation')[0]);
    expect(actions.onDuplicate).toHaveBeenCalled();
    fireEvent.click(screen.getAllByLabelText('Create offer draft')[0]);
    expect(actions.onCreateOffer).toHaveBeenCalledWith(base);
    expect(screen.getAllByLabelText('Delete calculation')[0]).toBeDisabled();
  });
});
