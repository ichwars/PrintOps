import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { SupplierEditor } from '../../components/warehouse/SupplierEditor';
import { render } from '../utils';

describe('SupplierEditor', () => {
  afterEach(cleanup);

  it('submits complete supplier master data', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<SupplierEditor supplier={null} onClose={vi.fn()} onSubmit={onSubmit} canDelete={false} />);

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
});
