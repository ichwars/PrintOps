import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import { tableHeaderCellClass } from '../ui/tableStyles';
import type { SortDirection } from '../../utils/orderSorting';

interface OrderSortHeaderProps {
  label: string;
  direction?: SortDirection;
  onSort: () => void;
  align?: 'left' | 'center' | 'right';
  cellClassName?: string;
  normalCase?: boolean;
}

export function OrderSortHeader({ label, direction, onSort, align = 'left', cellClassName = tableHeaderCellClass, normalCase = false }: OrderSortHeaderProps) {
  const Icon = direction === 'asc' ? ArrowUp : direction === 'desc' ? ArrowDown : ArrowUpDown;
  const alignment = { left: 'text-left', center: 'text-center', right: 'text-right' }[align];
  return (
    <th scope="col" className={`${cellClassName} ${alignment}`} aria-sort={direction === 'asc' ? 'ascending' : direction === 'desc' ? 'descending' : 'none'}>
      <button type="button" onClick={onSort}
        className={`inline-flex items-center gap-1 whitespace-nowrap rounded ${normalCase ? '' : 'uppercase tracking-wide'} transition-colors hover:text-accent-foreground focus-visible:outline-2 focus-visible:outline-accent-foreground max-[768px]:min-h-[44px] ${direction ? 'text-accent-foreground' : ''}`}>
        {label}<Icon aria-hidden="true" className="h-3 w-3 shrink-0" />
      </button>
    </th>
  );
}
