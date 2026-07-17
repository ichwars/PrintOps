import { forwardRef } from 'react';

import { TextField, type TextFieldProps } from './TextField';

export type TimeFieldProps = Omit<TextFieldProps, 'inputMode' | 'pattern' | 'type'>;

const TIME_PATTERN = String.raw`^(?:([01]\d|2[0-3]):[0-5]\d|(?:0?[1-9]|1[0-2]):[0-5]\d\s?[AaPp][Mm])$`;

export const TimeField = forwardRef<HTMLInputElement, TimeFieldProps>(function TimeField(
  { placeholder = 'HH:MM', ...props },
  ref,
) {
  return (
    <TextField
      {...props}
      ref={ref}
      inputMode="numeric"
      pattern={TIME_PATTERN}
      placeholder={placeholder}
    />
  );
});
