import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react';

export type TabItem<T extends string> = {
  value: T;
  label: ReactNode;
  content: ReactNode;
  disabled?: boolean;
};

export type TabsProps<T extends string> = {
  value: T;
  onValueChange: (value: T) => void;
  items: TabItem<T>[];
  ariaLabel: string;
  className?: string;
};

const adjacentEnabledIndex = <T extends string>(
  items: TabItem<T>[],
  current: number,
  delta: -1 | 1,
) => {
  for (let step = 1; step <= items.length; step += 1) {
    const candidate = (current + delta * step + items.length) % items.length;
    if (!items[candidate].disabled) return candidate;
  }
  return current;
};

export function Tabs<T extends string>({
  value,
  onValueChange,
  items,
  ariaLabel,
  className = '',
}: TabsProps<T>) {
  const generatedId = useId().replace(/:/g, '');
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const activeIndex = items.findIndex((item) => item.value === value);
  const enabledIndices = items
    .map((item, index) => (item.disabled ? -1 : index))
    .filter((index) => index >= 0);

  const activate = (index: number) => {
    const item = items[index];
    if (!item || item.disabled) return;
    onValueChange(item.value);
    tabRefs.current[index]?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let target: number | undefined;
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        target = adjacentEnabledIndex(items, index, 1);
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        target = adjacentEnabledIndex(items, index, -1);
        break;
      case 'Home':
        target = enabledIndices[0];
        break;
      case 'End':
        target = enabledIndices.at(-1);
        break;
      default:
        return;
    }
    if (target === undefined) return;
    event.preventDefault();
    activate(target);
  };

  return (
    <div className={className}>
      <div
        role="tablist"
        aria-label={ariaLabel}
        className="flex gap-1 overflow-x-auto border-b border-bambu-dark-tertiary"
      >
        {items.map((item, index) => {
          const selected = item.value === value;
          const valueId = item.value.replace(/[^a-zA-Z0-9_-]/g, '-');
          return (
            <button
              key={item.value}
              ref={(element) => {
                tabRefs.current[index] = element;
              }}
              id={`tabs-${generatedId}-tab-${valueId}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`tabs-${generatedId}-panel-${valueId}`}
              tabIndex={selected ? 0 : -1}
              disabled={item.disabled}
              className={`min-h-[38px] shrink-0 border-b-2 px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green max-[768px]:min-h-11 ${
                selected
                  ? 'border-bambu-green text-bambu-green'
                  : 'border-transparent text-bambu-gray hover:text-white'
              } disabled:cursor-not-allowed disabled:opacity-40`}
              onClick={() => activate(index)}
              onKeyDown={(event) => handleKeyDown(event, index)}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {activeIndex >= 0 ? (
        <div
          id={`tabs-${generatedId}-panel-${value.replace(/[^a-zA-Z0-9_-]/g, '-')}`}
          role="tabpanel"
          aria-labelledby={`tabs-${generatedId}-tab-${value.replace(/[^a-zA-Z0-9_-]/g, '-')}`}
          tabIndex={0}
        >
          {items[activeIndex].content}
        </div>
      ) : null}
    </div>
  );
}
