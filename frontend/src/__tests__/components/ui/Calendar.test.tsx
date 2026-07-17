import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Calendar } from '../../../components/ui';

afterEach(() => {
  vi.useRealTimers();
});

describe('Calendar', () => {
  it('moves by month and year with Page keys', async () => {
    render(<Calendar locale="de-DE" value="2026-07-17" onSelect={() => {}} />);
    const grid = screen.getByRole('grid');
    grid.focus();

    await userEvent.setup().keyboard('{PageDown}');
    expect(screen.getByText('August 2026')).toBeInTheDocument();

    await userEvent.setup().keyboard('{Shift>}{PageDown}{/Shift}');
    expect(screen.getByText('August 2027')).toBeInTheDocument();
  });

  it('moves the active date with arrows and selects with Enter', async () => {
    const onSelect = vi.fn();
    render(<Calendar locale="de-DE" value="2026-07-17" onSelect={onSelect} />);
    const grid = screen.getByRole('grid');
    grid.focus();

    await userEvent.setup().keyboard('{ArrowRight}{Enter}');

    expect(onSelect).toHaveBeenCalledWith('2026-07-18');
    expect(grid).toHaveAttribute('aria-activedescendant', expect.stringContaining('2026-07-18'));
  });

  it('disables dates outside bounds and custom disabled dates', () => {
    render(
      <Calendar
        locale="de-DE"
        value="2026-07-17"
        min="2026-07-17"
        max="2026-07-20"
        isDateDisabled={(date) => date === '2026-07-19'}
        onSelect={() => {}}
      />,
    );

    expect(screen.getByRole('button', { name: '16. Juli 2026' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '19. Juli 2026' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '21. Juli 2026' })).toBeDisabled();
  });

  it('marks today and uses a localized month heading', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-17T12:00:00Z'));

    render(<Calendar locale="de-DE" value="2026-07-18" onSelect={() => {}} />);

    expect(screen.getByText('Juli 2026')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '17. Juli 2026' })).toHaveAttribute(
      'aria-current',
      'date',
    );
  });

  it('leaves Escape available to the owning popover', async () => {
    const onKeyDown = vi.fn();
    render(
      <div onKeyDown={onKeyDown}>
        <Calendar locale="de-DE" value="2026-07-17" onSelect={() => {}} />
      </div>,
    );
    screen.getByRole('grid').focus();

    await userEvent.setup().keyboard('{Escape}');

    expect(onKeyDown).toHaveBeenCalledWith(
      expect.objectContaining({ key: 'Escape', defaultPrevented: false }),
    );
  });
});
