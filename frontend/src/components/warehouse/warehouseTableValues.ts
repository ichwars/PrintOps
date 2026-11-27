import { setPageSelection } from '../../hooks/useTablePagination';
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { orderRecordId } from '../../utils/orderLinks';
import { formatDateInput, parseUTCDate, type DateFormat } from '../../utils/date';

const UNIT_SYMBOLS: Record<string, string> = {
  GRM: 'g', KGM: 'kg', MMT: 'mm', CMT: 'cm', MTR: 'm', MTK: 'm²', MTQ: 'm³', MLT: 'ml', LTR: 'l',
};

export function warehouseUnit(code: string, piece: string, fallback = code) {
  return code === 'C62' || code === 'H87' ? piece : UNIT_SYMBOLS[code] ?? fallback;
}

export function warehouseDate(value: string | null | undefined, format: DateFormat = 'system') {
  const date = parseUTCDate(value);
  return date ? formatDateInput(date, format) : '—';
}

export function groupWarehouseItems<Item>(items: Item[], label?: (item: Item) => string) {
  if (!label) return [{ title: '', items }];
  const groups = new Map<string, Item[]>();
  for (const item of items) {
    const title = label(item);
    const group = groups.get(title);
    if (group) group.push(item);
    else groups.set(title, [item]);
  }
  return [...groups].map(([title, items]) => ({ title, items }));
}

export function warehouseFilterOptions(entries: Array<{ value: string; label: string }>, locale?: string) {
  return [...new Map(entries.map(entry => [entry.value, entry])).values()]
    .sort((left, right) => left.label.localeCompare(right.label, locale));
}

export function useWarehouseRowTarget() {
  const [params, setParams] = useSearchParams();
  const focusedId = orderRecordId(params.get('focus'));

  function clearRowTarget() {
    if (!params.has('focus')) return;
    const next = new URLSearchParams(params);
    next.delete('focus');
    setParams(next, { replace: true });
  }

  return { focusedId, clearRowTarget };
}

export function focusWarehouseRow(row: HTMLTableRowElement | null) {
  if (!row) return;
  row.scrollIntoView?.({ block: 'center', inline: 'nearest' });
  row.focus({ preventScroll: true });
}

export function useWarehouseSelection(ids: number[]) {
  const scope = ids.join(',');
  const [state, setState] = useState<{ scope: string; ids: Set<number> }>();
  const selected = state?.scope === scope ? state.ids : new Set<number>();
  const update = (ids: Set<number>) => setState({ scope, ids });
  return {
    selected,
    all: ids.length > 0 && selected.size === ids.length,
    toggleAll: (checked: boolean, visibleIds = ids) => update(setPageSelection(selected, visibleIds, checked)),
    toggle: (id: number, checked: boolean) => {
      const next = new Set(selected);
      if (checked) next.add(id);
      else next.delete(id);
      update(next);
    },
    clear: () => setState(undefined),
  };
}
