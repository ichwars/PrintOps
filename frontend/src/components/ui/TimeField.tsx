import { forwardRef } from 'react';

import { TextField, type TextFieldProps } from './TextField';

export type TimeFieldProps = Omit<TextFieldProps, 'inputMode' | 'pattern' | 'type'>;

export const TimeField = forwardRef<HTMLInputElement, TimeFieldProps>(function TimeField(
  { placeholder = 'HH:MM', ...props },
  ref,
) {
  return (
    <TextField
      {...props}
      ref={ref}
      inputMode="numeric"
      pattern="^([01]\\d|2[0-3]):[0-5]\\d$"
      placeholder={placeholder}
    />
  );
});
