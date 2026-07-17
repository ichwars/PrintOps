import {
  forwardRef,
  type ChangeEventHandler,
  type ReactNode,
  type TextareaHTMLAttributes,
} from 'react';

import { FormField } from './FormField';
import { controlClass } from './TextField';

type TextAreaValueHandler =
  | { onValueChange: (value: string) => void; onChange?: never }
  | { onValueChange?: never; onChange: ChangeEventHandler<HTMLTextAreaElement> };

export type TextAreaProps = Omit<
  TextareaHTMLAttributes<HTMLTextAreaElement>,
  'value' | 'onChange'
> & {
  value: string;
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
} & TextAreaValueHandler;

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
    onChange,
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
          onChange={(event) => {
            onValueChange?.(event.target.value);
            onChange?.(event);
          }}
        />
      )}
    </FormField>
  );
});
