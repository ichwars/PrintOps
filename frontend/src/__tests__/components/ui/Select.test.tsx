import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRef } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { FloatingLayer, LegacySelect, Select } from '../../../components/ui';

describe('FloatingLayer', () => {
  it('portals a floating layer and dismisses outside pointer events', async () => {
    const onDismiss = vi.fn();

    function Harness() {
      const ref = useRef<HTMLButtonElement>(null);
      return (
        <>
          <button ref={ref}>Anchor</button>
          <FloatingLayer open anchorRef={ref} onDismiss={onDismiss}>
            Menu
          </FloatingLayer>
        </>
      );
    }

    render(<Harness />);

    expect(screen.getByText('Menu')).toBe(document.body.lastElementChild);
    await userEvent.setup().click(document.body);
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});

describe('Select', () => {
  it('selects a numeric value with the keyboard and returns focus', async () => {
    const onValueChange = vi.fn();
    render(
      <Select
        ariaLabel="Retries"
        value={3}
        onValueChange={onValueChange}
        options={[1, 3, 5].map((value) => ({ value, label: `${value} times` }))}
      />,
    );

    const trigger = screen.getByRole('combobox', { name: 'Retries' });
    trigger.focus();
    await userEvent.setup().keyboard('{Enter}{ArrowDown}{Enter}');

    expect(onValueChange).toHaveBeenCalledWith(5);
    expect(trigger).toHaveFocus();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('skips disabled options and supports Home and End', async () => {
    const onValueChange = vi.fn();
    render(
      <Select
        ariaLabel="Mode"
        value="a"
        onValueChange={onValueChange}
        options={[
          { value: 'a', label: 'Alpha' },
          { value: 'b', label: 'Beta', disabled: true },
          { value: 'c', label: 'Gamma' },
        ]}
      />,
    );

    const user = userEvent.setup();
    const trigger = screen.getByRole('combobox', { name: 'Mode' });
    await user.click(trigger);
    await user.keyboard('{ArrowDown}{Enter}');
    expect(onValueChange).toHaveBeenLastCalledWith('c');

    await user.click(trigger);
    await user.keyboard('{End}{Enter}');
    expect(onValueChange).toHaveBeenLastCalledWith('c');
  });

  it('closes on Escape and Tab without changing the value', async () => {
    const onValueChange = vi.fn();
    render(
      <>
        <Select
          ariaLabel="Mode"
          value="a"
          onValueChange={onValueChange}
          options={[
            { value: 'a', label: 'Alpha' },
            { value: 'b', label: 'Beta' },
          ]}
        />
        <button>After</button>
      </>,
    );

    const user = userEvent.setup();
    const trigger = screen.getByRole('combobox', { name: 'Mode' });
    await user.click(trigger);
    await user.keyboard('{Escape}');
    expect(trigger).toHaveFocus();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    await user.click(trigger);
    await user.tab();
    expect(screen.getByRole('button', { name: 'After' })).toHaveFocus();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(onValueChange).not.toHaveBeenCalled();
  });

  it('uses prefix search and renders group headings', async () => {
    const onValueChange = vi.fn();
    render(
      <Select
        ariaLabel="Material"
        value="pla"
        onValueChange={onValueChange}
        options={[
          { value: 'pla', label: 'Alpha PLA', group: 'Primary' },
          { value: 'petg', label: 'Beta PETG', group: 'Primary' },
          { value: 'abs', label: 'Gamma ABS', group: 'Engineering' },
        ]}
      />,
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole('combobox', { name: 'Material' }));
    await user.keyboard('gam{Enter}');

    expect(onValueChange).toHaveBeenCalledWith('abs');
    expect(screen.queryByText('Primary')).not.toBeInTheDocument();
  });

  it('renders an unknown current value without changing it on mount', () => {
    const onValueChange = vi.fn();
    render(
      <Select
        ariaLabel="Legacy"
        value={99}
        onValueChange={onValueChange}
        options={[{ value: 1, label: 'One' }]}
        renderValue={(_option, value) => `Legacy ${value}`}
      />,
    );

    expect(screen.getByRole('combobox', { name: 'Legacy' })).toHaveTextContent('Legacy 99');
    expect(onValueChange).not.toHaveBeenCalled();
  });

  it('adapts existing option declarations to the custom listbox', async () => {
    const onChange = vi.fn();
    render(
      <LegacySelect aria-label="Retries" value="3" onChange={onChange}>
        <option value="3">3 times</option>
        <option value="5">5 times</option>
      </LegacySelect>,
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole('combobox', { name: 'Retries' }));
    await user.click(screen.getByRole('option', { name: '5 times' }));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({
      target: expect.objectContaining({ value: '5' }),
    }));
  });
});
