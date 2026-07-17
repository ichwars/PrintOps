import { Check, Minus } from 'lucide-react';
import {
  useEffect,
  useId,
  useRef,
  type ChangeEventHandler,
  type InputHTMLAttributes,
  type ReactNode,
} from 'react';

type CheckboxValueHandler =
  | {
      onCheckedChange: (checked: boolean) => void;
      onChange?: never;
      label: ReactNode;
      ariaLabel?: string;
    }
  | {
      onCheckedChange: (checked: boolean) => void;
      onChange?: never;
      label?: never;
      ariaLabel: string;
    }
  | {
      onCheckedChange?: never;
      onChange: ChangeEventHandler<HTMLInputElement>;
      label?: ReactNode;
      ariaLabel?: string;
    };

export type CheckboxProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'checked' | 'defaultChecked' | 'onChange' | 'type'
> & {
  checked: boolean;
  indeterminate?: boolean;
  helperText?: ReactNode;
  error?: ReactNode;
} & CheckboxValueHandler;

export function Checkbox({
  id,
  checked,
  indeterminate = false,
  onCheckedChange,
  onChange,
  label,
  ariaLabel,
  helperText,
  error,
  disabled,
  className = '',
  ...props
}: CheckboxProps) {
  const generatedId = useId().replace(/:/g, '');
  const controlId = id ?? `checkbox-${generatedId}`;
  const helperId = helperText ? `${controlId}-helper` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const describedBy = [helperId, errorId].filter(Boolean).join(' ') || undefined;
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (inputRef.current) inputRef.current.indeterminate = indeterminate;
  }, [indeterminate]);

  const control = (
    <>
        <input
          {...props}
          ref={inputRef}
          id={controlId}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          aria-label={ariaLabel}
          aria-checked={indeterminate ? 'mixed' : checked}
          aria-describedby={describedBy}
          aria-invalid={Boolean(error) || undefined}
          className="peer sr-only"
          onChange={(event) => {
            onCheckedChange?.(event.target.checked);
            onChange?.(event);
          }}
        />
        <span
          data-testid="checkbox-visual"
          aria-hidden="true"
          className={`flex h-[18px] w-[18px] shrink-0 items-center justify-center leading-none rounded border transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-bambu-green peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-bambu-dark max-[768px]:h-[22px] max-[768px]:w-[22px] ${
            checked || indeterminate
              ? 'border-bambu-green bg-bambu-green text-white'
              : 'border-bambu-dark-tertiary bg-bambu-dark text-transparent'
          }`}
        >
          {indeterminate ? (
            <Minus className="block h-3 w-3" strokeWidth={2.5} />
          ) : checked ? (
            <Check className="block h-3 w-3" strokeWidth={2.5} />
          ) : null}
        </span>
    </>
  );
  const controlRow = label !== undefined ? (
    <label
      htmlFor={controlId}
      className={`inline-flex min-h-[38px] items-center gap-2 text-sm text-bambu-gray-light max-[768px]:min-h-11 ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
    >
      {control}
      <span>{label}</span>
    </label>
  ) : (
    <span
      className={`inline-flex min-h-[38px] items-center max-[768px]:min-h-11 ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
    >
      {control}
    </span>
  );

  if (label === undefined && helperText === undefined && error === undefined) {
    return controlRow;
  }

  return (
    <div className={`space-y-1 ${className}`}>
      {controlRow}
      {helperText ? (
        <p id={helperId} className="pl-[26px] text-xs text-bambu-gray max-[768px]:pl-[30px]">
          {helperText}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="pl-[26px] text-xs text-red-400 max-[768px]:pl-[30px]">
          {error}
        </p>
      ) : null}
    </div>
  );
}
