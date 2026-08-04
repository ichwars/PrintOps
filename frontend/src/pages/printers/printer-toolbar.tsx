import { useState, useLayoutEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { computePopoverPosition } from '../../utils/popoverPosition';
import { NOZZLE_TEMP_DEFAULTS, buildPresetOptions } from '../../utils/temperatureFanPresets';
import { NumberField } from '../../components/ui';
import { ChevronDown } from 'lucide-react';

export type ToolbarDropdownOption<T extends string> = {
  value: T;
  label: string;
};

export function ToolbarDropdown<T extends string>({
  value,
  options,
  onChange,
  fullWidth = false,
}: {
  value: T;
  options: ToolbarDropdownOption<T>[];
  onChange: (value: T) => void;
  fullWidth?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const selectedOption = options.find(option => option.value === value) ?? options[0];

  return (
    <div className={`relative ${fullWidth ? 'w-full min-w-0' : ''}`}>
      <button
        type="button"
        onClick={() => setIsOpen(open => !open)}
        className={`h-8 px-2 rounded-lg border bg-bambu-dark border-bambu-dark-tertiary text-white text-sm font-medium transition-colors hover:bg-bambu-dark-tertiary focus:outline-none focus:border-bambu-green flex items-center justify-between gap-2 ${fullWidth ? 'w-full' : 'min-w-28'}`}
      >
        <span className="truncate">{selectedOption?.label}</span>
        <ChevronDown className={`w-4 h-4 text-bambu-gray transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute left-0 top-full z-20 mt-1 min-w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary py-1 shadow-xl">
            {options.map(option => (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  onChange(option.value);
                  setIsOpen(false);
                }}
                className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-bambu-dark-tertiary ${
                  option.value === value ? 'text-bambu-green' : 'text-white'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function ToolbarMenu({
  label,
  icon,
  children,
}: {
  label: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(open => !open)}
        className="h-8 w-8 rounded-lg border bg-bambu-dark border-bambu-dark-tertiary text-white hover:bg-bambu-dark-tertiary transition-colors flex items-center justify-center"
        aria-label={label}
        title={label}
      >
        {icon}
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 top-full z-20 mt-1 min-w-40 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary p-2 shadow-xl">
            {children}
          </div>
        </>
      )}
    </div>
  );
}

export function IndicatorControlPopover({
  title,
  options = [],
  unit,
  customMin,
  customMax,
  customStep = 1,
  widthClass = 'w-[240px]',
  popoverWidth = 240,
  popoverHeight = 280,
  isPending,
  onClose,
  onSubmit,
  children,
}: {
  title: string;
  options?: Array<{ label: string; value: number }>;
  unit?: string;
  customMin?: number;
  customMax?: number;
  customStep?: number;
  widthClass?: string;
  popoverWidth?: number;
  popoverHeight?: number;
  isPending?: boolean;
  onClose: () => void;
  onSubmit?: (value: number) => void;
  children?: React.ReactNode;
}) {
  const anchorRef = useRef<HTMLSpanElement>(null);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);
  const [customValue, setCustomValue] = useState('');

  // Anchor to the trigger (the popover's DOM parent before portaling) so we
  // can position via fixed coords. Portaling to document.body escapes
  // ancestor stacking contexts — sibling PrinterCard wrappers create their
  // own contexts and would otherwise cover the popover even at z-[60].
  useLayoutEffect(() => {
    const trigger = anchorRef.current?.parentElement;
    if (!trigger) return;
    const measure = () => {
      const rect = trigger.getBoundingClientRect();
      setCoords(computePopoverPosition({
        triggerRect: rect,
        popoverWidth,
        estimatedHeight: popoverHeight,
        horizontalAlign: 'center',
      }));
    };
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [popoverWidth, popoverHeight]);

  const showCustomInput = unit !== undefined;
  const submitCustom = () => {
    const value = Number(customValue);
    if (!Number.isFinite(value)) return;
    const bounded = Math.min(customMax ?? value, Math.max(customMin ?? value, value));
    onSubmit?.(Math.round(bounded));
  };

  return (
    <>
      <span ref={anchorRef} className="hidden" aria-hidden="true" />
      {createPortal(
        <>
          <div className="fixed inset-0 z-[1000]" onClick={onClose} />
          <div
            className={`fixed z-[1001] flex ${widthClass} flex-col overflow-hidden rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary shadow-2xl`}
            style={{
              top: coords?.top ?? -9999,
              left: coords?.left ?? -9999,
              visibility: coords ? 'visible' : 'hidden',
            }}
            onClick={e => e.stopPropagation()}
          >
        <div className="shrink-0 px-3 py-2.5 text-center text-sm font-medium text-white">{title}</div>
        <div className="shrink-0 h-px bg-bambu-dark-tertiary" />
        {options.length > 0 && (
          <div className="px-3 py-2.5">
            <div className="grid grid-cols-2 gap-1.5">
              {options.map(option => (
                <button
                  key={`${option.label}-${option.value}`}
                  type="button"
                  disabled={isPending}
                  onClick={() => onSubmit?.(option.value)}
                  className="h-8 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-2 text-xs font-medium text-white transition-colors hover:bg-bambu-dark-tertiary disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        )}
        {children}
        {showCustomInput && (
          <>
            <div className="shrink-0 h-px bg-bambu-dark-tertiary" />
            <form
              className="flex gap-1.5 px-3 pt-2.5 pb-3"
              onSubmit={(e) => {
                e.preventDefault();
                submitCustom();
              }}
            >
              <NumberField
                min={customMin}
                max={customMax}
                step={customStep}
                value={customValue}
                onChange={e => setCustomValue(e.target.value)}
                placeholder="Custom"
                className="h-8 min-w-0 flex-1 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-2 text-xs text-white placeholder:text-bambu-gray/60 focus:border-bambu-green focus:outline-none"
              />
              <button
                type="submit"
                disabled={isPending || customValue.trim() === ''}
                className="h-8 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-2 text-xs font-medium text-white transition-colors hover:bg-bambu-dark-tertiary disabled:cursor-not-allowed disabled:opacity-50"
              >
                Set
              </button>
            </form>
          </>
        )}
          </div>
        </>,
        document.body
      )}
    </>
  );
}

export const NOZZLE_TEMPERATURE_OPTIONS = buildPresetOptions(NOZZLE_TEMP_DEFAULTS, 'C');

export function NozzleTemperatureControlBox({
  label,
  current,
  target,
  isActive,
  isPending,
  onSubmit,
  options = NOZZLE_TEMPERATURE_OPTIONS,
}: {
  label: string;
  current?: number;
  target?: number;
  isActive: boolean;
  isPending?: boolean;
  onSubmit: (value: number) => void;
  options?: Array<{ label: string; value: number }>;
}) {
  const [customValue, setCustomValue] = useState('');

  const submitCustom = () => {
    const value = Number(customValue);
    if (!Number.isFinite(value)) return;
    onSubmit(Math.min(320, Math.max(0, Math.round(value))));
  };

  return (
    <div className={`rounded-lg border p-2 ${isActive ? 'border-amber-500/60 dark:border-amber-400/60 bg-amber-50 dark:bg-amber-400/10' : 'border-bambu-dark-tertiary bg-bambu-dark'}`}>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className={`text-xs font-medium ${isActive ? 'text-amber-700 dark:text-amber-300' : 'text-white'}`}>{label}</span>
        <span className="text-[10px] text-bambu-gray">
          {Math.round(current ?? 0)}°C
          {target !== undefined ? ` / ${Math.round(target)}°` : ''}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-1">
        {options.map(option => (
          <button
            key={`${label}-${option.value}`}
            type="button"
            disabled={isPending}
            onClick={() => onSubmit(option.value)}
            className="h-7 rounded-md border border-bambu-dark-tertiary bg-bambu-dark-secondary px-1.5 text-[11px] font-medium text-white transition-colors hover:bg-bambu-dark-tertiary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {option.label}
          </button>
        ))}
      </div>
      <form
        className="mt-1.5 flex gap-1"
        onSubmit={(e) => {
          e.preventDefault();
          submitCustom();
        }}
      >
        <NumberField
          min={0}
          max={320}
          step={1}
          value={customValue}
          onChange={e => setCustomValue(e.target.value)}
          placeholder="Custom"
          className="h-7 min-w-0 flex-1 rounded-md border border-bambu-dark-tertiary bg-bambu-dark-secondary px-1.5 text-[11px] text-white placeholder:text-bambu-gray/60 focus:border-bambu-green focus:outline-none"
        />
        <button
          type="submit"
          disabled={isPending || customValue.trim() === ''}
          className="h-7 rounded-md border border-bambu-dark-tertiary bg-bambu-dark-secondary px-2 text-[11px] font-medium text-white transition-colors hover:bg-bambu-dark-tertiary disabled:cursor-not-allowed disabled:opacity-50"
        >
          Set
        </button>
      </form>
    </div>
  );
}
