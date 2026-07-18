import { useEffect, useId, useRef, useState } from 'react';

import { smallPartsApi, type SmallPartOption } from '../../api/smallParts';

interface SmallPartComboboxProps {
  value: SmallPartOption | null;
  onChange: (value: SmallPartOption | null) => void;
  disabled?: boolean;
  locale?: string;
  label?: string;
}

export function SmallPartCombobox({
  value,
  onChange,
  disabled = false,
  locale = 'de-DE',
  label = 'Kleinteil suchen',
}: SmallPartComboboxProps) {
  const listboxId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState(value ? `${value.sku} · ${value.name}` : '');
  const [options, setOptions] = useState<SmallPartOption[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (value) setQuery(`${value.sku} · ${value.name}`);
  }, [value]);

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => {
      setLoading(true);
      smallPartsApi.search(query).then((items) => {
        setOptions(items);
        setActiveIndex(-1);
      }).finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [open, query]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const selectOption = (option: SmallPartOption) => {
    onChange(option);
    setQuery(`${option.sku} · ${option.name}`);
    setOpen(false);
  };

  return (
    <div ref={rootRef} className="relative">
      <input
        type="text"
        role="combobox"
        aria-label={label}
        aria-expanded={open}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={activeIndex >= 0 ? `${listboxId}-${options[activeIndex]?.id}` : undefined}
        value={query}
        disabled={disabled}
        placeholder="Artikelnummer oder Bezeichnung"
        className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white outline-none focus:border-green-500"
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
          if (value) onChange(null);
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            event.preventDefault();
            setOpen(true);
            setActiveIndex((current) => Math.min(current + 1, options.length - 1));
          } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            setActiveIndex((current) => Math.max(current - 1, 0));
          } else if (event.key === 'Enter' && activeIndex >= 0 && options[activeIndex]) {
            event.preventDefault();
            selectOption(options[activeIndex]);
          } else if (event.key === 'Escape') {
            setOpen(false);
          }
        }}
      />
      {open && (
        <ul
          id={listboxId}
          role="listbox"
          className="absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-gray-600 bg-gray-900 p-1 shadow-xl"
        >
          {loading && <li className="px-3 py-2 text-sm text-gray-400">Suche …</li>}
          {!loading && options.length === 0 && (
            <li className="px-3 py-2 text-sm text-gray-400">Keine passenden Kleinteile</li>
          )}
          {options.map((option, index) => (
            <li
              id={`${listboxId}-${option.id}`}
              key={option.id}
              role="option"
              aria-selected={index === activeIndex}
              className={`cursor-pointer rounded-md px-3 py-2 text-sm ${index === activeIndex ? 'bg-green-600 text-white' : 'text-gray-100 hover:bg-gray-700'}`}
              onMouseDown={(event) => event.preventDefault()}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => selectOption(option)}
            >
              <div className="font-medium">{option.sku} · {option.name}</div>
              <div className="text-xs opacity-75">
                {new Intl.NumberFormat(locale, { maximumFractionDigits: 6 }).format(Number(option.available))} verfügbar
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
