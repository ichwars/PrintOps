import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { AppSettings } from '../../api/client';
import { PreheatSettingsCard } from '../../components/PreheatSettingsCard';

function defaults(extra: Partial<AppSettings> = {}): AppSettings {
  return {
    preheat_enabled: true,
    require_plate_clear: true,
    preheat_filament_targets: '',
    preheat_max_wait_seconds: 900,
    preheat_soak_seconds: 300,
    ...extra,
  } as AppSettings;
}

describe('PreheatSettingsCard keep-warm controls', () => {
  it('is off by default and displays the required compatibility gates', () => {
    render(<PreheatSettingsCard settings={defaults()} onChange={vi.fn()} />);
    expect(screen.getByRole('switch', { name: 'Keep the bed warm between compatible jobs' })).not.toBeChecked();
    expect(screen.getByText(/P2S\/X1C only/)).toBeInTheDocument();
    expect(screen.getByLabelText('Maximum warm hold (minutes)')).toBeDisabled();
  });

  it.each([
    { preheat_enabled: false },
    { require_plate_clear: false },
  ])('prevents opting in while a required gate is off (%j)', (extra) => {
    render(<PreheatSettingsCard settings={defaults(extra)} onChange={vi.fn()} />);
    expect(screen.getByRole('switch', { name: 'Keep the bed warm between compatible jobs' })).toBeDisabled();
  });

  it('allows an explicit opt-in and clamps the hold duration', () => {
    const change = vi.fn();
    const view = render(<PreheatSettingsCard settings={defaults()} onChange={change} />);
    fireEvent.click(screen.getByRole('switch', { name: 'Keep the bed warm between compatible jobs' }));
    expect(change).toHaveBeenCalledWith('queue_keep_bed_warm', true);
    view.rerender(<PreheatSettingsCard settings={defaults({ queue_keep_bed_warm: true })} onChange={change} />);
    const input = screen.getByLabelText('Maximum warm hold (minutes)');
    expect(input).toHaveValue(10);
    fireEvent.change(input, { target: { value: '99' } });
    expect(change).toHaveBeenCalledWith('queue_keep_warm_max_minutes', 30);
  });
});
