import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { DatePicker, DateTimePicker } from '../../../components/ui';

describe('DatePicker', () => {
  it('shows localized text but emits a stable date key', async () => {
    const onValueChange = vi.fn();
    render(
      <DatePicker
        label="Valid from"
        locale="de-DE"
        value="2026-07-17"
        onValueChange={onValueChange}
      />,
    );

    const trigger = screen.getByRole('button', { name: /Valid from/ });
    expect(trigger).toHaveTextContent('17.07.2026');
    await userEvent.setup().click(trigger);
    await userEvent.setup().click(screen.getByRole('button', { name: '18. Juli 2026' }));

    expect(onValueChange).toHaveBeenCalledWith('2026-07-18');
    expect(trigger).toHaveFocus();
  });

  it('displays invalid external values unchanged without emitting on mount', () => {
    const onValueChange = vi.fn();
    render(
      <DatePicker
        ariaLabel="Legacy date"
        locale="de-DE"
        value="2026-02-31"
        onValueChange={onValueChange}
      />,
    );

    const trigger = screen.getByRole('button', { name: 'Legacy date' });
    expect(trigger).toHaveTextContent('2026-02-31');
    expect(trigger).toHaveAttribute('aria-invalid', 'true');
    expect(onValueChange).not.toHaveBeenCalled();
  });
});

describe('DateTimePicker', () => {
  it('keeps date and time callbacks separate', () => {
    const onDateValueChange = vi.fn();
    const onTimeValueChange = vi.fn();
    render(
      <DateTimePicker
        dateLabel="Date"
        timeLabel="Time"
        locale="de-DE"
        dateValue="2026-07-17"
        timeValue="12:30"
        onDateValueChange={onDateValueChange}
        onTimeValueChange={onTimeValueChange}
      />,
    );

    fireEvent.change(screen.getByRole('textbox', { name: 'Time' }), {
      target: { value: '14:45' },
    });

    expect(onTimeValueChange).toHaveBeenCalledWith('14:45');
    expect(onDateValueChange).not.toHaveBeenCalled();
  });
});
