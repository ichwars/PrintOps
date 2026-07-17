import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { PreheatFilamentTargetsEditor } from '../../components/PreheatFilamentTargetsEditor';
import { PREHEAT_FILAMENT_ORDER } from '../../utils/preheatFilamentTargets';
import { render } from '../utils';

describe('remaining settings shared controls', () => {
  it('keeps the preheat numeric-field payload stable', () => {
    const onChange = vi.fn();
    render(<PreheatFilamentTargetsEditor value="" onChange={onChange} />);

    fireEvent.change(screen.getAllByRole('spinbutton')[0], { target: { value: '42' } });

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(JSON.parse(onChange.mock.calls[0][0])).toMatchObject({
      [PREHEAT_FILAMENT_ORDER[0]]: 42,
    });
  });
});
