import { useState } from 'react';

export function setPageSelection(selected: ReadonlySet<number>, visibleIds: readonly number[], checked: boolean) {
  const next = new Set(selected);
  for (const id of visibleIds) {
    if (checked) next.add(id);
    else next.delete(id);
  }
  return next;
}

export function useTablePagination<T>(rows: readonly T[], scope = '', initialSize = 15) {
  const [pageSize, setPageSize] = useState(initialSize);
  const [position, setPosition] = useState({ scope, offset: 0 });
  const size = pageSize === -1 ? Math.max(1, rows.length) : pageSize;
  const lastOffset = Math.max(0, Math.ceil(rows.length / size) - 1) * size;
  const offset = position.scope === scope ? Math.min(position.offset, lastOffset) : 0;
  if (position.scope !== scope || position.offset !== offset) setPosition({ scope, offset });
  return {
    rows: rows.slice(offset, offset + size),
    footer: {
      total: rows.length,
      offset,
      pageSize,
      onOffsetChange: (value: number) => setPosition({ scope, offset: value }),
      onPageSizeChange: (value: number) => {
        setPageSize(value);
        setPosition({ scope, offset: 0 });
      },
    },
  };
}
