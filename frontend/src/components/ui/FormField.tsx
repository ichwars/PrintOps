import { useId, type ReactNode } from 'react';

export type FormFieldA11y = {
  controlId: string;
  describedBy?: string;
  invalid: boolean;
};

export type FormFieldProps = {
  id?: string;
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  className?: string;
  children: (a11y: FormFieldA11y) => ReactNode;
};

export function FormField({
  id,
  label,
  helperText,
  error,
  required,
  className = '',
  children,
}: FormFieldProps) {
  const generatedId = useId();
  const controlId = id ?? `field-${generatedId.replace(/:/g, '')}`;
  const helperId = helperText ? `${controlId}-helper` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const describedBy = [helperId, errorId].filter(Boolean).join(' ') || undefined;
  const control = children({ controlId, describedBy, invalid: Boolean(error) });

  if (!label && !helperText && !error && !className) {
    return control;
  }

  return (
    <div className={`space-y-1 ${className}`}>
      {label ? (
        <label htmlFor={controlId} className="block text-sm text-bambu-gray-light">
          {label}
          {required ? (
            <span aria-hidden="true" className="text-red-400">
              {' '}*
            </span>
          ) : null}
        </label>
      ) : null}
      {control}
      {helperText ? (
        <p id={helperId} className="text-xs text-bambu-gray">
          {helperText}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="text-xs text-red-400">
          {error}
        </p>
      ) : null}
    </div>
  );
}
