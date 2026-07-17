import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react';

import { FormField } from './FormField';

export const controlClass =
  'w-full h-[38px] px-3 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white placeholder:text-bambu-gray focus:border-bambu-green focus:outline-none focus:ring-2 focus:ring-bambu-green/30 disabled:opacity-50 disabled:cursor-not-allowed max-[768px]:min-h-11';

export type TextFieldProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'value' | 'onChange' | 'size'
> & {
  value: string | number;
  onValueChange: (value: string) => void;
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
};

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  {
    id,
    label,
    helperText,
    error,
    required,
    className = '',
    value,
    onValueChange,
    ...props
  },
  ref,
) {
  return (
    <FormField
      id={id}
      label={label}
      helperText={helperText}
      error={error}
      required={required}
    >
      {({ controlId, describedBy, invalid }) => (
        <input
          {...props}
          ref={ref}
          id={controlId}
          value={value}
          required={required}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          className={`${controlClass} ${className}`}
          onChange={(event) => onValueChange(event.target.value)}
        />
      )}
    </FormField>
  );
});
