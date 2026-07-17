export type DateKey = string;

const DATE_KEY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

const pad = (value: number) => String(value).padStart(2, '0');

export function formatDateKey(date: Date): DateKey {
  if (Number.isNaN(date.getTime())) return '';
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}

export function parseDateKey(value: string): Date | undefined {
  const match = DATE_KEY_PATTERN.exec(value);
  if (!match) return undefined;
  const date = new Date(
    Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])),
  );
  return formatDateKey(date) === value ? date : undefined;
}

const requireDate = (value: DateKey) => {
  const date = parseDateKey(value);
  if (!date) throw new RangeError(`Invalid date key: ${value}`);
  return date;
};

export function addDays(value: DateKey, amount: number): DateKey {
  const date = requireDate(value);
  date.setUTCDate(date.getUTCDate() + amount);
  return formatDateKey(date);
}

export function addMonthsClamped(value: DateKey, amount: number): DateKey {
  const date = requireDate(value);
  const targetMonth = new Date(
    Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + amount, 1),
  );
  const lastDay = new Date(
    Date.UTC(targetMonth.getUTCFullYear(), targetMonth.getUTCMonth() + 1, 0),
  ).getUTCDate();
  targetMonth.setUTCDate(Math.min(date.getUTCDate(), lastDay));
  return formatDateKey(targetMonth);
}

export function compareDateKeys(left: DateKey, right: DateKey): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

export function buildMonthGrid(
  month: DateKey,
  firstWeekday = 1,
): DateKey[] {
  const date = requireDate(month);
  const firstOfMonth = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
  const offset = (firstOfMonth.getUTCDay() - firstWeekday + 7) % 7;
  const firstCell = addDays(formatDateKey(firstOfMonth), -offset);
  return Array.from({ length: 42 }, (_, index) => addDays(firstCell, index));
}

const SATURDAY_START_REGIONS = new Set([
  'AE', 'AF', 'BH', 'DJ', 'DZ', 'EG', 'IQ', 'IR', 'JO', 'KW', 'LY', 'OM', 'QA', 'SD',
  'SY',
]);
const SUNDAY_START_REGIONS = new Set([
  'AR', 'AU', 'BR', 'CA', 'CN', 'CO', 'IL', 'IN', 'JP', 'KR', 'MX', 'NZ', 'PH', 'SA',
  'TW', 'US', 'ZA',
]);

export function weekStartsOn(locale: string): number {
  try {
    const region = new Intl.Locale(locale).maximize().region;
    if (region && SATURDAY_START_REGIONS.has(region)) return 6;
    if (region && SUNDAY_START_REGIONS.has(region)) return 0;
  } catch {
    return 1;
  }
  return 1;
}
