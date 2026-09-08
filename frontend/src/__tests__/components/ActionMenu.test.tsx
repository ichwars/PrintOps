import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ActionMenu } from '../../components/ui/ActionMenu';

function setup(disabled = false) {
  const action = vi.fn();
  const parentClick = vi.fn();
  render(<>
    <button>Before</button>
    <div onClick={parentClick} style={{ overflow: 'hidden' }}>
      <ActionMenu label="File actions">
        {(close) => <>
          <button role="menuitem" disabled={disabled} onClick={() => { close(); action(); }}>Edit</button>
          <button role="menuitem" disabled>Forbidden</button>
          <button role="menuitem" onClick={close}>Download</button>
        </>}
      </ActionMenu>
    </div>
    <button>After</button>
  </>);
  return { action, parentClick, user: userEvent.setup(), trigger: screen.getByRole('button', { name: 'File actions' }) };
}

describe('ActionMenu', () => {
  it('portals outside clipping ancestors, focuses the first item and restores focus on Escape', async () => {
    const { user, trigger, parentClick } = setup();
    await user.click(trigger);
    const menu = screen.getByRole('menu');
    expect(menu.parentElement?.parentElement).toBe(document.body);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('menuitem', { name: 'Edit' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(parentClick).not.toHaveBeenCalled();
  });

  it('supports arrows, Home/End, skips forbidden actions and activates with Enter', async () => {
    const { user, trigger, action, parentClick } = setup();
    trigger.focus();
    await user.keyboard('{ArrowUp}');
    expect(screen.getByRole('menuitem', { name: 'Download' })).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('menuitem', { name: 'Edit' })).toHaveFocus();
    await user.keyboard('{End}{ArrowUp}{Home}{Enter}');
    expect(action).toHaveBeenCalledOnce();
    expect(trigger).toHaveFocus();
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(parentClick).not.toHaveBeenCalled();
  });

  it('restores the trigger and leaves native Tab/Shift+Tab navigation unprevented', async () => {
    const { user, trigger } = setup();
    await user.click(trigger);
    // user-event calculates Tab's destination from the original key target,
    // not the focus moved in the handler. Real Tab navigation is covered by
    // the production Playwright test; here assert the handoff contract.
    expect(fireEvent.keyDown(screen.getByRole('menuitem', { name: 'Edit' }), { key: 'Tab' })).toBe(true);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    await user.click(trigger);
    expect(fireEvent.keyDown(screen.getByRole('menuitem', { name: 'Edit' }), { key: 'Tab', shiftKey: true })).toBe(true);
    expect(trigger).toHaveFocus();
  });

  it('keeps disabled actions disabled and closes on an outside pointer without stealing focus', async () => {
    const { user, trigger, action } = setup(true);
    await user.click(trigger);
    expect(screen.getByRole('menuitem', { name: 'Download' })).toHaveFocus();
    await user.click(screen.getByRole('menuitem', { name: 'Edit' }));
    expect(action).not.toHaveBeenCalled();
    expect(screen.getByRole('menu')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'After' }));
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'After' })).toHaveFocus();
  });

  it('allows internal scrolling but dismisses on page scroll and cleans up listeners', async () => {
    const { user, trigger } = setup();
    await user.click(trigger);
    fireEvent.scroll(screen.getByRole('menu').parentElement!);
    expect(screen.getByRole('menu')).toBeInTheDocument();
    fireEvent.scroll(document);
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
    await user.click(trigger);
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });
});
