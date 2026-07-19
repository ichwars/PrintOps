import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ApiError } from '../../api/client';
import { SupplierEditor } from '../../components/warehouse/SupplierEditor';
import { render } from '../utils';

const supplier = {
  id: 1,
  name: 'Filament World',
  contact_name: 'Ada Supply',
  email: 'orders@example.test',
  phone: null,
  website: null,
  address_line1: null,
  address_line2: null,
  postal_code: null,
  city: 'Berlin',
  country_code: 'DE',
  customer_number: null,
  payment_terms: null,
  default_lead_time_days: 4,
  internal_notes: null,
  is_active: true,
  created_at: '2026-07-01T10:00:00Z',
  updated_at: '2026-07-01T10:00:00Z',
};

describe('SupplierEditor', () => {
  afterEach(cleanup);

  it('submits complete supplier master data', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<SupplierEditor supplier={null} onClose={vi.fn()} onSubmit={onSubmit} canEdit canDelete={false} />);

    await user.type(screen.getByRole('textbox', { name: /Company/ }), 'Filament World');
    await user.type(screen.getByRole('textbox', { name: 'Email' }), 'orders@example.test');
    await user.type(screen.getByRole('spinbutton', { name: 'Default lead time' }), '4');
    await user.click(screen.getByRole('button', { name: 'Save supplier' }));

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Filament World',
      default_lead_time_days: 4,
      email: 'orders@example.test',
    }));
  });

  it('keeps a read-only delete dialog open and shows the domain message after a referenced-supplier 409', async () => {
    const user = userEvent.setup();
    const domainMessage = 'Supplier is referenced by existing materials.';
    const onDelete = vi.fn().mockRejectedValue(new ApiError(domainMessage, 409));
    const onClose = vi.fn();
    render(
      <SupplierEditor
        supplier={supplier}
        onClose={onClose}
        onSubmit={vi.fn()}
        onDelete={onDelete}
        canEdit={false}
        canDelete
      />,
    );

    const dialog = screen.getByRole('dialog', { name: 'Delete supplier' });
    expect(within(dialog).getByRole('textbox', { name: /Company/ })).toHaveValue('Filament World');
    within(dialog).getAllByRole('textbox').forEach((field) => expect(field).toBeDisabled());
    expect(within(dialog).getByRole('checkbox', { name: 'Active supplier' })).toBeDisabled();
    expect(within(dialog).getByRole('spinbutton', { name: 'Default lead time' })).toBeDisabled();
    expect(within(dialog).queryByRole('button', { name: 'Save supplier' })).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: 'Delete supplier' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(domainMessage);
    expect(screen.getByRole('dialog', { name: 'Delete supplier' })).toBeInTheDocument();
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });
});
