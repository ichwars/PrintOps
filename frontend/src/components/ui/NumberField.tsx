import { ChevronDown, ChevronUp } from 'lucide-react';
import {
  forwardRef,
  useImperativeHandle,
  useRef,
  type ChangeEventHandler,
  type InputHTMLAttributes,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';

import { FormField } from './FormField';
import {
  isNumberStepBoundary,
  stepNumberValue,
  type NumberStepDirection,
} from './numberFieldMath';
import { controlClass } from './TextField';

export type NumberFieldProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'type' | 'value' | 'onChange' | 'size'
> & {
  value?: string | number;
  onValueChange?: (value: string) => void;
  onChange?: ChangeEventHandler<HTMLInputElement>;
  label?: ReactNode;
  helperText?: ReactNode;
  error?: ReactNode;
  containerClassName?: string;
  suffix?: ReactNode;
  incrementLabel?: string;
  decrementLabel?: string;
};

export const NumberField = forwardRef<HTMLInputElement, NumberFieldProps>(function NumberField(
  {
    id,
    label,
    helperText,
    error,
    containerClassName = '',
    suffix,
    required,
    className = '',
    value,
    onValueChange,
    onChange,
    onKeyDown,
    incrementLabel,
    decrementLabel,
    min,
    max,
    step,
    disabled,
    readOnly,
    'aria-describedby': externalDescribedBy,
    'aria-invalid': externalInvalid,
    ...props
  },
  forwardedRef,
) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  useImperativeHandle(forwardedRef, () => inputRef.current as HTMLInputElement);

  const emitStep = (direction: NumberStepDirection) => {
    const input = inputRef.current;
    if (!input || disabled || readOnly) return;

    const next = stepNumberValue({ value, direction, min, max, step });
    const prototypeSetter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'value',
    )?.set;
    prototypeSetter?.call(input, next);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus();
  };

  return (
    <FormField
      id={id}
      label={label}
      helperText={helperText}
      error={error}
      required={required}
    >
      {({ controlId, describedBy, invalid }) => (
        <div className={`relative ${containerClassName}`}>
          <input
            {...props}
            ref={inputRef}
            id={controlId}
            type="number"
            value={value ?? ''}
            min={min}
            max={max}
            step={step}
            required={required}
            disabled={disabled}
            readOnly={readOnly}
            aria-describedby={
              [externalDescribedBy, describedBy].filter(Boolean).join(' ') || undefined
            }
            aria-invalid={invalid ? true : externalInvalid}
            className={`${controlClass} [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none ${className} ${suffix ? 'pr-16 max-[768px]:pr-20' : 'pr-9 max-[768px]:pr-12'}`}
            onChange={(event) => {
              onValueChange?.(event.target.value);
              onChange?.(event);
            }}
            onKeyDown={(event) => {
              onKeyDown?.(event);
              if (event.defaultPrevented) return;
              if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;

              event.preventDefault();
              emitStep(event.key === 'ArrowUp' ? 1 : -1);
            }}
          />
          {suffix ? (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-y-px right-9 flex items-center px-2 text-xs text-bambu-gray max-[768px]:right-12"
            >
              {suffix}
            </span>
          ) : null}
          <div className="absolute inset-y-px right-px grid w-8 grid-rows-2 overflow-hidden rounded-r-[7px] border-l border-bambu-dark-tertiary max-[768px]:w-11">
            <button
              type="button"
              aria-label={incrementLabel ?? t('common.increaseValue')}
              disabled={
                disabled ||
                readOnly ||
                isNumberStepBoundary({ value, direction: 1, min, max, step })
              }
              className="grid place-items-center border-b border-bambu-dark-tertiary text-bambu-gray hover:bg-bambu-green/15 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => emitStep(1)}
            >
              <ChevronUp aria-hidden="true" className="h-3 w-3" />
            </button>
            <button
              type="button"
              aria-label={decrementLabel ?? t('common.decreaseValue')}
              disabled={
                disabled ||
                readOnly ||
                isNumberStepBoundary({ value, direction: -1, min, max, step })
              }
              className="grid place-items-center text-bambu-gray hover:bg-bambu-green/15 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => emitStep(-1)}
            >
              <ChevronDown aria-hidden="true" className="h-3 w-3" />
            </button>
          </div>
        </div>
      )}
    </FormField>
  );
});
