import {
  useId,
  type ChangeEventHandler,
  type InputHTMLAttributes,
  type ReactNode,
} from 'react';

type NativeSwitchProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  'checked' | 'defaultChecked' | 'onChange' | 'type' | 'aria-label'
>;

type SwitchValueHandler =
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

export type SwitchProps = NativeSwitchProps &
  {
    checked: boolean;
    helperText?: ReactNode;
    stopPropagation?: boolean;
  } & SwitchValueHandler;

export function Switch({
  id,
  checked,
  onCheckedChange,
  onChange,
  label,
  ariaLabel,
  helperText,
  disabled,
  stopPropagation = false,
  className = '',
  ...props
}: SwitchProps) {
  const generatedId = useId().replace(/:/g, '');
  const controlId = id ?? `switch-${generatedId}`;
  const helperId = helperText ? `${controlId}-helper` : undefined;

  const control = (
    <>
        <input
          {...props}
          id={controlId}
          type="checkbox"
          role="switch"
          checked={checked}
          disabled={disabled}
          aria-label={ariaLabel}
          aria-checked={checked}
          aria-describedby={helperId}
          className="peer sr-only"
          onClick={(event) => {
            if (stopPropagation) event.stopPropagation();
          }}
          onChange={(event) => {
            onCheckedChange?.(event.target.checked);
            onChange?.(event);
          }}
        />
        <span
          data-testid="switch-track"
          aria-hidden="true"
          className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-bambu-green peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-bambu-dark max-[768px]:h-7 max-[768px]:w-11 ${
            disabled
              ? 'cursor-not-allowed bg-bambu-dark-tertiary/50'
              : checked
                ? 'bg-bambu-green'
                : 'bg-bambu-dark-tertiary hover:bg-bambu-dark-tertiary/80'
          }`}
        >
          <span
            className={`pointer-events-none block h-4 w-4 rounded-full bg-white shadow transition-transform duration-200 ease-in-out max-[768px]:h-5 max-[768px]:w-5 ${
              checked
                ? 'translate-x-[18px] max-[768px]:translate-x-[21px]'
                : 'translate-x-0.5 max-[768px]:translate-x-[3px]'
            }`}
          />
        </span>
    </>
  );
  const wrapsOwnLabel = label !== undefined || ariaLabel !== undefined;
  const controlRow = wrapsOwnLabel ? (
    <label
      htmlFor={controlId}
      className={`inline-flex min-h-[38px] items-center gap-2 text-sm text-bambu-gray-light max-[768px]:min-h-11 ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
    >
      {control}
      {label !== undefined ? <span>{label}</span> : null}
    </label>
  ) : (
    <span
      className={`inline-flex min-h-[38px] items-center max-[768px]:min-h-11 ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
    >
      {control}
    </span>
  );

  if (!wrapsOwnLabel && helperText === undefined) {
    return controlRow;
  }

  return (
    <div className={`space-y-1 ${className}`}>
      {controlRow}
      {helperText ? (
        <p id={helperId} className="pl-11 text-xs text-bambu-gray max-[768px]:pl-[52px]">
          {helperText}
        </p>
      ) : null}
    </div>
  );
}
