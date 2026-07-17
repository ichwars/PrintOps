import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Checkbox, RadioGroup, Switch } from '../../../components/ui';

describe('selection controls', () => {
  it('centers the checkbox svg and exposes indeterminate state', () => {
    render(
      <Checkbox
        checked={false}
        indeterminate
        label="Partial"
        onCheckedChange={() => {}}
      />,
    );

    const checkbox = screen.getByRole('checkbox', { name: 'Partial' });
    expect(checkbox).toHaveAttribute('aria-checked', 'mixed');
    const visual = screen.getByTestId('checkbox-visual');
    expect(visual).toHaveClass('items-center', 'justify-center', 'leading-none');
    expect(visual.querySelector('.lucide-minus')).toBeInTheDocument();
  });

  it('reports checkbox changes and renders a centered check icon', async () => {
    const onCheckedChange = vi.fn();
    const { rerender } = render(
      <Checkbox checked={false} label="Enabled" onCheckedChange={onCheckedChange} />,
    );

    await userEvent.setup().click(screen.getByRole('checkbox', { name: 'Enabled' }));
    expect(onCheckedChange).toHaveBeenCalledWith(true);

    rerender(<Checkbox checked label="Enabled" onCheckedChange={onCheckedChange} />);
    expect(screen.getByTestId('checkbox-visual').querySelector('svg')).toHaveClass('block');
  });

  it('toggles a standalone checkbox when its visible control is clicked', async () => {
    const onCheckedChange = vi.fn();
    render(
      <Checkbox
        checked={false}
        ariaLabel="Select all colors"
        onCheckedChange={onCheckedChange}
      />,
    );

    await userEvent.setup().click(screen.getByTestId('checkbox-visual'));

    expect(onCheckedChange).toHaveBeenCalledWith(true);
  });

  it('requires an accessible switch name and reports its next state', async () => {
    const onCheckedChange = vi.fn();
    render(
      <Switch checked={false} ariaLabel="Automatic retry" onCheckedChange={onCheckedChange} />,
    );

    await userEvent.setup().click(screen.getByRole('switch', { name: 'Automatic retry' }));
    expect(onCheckedChange).toHaveBeenCalledWith(true);
  });

  it('changes a radio group with arrow keys', async () => {
    const onValueChange = vi.fn();
    render(
      <RadioGroup
        label="Mode"
        value="a"
        onValueChange={onValueChange}
        options={[
          { value: 'a', label: 'A' },
          { value: 'b', label: 'B' },
        ]}
      />,
    );

    screen.getByRole('radio', { name: 'A' }).focus();
    await userEvent.setup().keyboard('{ArrowRight}');
    expect(onValueChange).toHaveBeenCalledWith('b');
  });
});
