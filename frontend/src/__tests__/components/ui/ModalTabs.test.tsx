import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { Modal, Tabs } from '../../../components/ui';

describe('Modal', () => {
  it('traps focus and restores the trigger after closing', async () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Open</button>
          <Modal open={open} onClose={() => setOpen(false)} title="Dialog">
            <button>Inside</button>
          </Modal>
        </>
      );
    }

    render(<Harness />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Open' }));
    expect(screen.getByRole('button', { name: 'Inside' })).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(screen.getByRole('button', { name: 'Open' })).toHaveFocus();
  });
});

describe('Tabs', () => {
  it('automatically activates tabs with arrows while skipping disabled items', async () => {
    function Harness() {
      const [value, setValue] = useState('general');
      return (
        <Tabs
          ariaLabel="Settings sections"
          value={value}
          onValueChange={setValue}
          items={[
            { value: 'general', label: 'General', content: 'General panel' },
            { value: 'locked', label: 'Locked', content: 'Locked panel', disabled: true },
            { value: 'advanced', label: 'Advanced', content: 'Advanced panel' },
          ]}
        />
      );
    }

    render(<Harness />);
    const user = userEvent.setup();
    const general = screen.getByRole('tab', { name: 'General' });
    general.focus();
    await user.keyboard('{ArrowRight}');

    expect(screen.getByRole('tab', { name: 'Advanced' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Advanced panel');

    await user.keyboard('{Home}');
    expect(general).toHaveAttribute('aria-selected', 'true');
    expect(general).toHaveFocus();
  });

  it('exposes panel-less settings tabs as labeled navigation', () => {
    render(
      <Tabs
        ariaLabel="Settings sections"
        value="general"
        onValueChange={() => {}}
        renderPanel={false}
        items={[
          { value: 'general', label: 'General', content: null },
          { value: 'advanced', label: 'Advanced', content: null },
        ]}
      />,
    );

    expect(screen.getByRole('navigation', { name: 'Settings sections' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'General' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });
});
