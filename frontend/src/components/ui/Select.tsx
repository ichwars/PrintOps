import { Check, ChevronDown } from 'lucide-react';
import {
  Fragment,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';

import { FloatingLayer } from './FloatingLayer';
import { FormField } from './FormField';
import { controlClass } from './TextField';

export type SelectValue = string | number;

export type SelectOption<T extends SelectValue> = {
  value: T;
  label: ReactNode;
  disabled?: boolean;
  group?: string;
};

export type SelectProps<T extends SelectValue> = {
  value: T;
  options: SelectOption<T>[];
  onValueChange: (value: T) => void;
  id?: string;
  label?: ReactNode;
  ariaLabel?: string;
  helperText?: ReactNode;
  error?: ReactNode;
  placeholder?: ReactNode;
  disabled?: boolean;
  required?: boolean;
  className?: string;
  renderValue?: (option: SelectOption<T> | undefined, value: T) => ReactNode;
};

const optionText = (label: ReactNode) =>
  typeof label === 'string' || typeof label === 'number' ? String(label) : '';

const firstEnabledIndex = <T extends SelectValue>(options: SelectOption<T>[]) =>
  options.findIndex((option) => !option.disabled);

const lastEnabledIndex = <T extends SelectValue>(options: SelectOption<T>[]) => {
  for (let index = options.length - 1; index >= 0; index -= 1) {
    if (!options[index].disabled) return index;
  }
  return -1;
};

const adjacentEnabledIndex = <T extends SelectValue>(
  options: SelectOption<T>[],
  current: number,
  delta: -1 | 1,
) => {
  if (!options.length) return -1;
  for (let step = 1; step <= options.length; step += 1) {
    const candidate = (current + delta * step + options.length) % options.length;
    if (!options[candidate].disabled) return candidate;
  }
  return current;
};

export function Select<T extends SelectValue>({
  value,
  options,
  onValueChange,
  id,
  label,
  ariaLabel,
  helperText,
  error,
  placeholder,
  disabled = false,
  required = false,
  className = '',
  renderValue,
}: SelectProps<T>) {
  const generatedId = useId().replace(/:/g, '');
  const listboxId = `select-${generatedId}-listbox`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<Array<HTMLDivElement | null>>([]);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const searchQuery = useRef('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const selectedIndex = options.findIndex((option) => Object.is(option.value, value));
  const selectedOption = selectedIndex >= 0 ? options[selectedIndex] : undefined;

  useEffect(
    () => () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    },
    [],
  );

  useEffect(() => {
    if (!open || activeIndex < 0) return;
    optionRefs.current[activeIndex]?.scrollIntoView?.({ block: 'nearest' });
  }, [activeIndex, open]);

  const initialIndex = () =>
    selectedIndex >= 0 && !options[selectedIndex].disabled
      ? selectedIndex
      : firstEnabledIndex(options);

  const openList = () => {
    if (disabled) return;
    setActiveIndex(initialIndex());
    setOpen(true);
  };

  const closeList = (restoreFocus = false) => {
    setOpen(false);
    searchQuery.current = '';
    if (restoreFocus) triggerRef.current?.focus();
  };

  const selectIndex = (index: number) => {
    const option = options[index];
    if (!option || option.disabled) return;
    onValueChange(option.value);
    closeList(true);
  };

  const runPrefixSearch = (key: string) => {
    searchQuery.current += key.toLocaleLowerCase();
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      searchQuery.current = '';
    }, 700);
    const match = options.findIndex(
      (option) =>
        !option.disabled &&
        optionText(option.label).toLocaleLowerCase().startsWith(searchQuery.current),
    );
    if (match >= 0) setActiveIndex(match);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;

    if (event.key === 'Tab') {
      if (open) closeList(false);
      return;
    }
    if (event.key === 'Escape' && open) {
      event.preventDefault();
      event.stopPropagation();
      closeList(true);
      return;
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (open) selectIndex(activeIndex);
      else openList();
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) {
        openList();
        return;
      }
      const current = activeIndex >= 0 ? activeIndex : initialIndex();
      setActiveIndex(adjacentEnabledIndex(options, current, event.key === 'ArrowDown' ? 1 : -1));
      return;
    }
    if (open && (event.key === 'Home' || event.key === 'End')) {
      event.preventDefault();
      setActiveIndex(
        event.key === 'Home' ? firstEnabledIndex(options) : lastEnabledIndex(options),
      );
      return;
    }
    if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      event.stopPropagation();
      if (!open) openList();
      runPrefixSearch(event.key);
    }
  };

  const displayedValue = renderValue
    ? renderValue(selectedOption, value)
    : selectedOption?.label ?? placeholder ?? String(value);

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
            role="combobox"
            aria-label={label ? undefined : ariaLabel}
            aria-expanded={open}
            aria-controls={listboxId}
            aria-activedescendant={
              open && activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined
            }
            aria-describedby={describedBy}
            aria-invalid={invalid || undefined}
            aria-required={required || undefined}
            disabled={disabled}
            className={`${controlClass} flex items-center justify-between gap-2 text-left`}
            onClick={() => {
              if (open) closeList(false);
              else openList();
            }}
            onKeyDown={handleKeyDown}
          >
            <span className="min-w-0 flex-1 truncate">{displayedValue}</span>
            <ChevronDown
              aria-hidden="true"
              className={`h-4 w-4 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
            />
          </button>
          <FloatingLayer
            open={open}
            anchorRef={triggerRef}
            onDismiss={() => closeList(false)}
            matchAnchorWidth
            className="max-h-72 p-1"
          >
            <div id={listboxId} role="listbox" aria-label={ariaLabel}>
              {options.map((option, index) => {
                const showGroup = option.group && options[index - 1]?.group !== option.group;
                const selected = Object.is(option.value, value);
                const active = index === activeIndex;
                return (
                  <Fragment key={`${typeof option.value}-${String(option.value)}`}>
                    {showGroup ? (
                      <div className="px-3 pb-1 pt-2 text-xs font-semibold text-bambu-gray">
                        {option.group}
                      </div>
                    ) : null}
                    <div
                      ref={(element) => {
                        optionRefs.current[index] = element;
                      }}
                      id={`${listboxId}-option-${index}`}
                      role="option"
                      aria-selected={selected}
                      aria-disabled={option.disabled || undefined}
                      className={`flex min-h-[38px] items-center justify-between gap-3 rounded-md px-3 py-2 text-sm max-[768px]:min-h-11 ${
                        option.disabled
                          ? 'cursor-not-allowed text-bambu-gray opacity-50'
                          : active
                            ? 'cursor-pointer bg-bambu-green/20 text-white'
                            : 'cursor-pointer text-bambu-gray-light hover:bg-bambu-dark-tertiary hover:text-white'
                      }`}
                      onPointerDown={(event) => event.preventDefault()}
                      onMouseEnter={() => {
                        if (!option.disabled) setActiveIndex(index);
                      }}
                      onClick={() => selectIndex(index)}
                    >
                      <span>{option.label}</span>
                      {selected ? <Check aria-hidden="true" className="h-4 w-4 text-bambu-green" /> : null}
                    </div>
                  </Fragment>
                );
              })}
            </div>
          </FloatingLayer>
        </>
      )}
    </FormField>
  );
}
