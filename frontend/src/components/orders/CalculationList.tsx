import { resolveSupportedLanguage } from '../../i18n';
import { useTranslation } from 'react-i18next';
import { useMemo, useState } from 'react';
import { Archive, ArrowDown, ArrowUp, ArrowUpDown, Copy, GitBranch, Pencil, Printer, Trash2 } from 'lucide-react';
import type { CalculationDetail } from '../../api/calculations';
import { formatMoney } from '../../utils/calculationFormatting';
import { IconButton } from '../ui/IconButton';
import { tableHeaderActionCellClass, tableHeaderCellClass, tableHeaderClass, tableHeaderRowClass } from '../ui/tableStyles';

interface Props {
  items: CalculationDetail[];
  locale: string;
  onOpen: (item: CalculationDetail) => void;
  onDuplicate: (item: CalculationDetail) => void;
  onCreateOffer: (item: CalculationDetail) => void;
  onRevise: (item: CalculationDetail) => void;
  onArchive: (item: CalculationDetail) => void;
  onDelete: (item: CalculationDetail) => void;
  busyId?: number | null;
}

type SortKey = 'id' | 'customer' | 'variant' | 'revision' | 'status' | 'cost' | 'price' | 'learning' | 'updated';
type SortDirection = 'asc' | 'desc';
type ColumnAlign = 'left' | 'center' | 'right';

const centeredCellClass = 'px-4 py-3 text-center align-middle';
const actionIconClass = '!rounded-none !border-0 hover:!bg-transparent hover:!text-bambu-green focus:!ring-0';

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
      <div className="text-xs text-bambu-gray">
        <span className="block font-medium text-bambu-gray-light">{t('orders.runtimeCalculation.waiting', { lng: language })}</span>
        <span>{t('orders.runtimeCalculation.noProduction', { lng: language })}</span>
      </div>
    );
  }
  const largestDelta = learningScore(item);
  const percent = new Intl.NumberFormat(locale, { maximumFractionDigits: 1, style: 'percent' }).format(largestDelta);
  const tone = factor.status === 'matching'
    ? 'bg-bambu-green/10 text-bambu-green'
    : factor.status === 'watch'
      ? 'bg-amber-500/10 text-amber-200'
      : 'bg-red-500/10 text-red-300';
  return (
    <div className="text-xs">
      <span className={`inline-flex rounded-full px-2 py-1 font-medium ${tone}`}>{percent}</span>
      <span className="mt-1 block text-bambu-gray">{t('orders.runtimeCalculation.runS', { lng: language, count: factor.sample_count })}</span>
    </div>
  );
}

export function CalculationList({ items, locale, onOpen, onDuplicate, onCreateOffer, onRevise, onArchive, onDelete, busyId }: Props) {
  const language = resolveSupportedLanguage(locale);
  const { t } = useTranslation(undefined, { lng: language });
  const status: Record<string, string> = { draft: t('orders.runtimeCalculation.statusDraft', { lng: language }), approved: t('orders.runtimeCalculation.statusApproved', { lng: language }), superseded: t('orders.runtimeCalculation.statusSuperseded', { lng: language }), archived: t('orders.runtimeCalculation.statusArchived', { lng: language }) };
  const date = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' });
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection }>({ key: 'updated', direction: 'desc' });
  const sortedItems = useMemo(() => [...items].sort((left, right) => {
    const result = compareItems(left, right, sort.key);
    return sort.direction === 'asc' ? result : -result;
  }), [items, sort]);
  const money = (value: string | null, currency: string) => value === null ? '—' : formatMoney(value, locale, currency);
  const changeSort = (key: SortKey) => setSort(current => current.key === key
    ? { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
    : { key, direction: key === 'updated' || key === 'price' || key === 'cost' || key === 'learning' ? 'desc' : 'asc' });
  const header = (label: string, key: SortKey, align: ColumnAlign = 'left') => {
    const active = sort.key === key;
    const Icon = active ? (sort.direction === 'asc' ? ArrowUp : ArrowDown) : ArrowUpDown;
    const alignment = align === 'center' ? 'text-center' : align === 'right' ? 'text-right' : 'text-left';
    const contentAlignment = align === 'center' ? 'justify-center' : align === 'right' ? 'justify-end' : '';
    return (
      <th className={`${tableHeaderCellClass} ${alignment} cursor-pointer select-none whitespace-nowrap transition-colors hover:text-bambu-green ${active ? '!text-bambu-green' : ''}`} onClick={() => changeSort(key)} aria-sort={active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}>
        <span className={`inline-flex items-center gap-1 ${contentAlignment}`}>{label}<Icon className={`h-3 w-3 ${active ? '' : 'opacity-35'}`} /></span>
      </th>
    );
  };
  return (
    <div className="overflow-x-auto rounded-lg border border-bambu-dark-tertiary">
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
            <th className={`${tableHeaderActionCellClass} sticky right-0 z-10 bg-bambu-dark-tertiary/95`}>{t('common.actions', { lng: language })}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-bambu-dark-tertiary">
          {sortedItems.map(item => {
            const preferred = preferredVariant(item);
            const busy = busyId === item.id;
            const canCreateOffer = item.status === 'approved' && item.current_revision !== null;
            const canRevise = item.status === 'approved';
            const canArchive = item.status === 'approved' || item.status === 'superseded';
            const canDelete = item.status === 'draft';
            return (
              <tr key={item.id} className="group bg-bambu-dark-secondary hover:bg-bambu-dark-tertiary/40">
                <td className="px-4 py-3"><div className="font-medium text-white">K-{String(item.id).padStart(6, '0')}</div><div className="text-xs text-bambu-gray">{item.title}</div></td>
                <td className="px-4 py-3"><div className="text-white">{item.customer_display_name ?? (t('orders.runtimeCalculation.noCustomerAssigned', { lng: language }))}</div><div className="text-xs text-bambu-gray">{item.business_profile_name ?? `#${item.business_profile_id}`}</div></td>
                <td className={`${centeredCellClass} text-white`}>{preferred?.name ?? '—'}</td>
                <td className={`${centeredCellClass} text-bambu-gray`}>{item.current_revision ? `R${item.current_revision}` : '—'}</td>
                <td className={centeredCellClass}><span className="inline-flex items-center gap-1 rounded-full bg-bambu-dark px-2 py-1 text-xs text-bambu-green">{item.status === 'archived' && <Archive className="h-3 w-3" />}{status[item.status]}</span></td>
                <td className={`${centeredCellClass} text-bambu-gray`}>{money(item.production_cost, item.currency)}</td><td className={`${centeredCellClass} font-medium text-white`}>{money(item.selling_price, item.currency)}</td>
                <td className={centeredCellClass}><LearningCell item={item} locale={locale} /></td>
                <td className={`${centeredCellClass} text-bambu-gray`}>{date.format(new Date(item.updated_at))}</td>
                <td className="sticky right-0 bg-bambu-dark-secondary px-4 py-3 shadow-[-14px_0_18px_-18px_rgba(0,0,0,0.85)]">
                  <div className="flex min-w-[224px] justify-end gap-1">
                    <IconButton size="sm" label={t('orders.runtimeCalculation.editCalculation', { lng: language })} title={t('common.edit', { lng: language })} icon={Pencil} disabled={busy} onClick={() => onOpen(item)} className={actionIconClass} />
                    <IconButton size="sm" label={t('orders.runtimeCalculation.duplicateCalculation', { lng: language })} title={t('common.duplicate', { lng: language })} icon={Copy} disabled={busy} onClick={() => onDuplicate(item)} className={actionIconClass} />
                    <IconButton size="sm" label={t('orders.runtimeCalculation.createOfferDraft', { lng: language })} title={t('orders.runtimeCalculation.offer', { lng: language })} icon={Printer} disabled={busy || !canCreateOffer} onClick={() => onCreateOffer(item)} className={actionIconClass} />
                    <IconButton size="sm" label={t('orders.runtimeCalculation.createNewRevision', { lng: language })} title={t('orders.runtimeCalculation.newRevision', { lng: language })} icon={GitBranch} disabled={busy || !canRevise} onClick={() => onRevise(item)} className={actionIconClass} />
                    <IconButton size="sm" label={t('orders.runtimeCalculation.archiveCalculation', { lng: language })} title={t('inventory.bulk.archive', { lng: language })} icon={Archive} disabled={busy || !canArchive} onClick={() => onArchive(item)} className={actionIconClass} />
                    <IconButton size="sm" label={t('orders.runtimeCalculation.deleteCalculation', { lng: language })} title={t('common.delete', { lng: language })} icon={Trash2} disabled={busy || !canDelete} onClick={() => onDelete(item)} className="!rounded-none !border-0 hover:!bg-transparent hover:!text-red-300 focus:!ring-0" />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
