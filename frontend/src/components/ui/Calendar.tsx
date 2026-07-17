import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useEffect, useId, useMemo, useState, type KeyboardEvent } from 'react';

import { IconButton } from './IconButton';
import {
  addDays,
  addMonthsClamped,
  buildMonthGrid,
  compareDateKeys,
  formatDateKey,
  parseDateKey,
  weekStartsOn,
  type DateKey,
} from './dateMath';

export type CalendarProps = {
  value?: DateKey;
  focusedValue?: DateKey;
  onSelect: (value: DateKey) => void;
  locale: string;
  min?: DateKey;
  max?: DateKey;
  isDateDisabled?: (value: DateKey) => boolean;
  className?: string;
};

const monthKey = (value: DateKey) => `${value.slice(0, 7)}-01`;

export function Calendar({
  value,
  focusedValue,
  onSelect,
  locale,
  min,
  max,
  isDateDisabled,
  className = '',
}: CalendarProps) {
  const generatedId = useId().replace(/:/g, '');
  const now = new Date();
  const today = formatDateKey(
    new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())),
  );
  const initialFocus =
    (focusedValue && parseDateKey(focusedValue) ? focusedValue : undefined) ??
    (value && parseDateKey(value) ? value : undefined) ??
    today;
  const [focusedDate, setFocusedDate] = useState<DateKey>(initialFocus);
  const [displayedMonth, setDisplayedMonth] = useState<DateKey>(monthKey(initialFocus));
  const firstWeekday = weekStartsOn(locale);
  const days = useMemo(
    () => buildMonthGrid(displayedMonth, firstWeekday),
    [displayedMonth, firstWeekday],
  );

  useEffect(() => {
    if (!focusedValue || !parseDateKey(focusedValue)) return;
    setFocusedDate(focusedValue);
    setDisplayedMonth(monthKey(focusedValue));
  }, [focusedValue]);

  const monthDate = parseDateKey(displayedMonth)!;
  const monthHeading = new Intl.DateTimeFormat(locale, {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(monthDate);
  const accessibleDate = new Intl.DateTimeFormat(locale, {
    dateStyle: 'long',
    timeZone: 'UTC',
  });
  const shortWeekday = new Intl.DateTimeFormat(locale, {
    weekday: 'short',
    timeZone: 'UTC',
  });
  const longWeekday = new Intl.DateTimeFormat(locale, {
    weekday: 'long',
    timeZone: 'UTC',
  });
  const weekdays = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(Date.UTC(2021, 7, 1 + ((firstWeekday + index) % 7)));
    return { short: shortWeekday.format(date), long: longWeekday.format(date) };
  });

  const disabledDate = (date: DateKey) =>
    Boolean(
      (min && compareDateKeys(date, min) < 0) ||
        (max && compareDateKeys(date, max) > 0) ||
        isDateDisabled?.(date),
    );

  const moveFocus = (date: DateKey) => {
    setFocusedDate(date);
    setDisplayedMonth(monthKey(date));
  };

  const moveMonth = (amount: number) => {
    moveFocus(addMonthsClamped(focusedDate, amount));
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    let next: DateKey | undefined;
    switch (event.key) {
      case 'ArrowLeft':
        next = addDays(focusedDate, -1);
        break;
      case 'ArrowRight':
        next = addDays(focusedDate, 1);
        break;
      case 'ArrowUp':
        next = addDays(focusedDate, -7);
        break;
      case 'ArrowDown':
        next = addDays(focusedDate, 7);
        break;
      case 'Home': {
        const weekday = parseDateKey(focusedDate)!.getUTCDay();
        next = addDays(focusedDate, -((weekday - firstWeekday + 7) % 7));
        break;
      }
      case 'End': {
        const weekday = parseDateKey(focusedDate)!.getUTCDay();
        next = addDays(focusedDate, 6 - ((weekday - firstWeekday + 7) % 7));
        break;
      }
      case 'PageUp':
        next = addMonthsClamped(focusedDate, event.shiftKey ? -12 : -1);
        break;
      case 'PageDown':
        next = addMonthsClamped(focusedDate, event.shiftKey ? 12 : 1);
        break;
      case 'Enter':
      case ' ':
        event.preventDefault();
        if (!disabledDate(focusedDate)) onSelect(focusedDate);
        return;
      default:
        return;
    }

    event.preventDefault();
    moveFocus(next);
  };

  return (
    <div className={`w-[294px] p-3 ${className}`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <IconButton
          label="Previous month"
          icon={ChevronLeft}
          size="sm"
          onClick={() => moveMonth(-1)}
        />
        <div className="text-sm font-semibold text-white">{monthHeading}</div>
        <IconButton
          label="Next month"
          icon={ChevronRight}
          size="sm"
          onClick={() => moveMonth(1)}
        />
      </div>
      <div
        role="grid"
        tabIndex={0}
        aria-label={monthHeading}
        aria-activedescendant={`calendar-${generatedId}-date-${focusedDate}`}
        className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-bambu-green"
        onKeyDown={handleKeyDown}
      >
        <div role="row" className="grid grid-cols-7">
          {weekdays.map((weekday) => (
            <div
              key={weekday.long}
              role="columnheader"
              aria-label={weekday.long}
              className="flex h-8 items-center justify-center text-xs font-medium text-bambu-gray"
            >
              {weekday.short}
            </div>
          ))}
        </div>
        {Array.from({ length: 6 }, (_, row) => (
          <div key={row} role="row" className="grid grid-cols-7">
            {days.slice(row * 7, row * 7 + 7).map((date) => {
              const dateValue = parseDateKey(date)!;
              const selected = date === value;
              const active = date === focusedDate;
              const isToday = date === today;
              const disabled = disabledDate(date);
              const outsideMonth = monthKey(date) !== displayedMonth;
              return (
                <div key={date} role="gridcell" aria-selected={selected}>
                  <button
                    id={`calendar-${generatedId}-date-${date}`}
                    type="button"
                    tabIndex={-1}
                    disabled={disabled}
                    aria-label={accessibleDate.format(dateValue)}
                    aria-selected={selected}
                    aria-current={isToday ? 'date' : undefined}
                    className={`flex h-9 w-full items-center justify-center rounded-md text-sm transition-colors max-[768px]:h-11 ${
                      selected
                        ? 'bg-bambu-green font-semibold text-white'
                        : active
                          ? 'bg-bambu-green/20 text-white ring-1 ring-bambu-green'
                          : outsideMonth
                            ? 'text-bambu-gray/60 hover:bg-bambu-dark-tertiary'
                            : 'text-bambu-gray-light hover:bg-bambu-dark-tertiary hover:text-white'
                    } disabled:cursor-not-allowed disabled:opacity-30`}
                    onClick={() => {
                      moveFocus(date);
                      onSelect(date);
                    }}
                  >
                    {dateValue.getUTCDate()}
                  </button>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
