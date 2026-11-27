import { TablePagination } from '../../components/ui/TablePagination';
import { useTablePagination } from '../../hooks/useTablePagination';
import { OrderSortHeader } from './OrderSortHeader';
import { nextOrderSort, type OrderSort } from '../../utils/orderSorting';
import { resolveSupportedLanguage } from '../../i18n';
import { useTranslation } from 'react-i18next';
import { useMemo, useState } from 'react';
import { Archive, Copy, FileText, FolderOpen, GitBranch, History, Pencil, Printer, Trash2 } from 'lucide-react';
import type { CalculationDetail } from '../../api/calculations';
import { formatMoney } from '../../utils/calculationFormatting';
import { useNavigate } from 'react-router';
import { TableActionHeader, TableRowActions, type TableAction } from '../ui/TableRowActions';
import { OrderStatus, OrderTable, OrderTableRow } from './OrderLayout';
import { tableBodyCellClass, tableHeaderClass, tableHeaderRowClass, tableIdentifierClass } from '../ui/tableStyles';

interface Props {
  items: CalculationDetail[];
  locale: string;
  onOpen?: (item: CalculationDetail) => void;
  onDuplicate?: (item: CalculationDetail) => void;
  onCreateOffer?: (item: CalculationDetail) => void;
  onRevise?: (item: CalculationDetail) => void;
  onArchive?: (item: CalculationDetail) => void;
  onDelete?: (item: CalculationDetail) => void;
  onHistory: (item: CalculationDetail) => void;
  canReadOffers?: boolean;
  canReadProjects?: boolean;
  busyId?: number | null;
}

type SortKey = 'id' | 'customer' | 'variant' | 'revision' | 'status' | 'cost' | 'price' | 'learning' | 'updated';
type ColumnAlign = 'left' | 'center' | 'right';

const centeredCellClass = `${tableBodyCellClass} text-center tabular-nums`;

function numberValue(value: string | number | null | undefined): number {
  const parsed = Number(value ?? Number.NEGATIVE_INFINITY);
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
}

function preferredVariant(item: CalculationDetail) {
  return item.variants.find(variant => variant.is_preferred) ?? item.variants[0];
}

function learningScore(item: CalculationDetail): number {
  const factor = item.learning_factor;
  if (!factor || factor.status === 'pending') return Number.NEGATIVE_INFINITY;
  return Math.max(
    Math.abs(numberValue(factor.material_delta_rate)),
    Math.abs(numberValue(factor.energy_delta_rate)),
    Math.abs(numberValue(factor.cost_delta_rate)),
  );
}

function compareItems(a: CalculationDetail, b: CalculationDetail, key: SortKey): number {
  if (key === 'id') return a.id - b.id;
  if (key === 'customer') return (a.customer_display_name ?? '').localeCompare(b.customer_display_name ?? '');
  if (key === 'variant') return (preferredVariant(a)?.name ?? '').localeCompare(preferredVariant(b)?.name ?? '');
  if (key === 'revision') return (a.current_revision ?? 0) - (b.current_revision ?? 0);
  if (key === 'status') return a.status.localeCompare(b.status);
  if (key === 'cost') return numberValue(a.production_cost) - numberValue(b.production_cost);
  if (key === 'price') return numberValue(a.selling_price) - numberValue(b.selling_price);
  if (key === 'learning') return learningScore(a) - learningScore(b);
  return new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime();
}

function LearningCell({ item, locale }: { item: CalculationDetail; locale: string }) {
  const language = resolveSupportedLanguage(locale);
  const { t } = useTranslation(undefined, { lng: language });
  const factor = item.learning_factor;
  if (!factor || factor.status === 'pending' || factor.sample_count === 0) {
    return (
      <div className="text-xs text-table-secondary">
        <span className="block font-medium text-bambu-gray-light">{t('orders.runtimeCalculation.waiting', { lng: language })}</span>
        <span>{t('orders.runtimeCalculation.noProduction', { lng: language })}</span>
      </div>
    );
  }
  const largestDelta = learningScore(item);
  const percent = new Intl.NumberFormat(locale, { maximumFractionDigits: 1, style: 'percent' }).format(largestDelta);
  const tone = factor.status === 'matching' ? 'positive' : factor.status === 'watch' ? 'warning' : 'danger';
  return (
    <div className="text-xs">
      <OrderStatus tone={tone}>{percent}</OrderStatus>
      <span className="mt-1 block text-table-secondary">{t('orders.runtimeCalculation.runS', { lng: language, count: factor.sample_count })}</span>
    </div>
  );
}

export function CalculationList({ items, locale, onOpen, onDuplicate, onCreateOffer, onRevise, onArchive, onDelete, onHistory, canReadOffers, canReadProjects, busyId }: Props) {
  const language = resolveSupportedLanguage(locale);
  const { t } = useTranslation(undefined, { lng: language });
  const status: Record<string, string> = { draft: t('orders.runtimeCalculation.statusDraft', { lng: language }), approved: t('orders.runtimeCalculation.statusApproved', { lng: language }), superseded: t('orders.runtimeCalculation.statusSuperseded', { lng: language }), archived: t('orders.runtimeCalculation.statusArchived', { lng: language }) };
  const navigate = useNavigate();
  const date = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' });
  const [sort, setSort] = useState<OrderSort<SortKey>>({ key: 'updated', direction: 'desc' });
  const sortedItems = useMemo(() => [...items].sort((left, right) => {
    const result = compareItems(left, right, sort.key);
    return sort.direction === 'asc' ? result : -result;
  }), [items, sort]);
  const money = (value: string | null, currency: string) => value === null ? '—' : formatMoney(value, locale, currency);
  const changeSort = (key: SortKey) => setSort(current => nextOrderSort(current, key,
    key === 'updated' || key === 'price' || key === 'cost' || key === 'learning' ? 'desc' : 'asc'));
  const header = (label: string, key: SortKey, align: ColumnAlign = 'left') => (
    <OrderSortHeader label={label} align={align} direction={sort.key === key ? sort.direction : undefined} onSort={() => changeSort(key)} />
  );
  function rowActions(item: CalculationDetail): TableAction[] {
    const busy = busyId != null;
    const text = (key: string) => t(`orders.runtimeCalculation.${key}`, { lng: language });
    return [
      ...(onOpen ? [{ icon: Pencil, label: text('editCalculation'), onSelect: () => onOpen(item) }] : []),
      { icon: History, label: text('revisionHistory'), onSelect: () => onHistory(item) },
      ...(canReadProjects && item.project_id ? [{
        icon: FolderOpen, label: t('orders.runtimeDomain.orderDetail.openProject', { lng: language }),
        onSelect: () => navigate(`/projects/${item.project_id}`),
      }] : []),
      ...(canReadOffers ? [{
        icon: FileText, label: t('orders.rowActions.showOffers', { lng: language }),
        onSelect: () => navigate(`/orders/offers?calculation=${item.id}`),
      }] : []),
      ...(onDuplicate ? [{ icon: Copy, label: text('duplicateCalculation'), disabled: busy, onSelect: () => onDuplicate(item) }] : []),
      ...(onCreateOffer && item.status === 'approved' && item.current_revision !== null ? [{
        icon: Printer, label: text('createOfferDraft'), disabled: busy, onSelect: () => onCreateOffer(item),
      }] : []),
      ...(onRevise && item.status === 'approved' ? [{
        icon: GitBranch, label: text('createNewRevision'), disabled: busy, onSelect: () => onRevise(item),
      }] : []),
      ...(onArchive && (item.status === 'approved' || item.status === 'superseded') ? [{
        icon: Archive, label: text('archiveCalculation'), disabled: busy, destructive: true, onSelect: () => onArchive(item),
      }] : []),
      ...(onDelete && item.status === 'draft' ? [{
        icon: Trash2, label: text('deleteCalculation'), disabled: busy, destructive: true, onSelect: () => onDelete(item),
      }] : []),
    ];
  }

  const pagination = useTablePagination(sortedItems, JSON.stringify(sort));
  return (
    <OrderTable label={t('orders.runtimeCalculation.calculations', { lng: language })} footer={<TablePagination {...pagination.footer} label={t('orders.runtimeCalculation.calculations', { lng: language })} />}>
      <table className="w-full min-w-[1120px] text-sm">
        <thead className={tableHeaderClass}>
          <tr className={tableHeaderRowClass}>
            {header(t('printops.nav.calculation', { lng: language }), 'id')}
            {header(t('orders.runtimeCalculation.customerProfile', { lng: language }), 'customer')}
            {header(t('orders.runtimeCalculation.variant', { lng: language }), 'variant', 'center')}
            {header(t('orders.runtimeCalculation.rev', { lng: language }), 'revision', 'center')}
            {header(t('common.status', { lng: language }), 'status', 'center')}
            {header(t('orders.runtimeCalculation.cost', { lng: language }), 'cost', 'center')}
            {header(t('orders.runtimeCalculation.price', { lng: language }), 'price', 'center')}
            {header(t('orders.runtimeCalculation.learning', { lng: language }), 'learning', 'center')}
            {header(t('orders.runtimeCalculation.updated', { lng: language }), 'updated', 'center')}
            <TableActionHeader />
          </tr>
        </thead>
        <tbody>
          {pagination.rows.map(item => {
            const preferred = preferredVariant(item);
            const number = `K-${String(item.id).padStart(6, '0')}`;
            return (
              <OrderTableRow key={item.id} onOpen={() => onHistory(item)}>
                <td className={tableBodyCellClass}><div className={`${tableIdentifierClass} text-white`}>{number}</div><div className="text-xs text-table-secondary">{item.title}</div></td>
                <td className={tableBodyCellClass}><div className="text-white">{item.customer_display_name ?? (t('orders.runtimeCalculation.noCustomerAssigned', { lng: language }))}</div><div className="text-xs text-table-secondary">{item.business_profile_name ?? `#${item.business_profile_id}`}</div></td>
                <td className={`${centeredCellClass} text-white`}>{preferred?.name ?? '—'}</td>
                <td className={centeredCellClass}>{item.current_revision ? `R${item.current_revision}` : '—'}</td>
                <td className={centeredCellClass}><OrderStatus tone={item.status === 'approved' ? 'positive' : 'neutral'}>{item.status === 'archived' && <Archive className="h-3 w-3" />}{status[item.status]}</OrderStatus></td>
                <td className={centeredCellClass}>{money(item.production_cost, item.currency)}</td><td className={`${centeredCellClass} font-medium text-white`}>{money(item.selling_price, item.currency)}</td>
                <td className={centeredCellClass}><LearningCell item={item} locale={locale} /></td>
                <td className={centeredCellClass}>{date.format(new Date(item.updated_at))}</td>
                <TableRowActions subject={number} actions={rowActions(item)} />
              </OrderTableRow>
            );
          })}
        </tbody>
      </table>
    </OrderTable>
  );
}
