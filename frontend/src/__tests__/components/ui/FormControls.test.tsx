import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TextArea, TextField } from '../../../components/ui';

describe('form controls', () => {
  it('links label, helper text, and error to the input', () => {
    render(
      <TextField
        label="Timeout"
        helperText="Seconds"
        error="Required"
        value=""
        onValueChange={() => {}}
      />,
    );

    const input = screen.getByRole('textbox', { name: 'Timeout' });
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input.getAttribute('aria-describedby')).toContain('helper');
    expect(input.getAttribute('aria-describedby')).toContain('error');
  });

  it('reports value changes instead of DOM events', async () => {
    const onValueChange = vi.fn();
    render(<TextArea label="Notes" value="" onValueChange={onValueChange} />);

    await userEvent.setup().type(screen.getByRole('textbox', { name: 'Notes' }), 'abc');

    expect(onValueChange).toHaveBeenLastCalledWith('c');
  });
});
