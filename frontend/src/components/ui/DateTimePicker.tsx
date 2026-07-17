import type { ReactNode } from 'react';

import { DatePicker } from './DatePicker';
import { TextField } from './TextField';
import type { DateKey } from './dateMath';

export type DateTimePickerProps = {
  dateValue: DateKey | '';
  timeValue: string;
  onDateValueChange: (value: DateKey | '') => void;
  onTimeValueChange: (value: string) => void;
  locale: string;
  dateLabel?: ReactNode;
  dateAriaLabel?: string;
  timeLabel?: ReactNode;
  timeAriaLabel?: string;
  dateHelperText?: ReactNode;
  timeHelperText?: ReactNode;
  dateError?: ReactNode;
  timeError?: ReactNode;
  min?: DateKey;
  max?: DateKey;
  disabled?: boolean;
  required?: boolean;
  className?: string;
};

export function DateTimePicker({
  dateValue,
  timeValue,
  onDateValueChange,
  onTimeValueChange,
  locale,
  dateLabel,
  dateAriaLabel,
  timeLabel,
  timeAriaLabel,
  dateHelperText,
  timeHelperText,
  dateError,
  timeError,
  min,
  max,
  disabled,
  required,
  className = '',
}: DateTimePickerProps) {
  return (
    <div className={`grid gap-3 sm:grid-cols-[minmax(0,1fr)_8rem] ${className}`}>
      <DatePicker
        value={dateValue}
        onValueChange={onDateValueChange}
        locale={locale}
        label={dateLabel}
        ariaLabel={dateAriaLabel}
        helperText={dateHelperText}
        error={dateError}
        min={min}
        max={max}
        disabled={disabled}
        required={required}
      />
      <TextField
        value={timeValue}
        onValueChange={onTimeValueChange}
        label={timeLabel}
        aria-label={timeLabel ? undefined : timeAriaLabel}
        helperText={timeHelperText}
        error={timeError}
        disabled={disabled}
        required={required}
        inputMode="numeric"
        placeholder="HH:MM"
        pattern="^([01]\\d|2[0-3]):[0-5]\\d$"
      />
    </div>
  );
}
