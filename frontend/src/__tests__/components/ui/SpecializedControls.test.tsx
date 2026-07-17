import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  ColorInput,
  FileInput,
  LegacyDatePicker,
  Radio,
  Slider,
  TextField,
  TimeField,
} from '../../../components/ui';

describe('specialized form controls', () => {
  it('keeps standalone text fields free of an extra layout wrapper', () => {
    const { container } = render(
      <TextField aria-label="Search" value="query" onValueChange={() => {}} />,
    );

    expect(screen.getByRole('textbox', { name: 'Search' }).parentElement).toBe(container);
  });

  it('renders a centered owned radio indicator and forwards changes', async () => {
    const onChange = vi.fn();
    render(<Radio aria-label="Preferred" name="variant" checked={false} onChange={onChange} />);

    await userEvent.setup().click(screen.getByRole('radio', { name: 'Preferred' }));

    const visual = screen.getByTestId('radio-visual');
    expect(visual).toHaveClass(
      'items-center',
      'justify-center',
      'peer-checked:[&>span]:opacity-100',
    );
    expect(visual.firstElementChild).not.toHaveClass('peer-checked:opacity-100');
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('uses a text-based HH:MM time field', async () => {
    const onValueChange = vi.fn();
    render(<TimeField aria-label="Start" value="03:00" onValueChange={onValueChange} />);

    const input = screen.getByRole('textbox', { name: 'Start' });
    expect(input).toHaveAttribute('inputmode', 'numeric');
    expect(input).toHaveAttribute('placeholder', 'HH:MM');
    expect(input).not.toHaveAttribute('type', 'time');
    await userEvent.setup().clear(input);
    expect(onValueChange).toHaveBeenCalled();
  });

  it('accepts the 12-hour values produced by print scheduling', () => {
    render(<TimeField aria-label="Start" value="9:30 AM" onValueChange={() => {}} />);

    expect(screen.getByRole('textbox', { name: 'Start' })).toBeValid();
  });

  it('adapts the owned date picker to a native-style change callback', async () => {
    const onChange = vi.fn();

    function ControlledDate() {
      const [value, setValue] = useState('2026-07-17');
      return (
        <LegacyDatePicker
          aria-label="Due date"
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
            onChange(event.target.value);
          }}
        />
      );
    }

    render(<ControlledDate />);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Due date' }));
    await userEvent.setup().click(screen.getByRole('button', { name: /18/ }));

    expect(onChange).toHaveBeenCalledWith('2026-07-18');
  });

  it('forwards file, color, and slider values through owned inputs', async () => {
    const onFileChange = vi.fn();
    const onColorChange = vi.fn();
    const onSliderChange = vi.fn();
    render(
      <>
        <FileInput aria-label="Upload" accept=".txt" onChange={onFileChange} />
        <ColorInput aria-label="Color" value="#00aa55" onChange={onColorChange} />
        <Slider aria-label="Brightness" min={0} max={100} value={50} onChange={onSliderChange} />
      </>,
    );

    const file = new File(['hello'], 'sample.txt', { type: 'text/plain' });
    await userEvent.setup().upload(screen.getByLabelText('Upload'), file);
    fireEvent.change(screen.getByLabelText('Color'), { target: { value: '#112233' } });
    fireEvent.change(screen.getByRole('slider', { name: 'Brightness' }), {
      target: { value: '75' },
    });

    expect(onFileChange).toHaveBeenCalledTimes(1);
    expect(onColorChange).toHaveBeenCalledTimes(1);
    expect(onSliderChange).toHaveBeenCalledTimes(1);
  });
});
