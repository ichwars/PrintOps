import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CalculationsPage } from '../../pages/CalculationsPage';
import { calculationsApi } from '../../api/calculations';
import { selectComboboxOption } from '../utils';

vi.mock('../../api/calculations', () => ({
  calculationsApi: {
    list: vi.fn(),
    templates: vi.fn(),
    instantiateTemplate: vi.fn(),
  },
}));

vi.mock('../../components/orders/CalculationList', () => ({
  CalculationList: ({ items, onOpen }: { items: Array<{ id: number; title: string }>; onOpen: (item: unknown) => void }) => (
    <div>{items.map(item => <button key={item.id} onClick={() => onOpen(item)}>{item.title}</button>)}</div>
  ),
}));

vi.mock('../../components/orders/CalculationWorkspace', () => ({
  CalculationWorkspace: ({ calculation, onClose, onSaved }: { calculation: unknown; onClose: () => void; onSaved: () => void }) => (
    <div data-testid="workspace"><span>{calculation ? 'existing' : 'new'}</span><button onClick={onClose}>close</button><button onClick={onSaved}>saved</button></div>
  ),
}));

const item = {
  id: 7, business_profile_id: 1, customer_id: null, customer_display_name: null, business_profile_name: 'PrintOps',
  title: 'Bracket', status: 'draft' as const, currency: 'EUR', notes: null, version: 1,
  created_at: '2026-07-12T00:00:00Z', updated_at: '2026-07-12T00:00:00Z', variants: [],
  current_revision: null, production_cost: null, selling_price: null,
};

describe('CalculationsPage', () => {
  beforeEach(() => {
    vi.mocked(calculationsApi.list).mockResolvedValue({ items: [item], total: 1, limit: 50, offset: 0 });
    vi.mocked(calculationsApi.templates).mockResolvedValue([{ id: 4, business_profile_id: 1, name: 'Standard', version: 1, definition: {}, created_at: '2026-07-12T00:00:00Z' }]);
    vi.mocked(calculationsApi.instantiateTemplate).mockResolvedValue(item);
  });

  it('loads, filters, opens, creates, and instantiates calculations', async () => {
    render(<CalculationsPage />);
    expect(await screen.findByText('Bracket')).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/Search calculations/i), { target: { value: 'missing' } });
    expect(screen.getByText('No calculations yet')).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/Search calculations/i), { target: { value: '' } });

    fireEvent.click(screen.getByText('Bracket'));
    expect(screen.getByTestId('workspace')).toHaveTextContent('existing');
    fireEvent.click(screen.getByText('close'));

    fireEvent.click(screen.getByText('Add calculation'));
    expect(screen.getByTestId('workspace')).toHaveTextContent('new');
    fireEvent.click(screen.getByText('close'));

    selectComboboxOption(screen.getByLabelText('Select template'), 'Standard');
    fireEvent.click(screen.getByText('From template'));
    await waitFor(() => expect(calculationsApi.instantiateTemplate).toHaveBeenCalledWith(4, 'Standard'));
    expect(screen.getByTestId('workspace')).toHaveTextContent('existing');
  });

  it('shows a retryable loading error and reloads by status', async () => {
    vi.mocked(calculationsApi.list).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ items: [], total: 0, limit: 50, offset: 0 });
    render(<CalculationsPage />);
    expect(await screen.findByText('Calculations could not be loaded.')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Retry'));
    expect(await screen.findByText('No calculations yet')).toBeInTheDocument();
    selectComboboxOption(screen.getByLabelText('Filter status'), 'Approved');
    await waitFor(() => expect(calculationsApi.list).toHaveBeenLastCalledWith({ status: 'approved' }));
  });
});
