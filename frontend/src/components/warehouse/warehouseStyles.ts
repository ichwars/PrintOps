export {
  tableBodyRowClass as warehouseTableRowClass,
  tableIdentifierClass as warehouseTableIdentifierClass,
  tablePrimaryTextClass as warehouseTableDescriptionClass,
  tableStickyActionHeaderClass as warehouseActionHeaderClass,
  tableStickyActionCellClass as warehouseActionCellClass,
} from '../ui/tableStyles';

export const warehousePageClass = 'min-w-0 space-y-6 p-4 md:p-8';
export const warehouseMetricsClass = 'grid grid-cols-2 gap-3 md:grid-cols-3';
export const warehouseMetricClass = 'rounded-lg bg-bambu-dark-secondary p-4';
export const warehouseResultsClass = 'ml-auto text-xs text-table-secondary';
export const warehouseTableQuantityClass = 'whitespace-nowrap px-4 py-3 text-center align-middle tabular-nums';
export const warehouseSelectedActionClass = '[--table-action-overlay:color-mix(in_srgb,var(--accent)_10%,transparent)]';
export const warehouseArchivedActionClass = '[--table-action-overlay:color-mix(in_srgb,var(--bg-tertiary)_20%,transparent)]';
export const warehouseGroupedActionClass = '[--table-action-overlay:color-mix(in_srgb,var(--accent)_5%,transparent)]';

export function warehouseFilterSelectClass(active: boolean) {
  return `h-8! min-w-0 border max-[768px]:min-h-[44px]! px-3 py-1.5 text-xs font-medium transition-colors ${active
    ? 'border-bambu-green/30 bg-bambu-green/20! text-accent-foreground!'
    : 'border-bambu-dark-tertiary bg-transparent! text-table-secondary! hover:bg-bambu-dark-tertiary!'}`;
}
