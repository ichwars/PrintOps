import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';

export type RadioOption<T extends string> = {
  value: T;
  label: ReactNode;
  disabled?: boolean;
};

export type RadioGroupProps<T extends string> = {
  value: T;
  onValueChange: (value: T) => void;
  options: RadioOption<T>[];
  label?: ReactNode;
  name?: string;
  disabled?: boolean;
  className?: string;
};

const nextIndex = (current: number, delta: -1 | 1, enabled: boolean[]) => {
  for (let step = 1; step <= enabled.length; step += 1) {
    const candidate = (current + delta * step + enabled.length) % enabled.length;
    if (enabled[candidate]) return candidate;
  }
  return current;
};

export function RadioGroup<T extends string>({
  value,
  onValueChange,
  options,
  label,
  name,
  disabled = false,
  className = '',
}: RadioGroupProps<T>) {
  const generatedId = useId().replace(/:/g, '');
  const groupName = name ?? `radio-${generatedId}`;
  const refs = useRef<Array<HTMLInputElement | null>>([]);

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>, index: number) => {
    const delta =
      event.key === 'ArrowLeft' || event.key === 'ArrowUp'
        ? -1
        : event.key === 'ArrowRight' || event.key === 'ArrowDown'
          ? 1
          : undefined;
    if (!delta) return;

    event.preventDefault();
    const target = nextIndex(
      index,
      delta,
      options.map((option) => !disabled && !option.disabled),
    );
    onValueChange(options[target].value);
    refs.current[target]?.focus();
  };

  return (
    <fieldset disabled={disabled} className={`space-y-2 ${className}`}>
      {label ? <legend className="text-sm text-bambu-gray-light">{label}</legend> : null}
      <div className="flex flex-wrap gap-x-4 gap-y-2">
        {options.map((option, index) => (
          <label
            key={option.value}
            className={`inline-flex min-h-[38px] items-center gap-2 text-sm text-bambu-gray-light max-[768px]:min-h-11 ${
              disabled || option.disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
            }`}
          >
            <input
              ref={(element) => {
                refs.current[index] = element;
              }}
              type="radio"
              name={groupName}
              value={option.value}
              checked={value === option.value}
              disabled={disabled || option.disabled}
              className="h-[18px] w-[18px] accent-bambu-green focus:ring-2 focus:ring-bambu-green max-[768px]:h-[22px] max-[768px]:w-[22px]"
              onChange={() => onValueChange(option.value)}
              onKeyDown={(event) => handleKeyDown(event, index)}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
