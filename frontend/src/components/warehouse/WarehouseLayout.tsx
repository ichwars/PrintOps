import { AlertTriangle, ArrowDown, ArrowUp, ArrowUpDown, Clock, LayoutGrid, Search, TableProperties, TrendingUp, X, type LucideIcon } from 'lucide-react';
import { useId, useLayoutEffect, useRef, useState, type ButtonHTMLAttributes, type CSSProperties, type ReactNode, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { ScrollArea, Select, Slider, TextField } from '../ui';
import { tableFrameClass } from '../ui/tableStyles';
import { warehouseFilterSelectClass, warehousePageClass, warehouseResultsClass } from './warehouseStyles';

interface WarehouseHeaderProps {
  icon: LucideIcon;
  title: string;
  description: string;
  children?: ReactNode;
}

export function WarehouseHeader({ icon: Icon, title, description, children }: WarehouseHeaderProps) {
  return (
    <header className="flex flex-col gap-3 xl:flex-row xl:flex-wrap xl:items-center xl:justify-between">
      <div className="min-w-0">
        <h1 className="flex items-center gap-3 text-2xl font-bold text-white">
          <Icon aria-hidden="true" className="h-7 w-7 shrink-0 text-bambu-green" />
          {title}
        </h1>
        <p className="mt-1 text-bambu-gray">{description}</p>
      </div>
      {children && <div className="flex flex-wrap items-center gap-2 max-[768px]:[&>button]:min-h-[44px]">{children}</div>}
    </header>
  );
}

interface WarehouseToolbarProps {
  searchLabel: string;
  placeholder?: string;
  value: string;
  onSearch: (value: string) => void;
  hideSearch?: boolean;
  children?: ReactNode;
}

export function WarehouseToolbar({
  searchLabel, placeholder = searchLabel, value, onSearch, hideSearch, children,
}: WarehouseToolbarProps) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
      <div className={`relative w-full max-w-md flex-1 ${hideSearch ? 'hidden sm:invisible sm:block' : ''}`}>
        <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-table-secondary" />
        <TextField
          type="search"
          aria-label={searchLabel}
          placeholder={placeholder}
          value={value}
          onValueChange={onSearch}
          className="bg-bambu-dark-secondary! pl-10 pr-11 text-sm max-[768px]:min-h-[44px]! placeholder:text-table-secondary! [&::-webkit-search-cancel-button]:appearance-none"
        />
        {value && (
          <button
            type="button"
            onClick={() => onSearch('')}
            className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-lg text-table-secondary hover:text-white focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-foreground"
            aria-label={t('orders.runtimeDomain.smallParts.clearSearch')}
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      {children && <div className="flex max-w-full flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

export function WarehouseFilters({ children, hidden }: { children: ReactNode; hidden?: boolean }) {
  return <div hidden={hidden} className={hidden ? 'hidden' : 'flex flex-wrap items-center gap-2'}>{children}</div>;
}

export function WarehouseSegments({ children, label }: { children: ReactNode; label?: string }) {
  return <div role={label ? 'group' : undefined} aria-label={label} className="flex max-w-full flex-wrap items-center overflow-hidden rounded-lg border border-bambu-dark-tertiary">{children}</div>;
}

interface WarehouseSegmentProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  active: boolean;
  variant?: 'filter' | 'warning' | 'view';
}

export function WarehouseSegment({ active, variant = 'filter', children, ...attrs }: WarehouseSegmentProps) {
  const selected = {
    filter: 'bg-bambu-green/20 text-accent-foreground',
    warning: 'bg-amber-500/20 text-amber-900 dark:text-amber-200',
    view: 'bg-bambu-green text-black',
  };
  return (
    <button
      {...attrs}
      type="button"
      aria-pressed={active}
      className={`flex min-h-8 shrink-0 items-center gap-1.5 px-3 py-1.5 font-medium transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-foreground disabled:cursor-not-allowed disabled:opacity-40 max-[768px]:min-h-[44px] ${variant === 'view' ? 'text-sm' : 'text-xs'} ${active ? selected[variant] : 'text-table-secondary hover:bg-bambu-dark-tertiary'}`}
    >
      {children}
    </button>
  );
}

export function WarehouseToolbarButton({ label, icon: Icon, onClick, pressed }: {
  label: string; icon: LucideIcon; onClick: () => void; pressed?: boolean;
}) {
  return (
    <button type="button" aria-label={label} title={label} aria-pressed={pressed} onClick={onClick}
      className={`flex min-h-8 items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-accent-foreground max-[768px]:min-h-11 max-[768px]:min-w-11 ${pressed
        ? 'border-bambu-green/30 bg-bambu-green/20 text-accent-foreground'
        : 'border-bambu-dark-tertiary text-table-secondary hover:bg-bambu-dark-tertiary'}`}>
      <Icon aria-hidden="true" className="h-4 w-4" />
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}

export function WarehouseRemainingSort({ direction, onClick }: {
  direction?: 'asc' | 'desc'; onClick: () => void;
}) {
  const { t } = useTranslation();
  return <WarehouseToolbarButton label={t('inventory.remaining')} icon={direction === 'asc' ? ArrowUp : direction === 'desc' ? ArrowDown : ArrowUpDown} pressed={Boolean(direction)} onClick={onClick} />;
}

type WarehouseView = 'table' | 'cards' | 'forecast';

export function WarehouseViewOptions<View extends WarehouseView>({ view, onChange, options }: {
  view: View; onChange: (view: View) => void; options: readonly View[];
}) {
  const { t } = useTranslation();
  const icons = { table: TableProperties, cards: LayoutGrid, forecast: TrendingUp };
  const labels = { table: t('inventory.table'), cards: t('inventory.cards'), forecast: t('forecast.title') };
  return (
    <WarehouseSegments>
      {options.map(option => {
        const Icon: LucideIcon = icons[option];
        return (
          <WarehouseSegment key={option} variant="view" active={view === option} aria-label={labels[option]} onClick={() => onChange(option)}>
            <Icon aria-hidden="true" className="h-4 w-4" /><span className="hidden sm:inline">{labels[option]}</span>
          </WarehouseSegment>
        );
      })}
    </WarehouseSegments>
  );
}

export type WarehouseUsageFilter = 'all' | 'used' | 'new' | 'lowstock';

export function WarehouseUsageOptions({ value, onChange, lowLabel }: {
  value: WarehouseUsageFilter; onChange: (value: WarehouseUsageFilter) => void; lowLabel?: string;
}) {
  const { t } = useTranslation();
  return (
    <WarehouseSegments label={t('inventory.weightUsed')}>
      <WarehouseSegment active={value === 'all'} onClick={() => onChange('all')}>{t('inventory.all')}</WarehouseSegment>
      <WarehouseSegment active={value === 'used'} onClick={() => onChange('used')}><Clock aria-hidden className="h-3.5 w-3.5" />{t('inventory.used')}</WarehouseSegment>
      <WarehouseSegment active={value === 'new'} onClick={() => onChange('new')}>{t('inventory.new')}</WarehouseSegment>
      <WarehouseSegment variant="warning" active={value === 'lowstock'} onClick={() => onChange('lowstock')}>
        <AlertTriangle aria-hidden className="h-3.5 w-3.5" />{lowLabel ?? t('inventory.lowStock')}
      </WarehouseSegment>
    </WarehouseSegments>
  );
}

export function WarehouseFilterSelect<Value extends string>({ label, value, onChange, options }: {
  label: string; value: Value | ''; onChange: (value: Value | '') => void;
  options: Array<{ value: Value; label: string }>;
}) {
  return <Select<Value | ''> ariaLabel={label} value={value} onValueChange={onChange}
    controlClassName={warehouseFilterSelectClass(Boolean(value))} options={[{ value: '', label }, ...options]} />;
}

export function WarehouseFilterResults({ total, onReset }: {
  total: ReactNode; onReset?: () => void;
}) {
  const { t } = useTranslation();
  if (!onReset && total === undefined) return null;
  return (
    <div className="ml-auto flex max-w-full flex-wrap items-center gap-2">
      {onReset && (
        <button type="button" onClick={onReset} className="flex min-h-8 items-center gap-1 rounded px-2 text-xs text-table-secondary hover:text-accent-foreground focus-visible:outline-2 focus-visible:outline-accent-foreground max-[768px]:min-h-11">
          <X aria-hidden="true" className="h-3.5 w-3.5" />{t('inventory.clearFilters')}
        </button>
      )}
      <span className={warehouseResultsClass} role="status">{total}</span>
    </div>
  );
}

export function WarehouseTableGroupHeading({ title, colSpan }: { title: string; colSpan: number }) {
  return (
    <tr><th scope="rowgroup" colSpan={colSpan} className="border-y border-bambu-dark-tertiary bg-bambu-dark-tertiary/60 px-4 py-2 text-left text-xs font-semibold text-table-secondary">{title}</th></tr>
  );
}

export function WarehousePage({ children, footer }: { children: ReactNode; footer?: ReactNode }) {
  return (
    <div data-warehouse-paged-layout={footer ? '' : undefined}>
      <div className={warehousePageClass} data-warehouse-page-content={footer ? '' : undefined}>
        {children}
      </div>
      {footer && (
        <div data-warehouse-pagination-dock className="shrink-0 px-4 md:px-8">
          <div className={tableFrameClass}>{footer}</div>
        </div>
      )}
    </div>
  );
}

export function WarehouseTable({ children }: { children: ReactNode }) {
  return (
    <div data-warehouse-table className={`${tableFrameClass} [&_thead]:normal-case`}>
      {children}
    </div>
  );
}

export function WarehouseTableScroll({ label, children, viewportRef: externalViewportRef }: {
  label: string; children: ReactNode; viewportRef?: RefObject<HTMLDivElement | null>;
}) {
  const { t } = useTranslation();
  const viewportId = useId();
  const localViewportRef = useRef<HTMLDivElement>(null);
  const viewportRef = externalViewportRef ?? localViewportRef;
  const [widths, setWidths] = useState({ visible: 0, content: 0 });
  const [offset, setOffset] = useState(0);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const measure = () => {
      const { clientWidth: visible, scrollWidth: content } = viewport;
      setWidths(previous => previous.visible === visible && previous.content === content ? previous : { visible, content });
      setOffset(Math.abs(viewport.scrollLeft));
    };
    measure();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure);
      return () => window.removeEventListener('resize', measure);
    }

    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    if (viewport.firstElementChild) observer.observe(viewport.firstElementChild);
    return () => observer.disconnect();
  }, [viewportRef]);

  const overflow = widths.content - widths.visible;
  const showScrollbar = widths.visible > 0 && overflow > 0;
  const moveTo = (position: number) => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const direction = getComputedStyle(viewport).direction === 'rtl' ? -1 : 1;
    viewport.scrollLeft = direction * Math.max(0, Math.min(position, overflow));
    setOffset(Math.abs(viewport.scrollLeft));
  };

  return (
    <div className="warehouse-table-scroll">
      <ScrollArea
        ref={viewportRef}
        id={viewportId}
        direction="horizontal"
        scrollbar={showScrollbar ? 'hidden' : 'normal'}
        tabIndex={0}
        role="region"
        aria-label={label}
        onScroll={event => setOffset(Math.abs(event.currentTarget.scrollLeft))}
        className="focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-foreground"
      >
        {children}
      </ScrollArea>
      {showScrollbar && (
        <div className="warehouse-table-scroll-controls sticky bottom-0 z-20 border-t border-bambu-dark-tertiary bg-bambu-dark-secondary pl-3 pr-16">
          <Slider
            variant="unstyled"
            min={0}
            max={overflow}
            step="any"
            value={Math.min(offset, overflow)}
            aria-label={t('common.scrollTableHorizontally', { table: label })}
            aria-controls={viewportId}
            className="warehouse-table-scrollbar block h-7 w-full rounded focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-foreground max-[768px]:h-11"
            style={{ '--warehouse-scrollbar-thumb-width': `${widths.visible / widths.content * 100}%` } as CSSProperties}
            onChange={event => moveTo(event.currentTarget.valueAsNumber)}
            onKeyDown={event => {
              if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
              event.preventDefault();
              const rtl = getComputedStyle(event.currentTarget).direction === 'rtl';
              moveTo(offset + ((event.key === 'ArrowRight') !== rtl ? 48 : -48));
            }}
          />
        </div>
      )}
    </div>
  );
}
