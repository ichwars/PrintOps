import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState, type FormEvent } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { NumberField } from '../../../components/ui';

describe('NumberField', () => {
  it('links field copy and emits raw typed values through both callbacks', async () => {
    const onValueChange = vi.fn();
    const onChange = vi.fn();

    function ControlledField() {
      const [value, setValue] = useState('');
      return (
        <NumberField
          label="Timeout"
          helperText="Seconds"
          error="Required"
          value={value}
          onValueChange={(next) => {
            setValue(next);
            onValueChange(next);
          }}
          onChange={onChange}
        />
      );
    }

    render(<ControlledField />);
    const input = screen.getByRole('spinbutton', { name: 'Timeout' });
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input.getAttribute('aria-describedby')).toContain('helper');
    expect(input.getAttribute('aria-describedby')).toContain('error');

    await userEvent.setup().type(input, '2.5');

    expect(onValueChange).toHaveBeenLastCalledWith('2.5');
    expect(onChange).toHaveBeenCalled();
  });

  it('increments, decrements, clamps, and retains input focus', async () => {
    const onValueChange = vi.fn();
    const changedValues: string[] = [];
    const user = userEvent.setup();
    const { rerender } = render(
      <NumberField
        aria-label="Rate"
        value="0.2"
        step="0.1"
        max="0.3"
        onValueChange={onValueChange}
        onChange={(event) => changedValues.push(event.target.value)}
      />,
    );
    const input = screen.getByRole('spinbutton', { name: 'Rate' });
    expect(input).toHaveAttribute('type', 'number');

    await user.click(screen.getByRole('button', { name: 'Increase value' }));

    expect(onValueChange).toHaveBeenLastCalledWith('0.3');
    expect(onValueChange).toHaveBeenCalledTimes(1);
    expect(changedValues).toEqual(['0.3']);
    expect(input).toHaveFocus();

    rerender(
      <NumberField
        aria-label="Rate"
        value="0.3"
        step="0.1"
        max="0.3"
        onValueChange={onValueChange}
      />,
    );
    expect(screen.getByRole('button', { name: 'Increase value' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Decrease value' }));
    expect(onValueChange).toHaveBeenLastCalledWith('0.2');
  });

  it('steps with Arrow Up and Arrow Down while preserving consumer key handlers', async () => {
    const onValueChange = vi.fn();
    const onKeyDown = vi.fn();
    const user = userEvent.setup();

    render(
      <NumberField
        aria-label="Rate"
        value="0.2"
        step="0.1"
        onValueChange={onValueChange}
        onKeyDown={onKeyDown}
      />,
    );

    const input = screen.getByRole('spinbutton', { name: 'Rate' });
    input.focus();
    await user.keyboard('{ArrowUp}');
    await user.keyboard('{ArrowDown}');

    expect(onKeyDown).toHaveBeenCalledTimes(2);
    expect(onValueChange).toHaveBeenNthCalledWith(1, '0.3');
    expect(onValueChange).toHaveBeenNthCalledWith(2, '0.1');
    expect(input).toHaveFocus();
  });

  it('never submits a surrounding form from either step button', async () => {
    const onSubmit = vi.fn((event: FormEvent) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <NumberField aria-label="Copies" value="1" onValueChange={() => {}} />
      </form>,
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Increase value' }));
    await user.click(screen.getByRole('button', { name: 'Decrease value' }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('disables steppers for disabled and read-only fields', () => {
    const { rerender } = render(<NumberField aria-label="Copies" value="1" disabled />);
    expect(screen.getByRole('spinbutton', { name: 'Copies' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Increase value' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Decrease value' })).toBeDisabled();

    rerender(<NumberField aria-label="Copies" value="1" readOnly />);
    expect(screen.getByRole('spinbutton', { name: 'Copies' })).toHaveAttribute('readonly');
    expect(screen.getByRole('button', { name: 'Increase value' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Decrease value' })).toBeDisabled();
  });

  it('does not emit on mount and supports custom stepper labels', () => {
    const onValueChange = vi.fn();
    render(
      <NumberField
        aria-label="Copies"
        value="1"
        incrementLabel="More copies"
        decrementLabel="Fewer copies"
        onValueChange={onValueChange}
      />,
    );

    expect(screen.getByRole('button', { name: 'More copies' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fewer copies' })).toBeInTheDocument();
    expect(onValueChange).not.toHaveBeenCalled();
  });

  it('uses consistently sized step controls and readable icons', () => {
    render(<NumberField aria-label="Copies" value="1" />);

    const increase = screen.getByRole('button', { name: 'Increase value' });
    const decrease = screen.getByRole('button', { name: 'Decrease value' });
    const stepper = increase.parentElement;

    expect(stepper).toHaveClass('w-10');
    expect(stepper).not.toHaveClass('w-[34px]');
    expect(increase.querySelector('svg')).toHaveClass('h-3.5', 'w-3.5');
    expect(decrease.querySelector('svg')).toHaveClass('h-3.5', 'w-3.5');
  });

  it('preserves accessibility state supplied by an outer field wrapper', () => {
    render(
      <>
        <NumberField
          aria-label="Payment days"
          aria-describedby="payment-days-error"
          aria-invalid
          value="366"
        />
        <span id="payment-days-error">Must be between 0 and 365.</span>
      </>,
    );

    const input = screen.getByRole('spinbutton', { name: 'Payment days' });
    expect(input).toHaveAccessibleDescription('Must be between 0 and 365.');
    expect(input).toHaveAttribute('aria-invalid', 'true');
  });
});
