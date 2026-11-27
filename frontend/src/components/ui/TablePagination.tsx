import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';
import type { RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { usePaginatedTableViewport } from '../../hooks/usePaginatedTableViewport';
import { Select } from './Select';

const TABLE_PAGE_SIZES = [15, 30, 50, 100];

export function TablePagination({ total, offset, pageSize, onOffsetChange, onPageSizeChange,
  sizes = TABLE_PAGE_SIZES, busy = false, itemLabel, label, density = 'default', viewportRef }: {
  total: number;
  offset: number;
  pageSize: number;
  onOffsetChange: (offset: number) => void;
  onPageSizeChange: (size: number) => void;
  sizes?: readonly number[];
  busy?: boolean;
  itemLabel?: string;
  label?: string;
  density?: 'default' | 'compact';
  viewportRef?: RefObject<HTMLDivElement | null>;
}) {
  const { t, i18n } = useTranslation();
  const format = new Intl.NumberFormat(i18n?.resolvedLanguage);
  const showAll = pageSize === -1;
  const size = showAll ? Math.max(1, total) : Math.max(1, Math.floor(pageSize) || 1);
  const lastOffset = Math.max(0, Math.ceil(total / size) - 1) * size;
  const currentOffset = Math.min(lastOffset, Math.max(0, offset));
  const footerRef = usePaginatedTableViewport(currentOffset, pageSize, viewportRef);
  const start = total ? currentOffset + 1 : 0;
  const end = Math.min(currentOffset + size, total);
  const compact = density === 'compact';
  const previous = t('orders.customers.previous');
  const next = t('orders.customers.next');
  const buttons = [
    { title: t('orders.runtimeInterface.firstPage'), target: 0, disabled: currentOffset === 0, icon: ChevronsLeft },
    { title: previous, target: Math.max(0, currentOffset - size), disabled: currentOffset === 0, icon: ChevronLeft },
    { title: next, target: Math.min(lastOffset, currentOffset + size), disabled: currentOffset === lastOffset, icon: ChevronRight },
    { title: t('orders.runtimeInterface.lastPage'), target: lastOffset, disabled: currentOffset === lastOffset, icon: ChevronsRight },
  ];
  const button = ({ title, target, disabled, icon: Icon }: typeof buttons[number]) => (
    <button key={title} type="button" aria-label={title} title={title} disabled={busy || disabled}
      onClick={() => onOffsetChange(target)}
      className={`inline-flex shrink-0 items-center justify-center rounded-md text-table-secondary hover:bg-secondary-action-hover hover:text-white focus-visible:outline-2 focus-visible:outline-accent-foreground disabled:opacity-30 disabled:hover:bg-transparent max-[768px]:h-11 max-[768px]:w-11 ${compact ? 'h-7 w-7' : 'h-8 w-8'}`}>
      <Icon aria-hidden="true" className="h-4 w-4" />
    </button>
  );

  return (
    <div ref={footerRef} role="group" aria-label={label ?? t('archives.log.rowsPerPage')} data-table-pagination
      data-compact={compact ? '' : undefined}
      className={`flex w-full shrink-0 flex-wrap items-center justify-between border-t border-bambu-dark-tertiary text-table-secondary ${compact ? 'gap-x-2 gap-y-1 py-1.5 text-xs' : 'gap-x-4 gap-y-2 bg-bambu-dark-tertiary/50 px-4 py-3 text-sm'}`}>
      <span className="tabular-nums" aria-live="polite">
        {t('inventory.showing')} {format.format(start)} {t('inventory.to')} {format.format(end)}{' '}
        {t('inventory.of')} {format.format(total)}{itemLabel && ` ${itemLabel}`}
      </span>
      <div className="ml-auto flex min-w-0 flex-wrap items-center justify-end gap-x-2 gap-y-1">
        <div className="flex items-center gap-2">
          <span>{t('inventory.show')}</span>
          <Select ariaLabel={t('archives.log.rowsPerPage')} value={pageSize} disabled={busy}
            controlClassName={compact ? 'h-7! px-2! bg-bambu-dark-secondary' : 'bg-bambu-dark-secondary'}
            onValueChange={onPageSizeChange}
            options={sizes.map(value => ({ value, label: value === -1 ? t('inventory.all') : format.format(value) }))} />
        </div>
        {!showAll && <div className="flex min-w-0 flex-wrap items-center justify-end">
          <div className="flex items-center">{buttons.slice(0, 2).map(button)}</div>
          <span className="whitespace-nowrap px-1 tabular-nums sm:px-2" aria-live="polite">
            {t('inventory.page')} {format.format(Math.floor(currentOffset / size) + 1)} {t('inventory.of')} {format.format(lastOffset / size + 1)}
          </span>
          <div className="flex items-center">{buttons.slice(2).map(button)}</div>
        </div>}
      </div>
    </div>
  );
}
