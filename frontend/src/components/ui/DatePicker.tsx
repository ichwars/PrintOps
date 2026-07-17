import { CalendarDays } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';

import { Calendar } from './Calendar';
import { FloatingLayer } from './FloatingLayer';
import { FormField } from './FormField';
import { controlClass } from './TextField';
import { parseDateKey, type DateKey } from './dateMath';

export type DatePickerProps = {
  value: DateKey | '';
  onValueChange: (value: DateKey | '') => void;
  locale: string;
  id?: string;
  label?: ReactNode;
  ariaLabel?: string;
  helperText?: ReactNode;
  error?: ReactNode;
  placeholder?: ReactNode;
  min?: DateKey;
  max?: DateKey;
  disabled?: boolean;
  required?: boolean;
  className?: string;
  isDateDisabled?: (value: DateKey) => boolean;
};

export function DatePicker({
  value,
  onValueChange,
  locale,
  id,
  label,
  ariaLabel,
  helperText,
  error,
  placeholder = 'Select date',
  min,
  max,
  disabled = false,
  required = false,
  className = '',
  isDateDisabled,
}: DatePickerProps) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const calendarContainerRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const parsedValue = value ? parseDateKey(value) : undefined;
  const invalidValue = Boolean(value && !parsedValue);

  useEffect(() => {
    if (!open) return undefined;
    const frame = requestAnimationFrame(() => {
      calendarContainerRef.current?.querySelector<HTMLElement>('[role="grid"]')?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [open]);

  const displayValue = parsedValue
    ? new Intl.DateTimeFormat(locale, {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        timeZone: 'UTC',
      }).format(parsedValue)
    : value || placeholder;

  return (
    <FormField
      id={id}
      label={label}
      helperText={helperText}
      error={error}
      required={required}
      className={className}
    >
      {({ controlId, describedBy, invalid }) => (
        <>
          <button
            ref={triggerRef}
            id={controlId}
            type="button"
            aria-label={label ? undefined : ariaLabel}
            aria-haspopup="dialog"
            aria-expanded={open}
            aria-describedby={describedBy}
            aria-invalid={invalid || invalidValue || undefined}
            aria-required={required || undefined}
            disabled={disabled}
            className={`${controlClass} flex items-center justify-between gap-2 text-left`}
            onClick={() => setOpen((current) => !current)}
            onKeyDown={(event) => {
              if ((event.key === 'Backspace' || event.key === 'Delete') && value && !required) {
                event.preventDefault();
                onValueChange('');
              }
            }}
          >
            <span className={`min-w-0 flex-1 truncate ${value ? '' : 'text-bambu-gray'}`}>
              {displayValue}
            </span>
            <CalendarDays aria-hidden="true" className="h-4 w-4 shrink-0" />
          </button>
          <FloatingLayer
            open={open}
            anchorRef={triggerRef}
            onDismiss={() => setOpen(false)}
            returnFocus
          >
            <div ref={calendarContainerRef}>
              <Calendar
                locale={locale}
                value={parsedValue ? value : undefined}
                focusedValue={parsedValue ? value : undefined}
                min={min}
                max={max}
                isDateDisabled={isDateDisabled}
                onSelect={(date) => {
                  onValueChange(date);
                  setOpen(false);
                  triggerRef.current?.focus();
                }}
              />
            </div>
          </FloatingLayer>
        </>
      )}
    </FormField>
  );
}
