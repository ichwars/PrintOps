import type { ChangeEvent, ChangeEventHandler, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { DatePicker } from './DatePicker';
import type { DateKey } from './dateMath';

export type LegacyDatePickerProps = {
  value?: string;
  onChange?: ChangeEventHandler<HTMLInputElement>;
  onValueChange?: (value: string) => void;
  id?: string;
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
  min?: string;
  max?: string;
  disabled?: boolean;
  required?: boolean;
  className?: string;
  'aria-label'?: string;
};

export function LegacyDatePicker({
  value = '',
  onChange,
  onValueChange,
  id,
  label,
  helperText,
  error,
  min,
  max,
  disabled,
  required,
  className,
  'aria-label': ariaLabel,
}: LegacyDatePickerProps) {
  const { i18n } = useTranslation();

  return (
    <DatePicker
      id={id}
      label={label}
      ariaLabel={ariaLabel}
      helperText={helperText}
      error={error}
      value={value as DateKey | ''}
      min={min as DateKey | undefined}
      max={max as DateKey | undefined}
      disabled={disabled}
      required={required}
      locale={i18n.resolvedLanguage ?? i18n.language}
      controlClassName={className}
      onValueChange={(nextValue) => {
        onValueChange?.(nextValue);
        const target = { value: nextValue } as HTMLInputElement;
        onChange?.({ target, currentTarget: target } as ChangeEvent<HTMLInputElement>);
      }}
    />
  );
}
