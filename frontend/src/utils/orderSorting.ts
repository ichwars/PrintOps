export type SortDirection = 'asc' | 'desc';
export type OrderSort<Key> = { key: Key; direction: SortDirection };

export function nextOrderSort<Key>(current: OrderSort<Key> | null, key: Key, initial: SortDirection = 'asc'): OrderSort<Key> {
  return { key, direction: current?.key === key ? (current.direction === 'asc' ? 'desc' : 'asc') : initial };
}

type SortValue = string | number | bigint | null | undefined;

export function orderValueComparator<Item>(getValue: (item: Item) => SortValue, direction: SortDirection, locale: string) {
  const collator = new Intl.Collator(locale, { numeric: true, sensitivity: 'base' });
  return (left: Item, right: Item) => {
    const a = getValue(left);
    const b = getValue(right);
    const missing = (value: SortValue) => value == null || value === '' || (typeof value === 'number' && !Number.isFinite(value));
    if (missing(a) || missing(b)) return Number(missing(a)) - Number(missing(b));
    const result = typeof a === 'bigint' && typeof b === 'bigint' ? (a < b ? -1 : a > b ? 1 : 0)
      : typeof a === 'number' && typeof b === 'number' ? a - b
      : collator.compare(String(a), String(b));
    return direction === 'asc' ? result : -result;
  };
}
