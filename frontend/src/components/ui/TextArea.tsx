import { forwardRef, type ReactNode, type TextareaHTMLAttributes } from 'react';

import { FormField } from './FormField';
import { controlClass } from './TextField';

export type TextAreaProps = Omit<
  TextareaHTMLAttributes<HTMLTextAreaElement>,
  'value' | 'onChange'
> & {
  value: string;
  onValueChange: (value: string) => void;
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
};

export const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(function TextArea(
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
        <textarea
          {...props}
          ref={ref}
          id={controlId}
          value={value}
          required={required}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          className={`${controlClass} min-h-24 h-auto py-2 ${className}`}
          onChange={(event) => onValueChange(event.target.value)}
        />
      )}
    </FormField>
  );
});
