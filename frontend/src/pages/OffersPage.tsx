import { TablePagination } from '../components/ui/TablePagination';
import { OfferDetailsDialog } from '../components/orders/OfferDetailsDialog';
import { offerCalculationTitle, snapshotPart } from '../utils/offerSnapshot';
import { TableActionHeader, TableRowActions, type TableAction } from '../components/ui/TableRowActions';
import { useAuth } from '../contexts/AuthContext';
import { ConfirmModal } from '../components/ConfirmModal';
import { CommercialDocumentDialog } from '../components/orders/CommercialDocumentDialog';
import { OrderFilterChip } from '../components/orders/OrderFilterChip';
import { orderRecordId } from '../utils/orderLinks';
import { OrderSortHeader } from '../components/orders/OrderSortHeader';
import { nextOrderSort, orderValueComparator, type OrderSort } from '../utils/orderSorting';
import { useEffect, useState } from 'react';
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { Calculator, Check, ClipboardList, Eye, FileText, RefreshCw, Search, Send, X, XCircle } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { offersApi, type Offer, type OfferColumn, type OfferPageQuery, type OfferStatus } from '../api/offers';
import { IconButton, Select, TextField } from '../components/ui';
import { OrderHeader, OrderStatus, OrderTable, OrderTableRow, orderControlClass, orderPageClass } from '../components/orders/OrderLayout';
import { tableBodyCellClass, tableHeaderClass, tableHeaderRowClass, tableIdentifierClass, tablePrimaryTextClass } from '../components/ui/tableStyles';
import { formatMoney } from '../utils/calculationFormatting';

function offerCalculationId(offer: Offer) {
  return orderRecordId(String(snapshotPart(offer.snapshot, 'calculation').id ?? ''));
}

const OFFER_STATUSES: OfferStatus[] = ['draft', 'sent', 'accepted', 'rejected'];
const PAGE_SIZES = [15, 25, 30, 50, 100, 200];

export function OffersPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? i18n.language ?? 'en';
  const [sort, setSort] = useState<OrderSort<OfferColumn>>({ key: 'updated', direction: 'desc' });
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const client = useQueryClient();
  const { hasPermission } = useAuth();
  const canRead = hasPermission('commercial_documents:read');
  const canSend = hasPermission('commercial_documents:issue');
  const canAccept = hasPermission('commercial_documents:approve');
  const canReject = hasPermission('commercial_documents:correct');
  const canReadOrders = hasPermission('orders:read');
  const canReadCalculations = hasPermission('calculations:read');
  const [filter, setFilter] = useState<OfferStatus | ''>('');
  const [search, setSearch] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [pageSize, setPageSize] = useState(25);
  const [position, setPosition] = useState({ scope: '', offset: 0 });
  const [acceptTarget, setAcceptTarget] = useState<Offer | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [documentId, setDocumentId] = useState<number | null>(null);
  const customerFilter = orderRecordId(params.get('customer'));
  const profileFilter = orderRecordId(params.get('profile'));
  const calculationFilter = orderRecordId(params.get('calculation'));
  const selectedId = orderRecordId(params.get('offer'));
  const scope = `${customerFilter}:${profileFilter}:${calculationFilter}`;
  const offset = position.scope === scope ? position.offset : 0;
  const statusLabel = (status: OfferStatus) => ({ draft: t('settings.documentLayout.statuses.draft', { lng: locale }), sent: t('orders.runtimeCalculation.sent', { lng: locale }), accepted: t('orders.runtimeCalculation.accepted', { lng: locale }), rejected: t('orders.runtimeCalculation.rejected', { lng: locale }) })[status];
  const query: OfferPageQuery = {
    status: filter || undefined,
    customer_id: customerFilter ?? undefined,
    business_profile_id: customerFilter === null ? undefined : profileFilter ?? undefined,
    calculation_id: calculationFilter ?? undefined,
    q: searchQuery || undefined,
    sort_by: sort.key,
    sort_dir: sort.direction,
    status_order: sort.key === 'status' ? [...OFFER_STATUSES].sort(orderValueComparator(statusLabel, 'asc', locale)) : undefined,
    offset,
    limit: pageSize,
  };
  const listing = useQuery({
    queryKey: ['offers', 'page', query],
    queryFn: () => offersApi.page(query),
    enabled: canRead,
    placeholderData: keepPreviousData,
  });
  const page = listing.data;
  const offers = page?.items ?? [];
  const error = actionError ?? (listing.error?.message || null);

  useEffect(() => {
    const next = search.trim();
    if (next === searchQuery) return;
    const timer = window.setTimeout(() => {
      setSearchQuery(next);
      setPosition({ scope, offset: 0 });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [scope, search, searchQuery]);

  useEffect(() => {
    if (!page || listing.isPlaceholderData || page.items.length > 0 || offset === 0) return;
    const lastOffset = Math.max(0, Math.floor((page.total - 1) / page.limit) * page.limit);
    setPosition({ scope, offset: lastOffset });
  }, [listing.isPlaceholderData, offset, page, scope]);

  function changeParams(change: (next: URLSearchParams) => void) {
    const next = new URLSearchParams(params);
    change(next);
    setParams(next, { replace: true });
  }

  const action = async (offer: Offer, kind: 'send' | 'reject' | 'accept') => {
    const permitted = { send: canSend, accept: canAccept, reject: canReject }[kind];
    if (!permitted || busyId !== null) return;
    setBusyId(offer.id);
    setActionError(null);
    try {
      if (kind === 'send') await offersApi.send(offer.id, offer.version);
      else if (kind === 'reject') await offersApi.reject(offer.id, offer.version);
      else await offersApi.accept(offer.id, offer.version, `accept-${offer.id}-${Date.now()}`);
      await client.invalidateQueries({ queryKey: ['offers'] });
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === 'reservation_blocked') setActionError(t('orders.runtimeCalculation.reservationBlocked', { lng: locale, message: reason.message }));
      else setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusyId(null);
    }
  };
  const title = t('printops.nav.offers', { lng: locale });
  const offerText = (key: string) => t(`orders.runtimeCalculation.${key}`, { lng: locale });
  const columns: { key: OfferColumn; label: string; align?: 'center' }[] = [
    { key: 'number', label: offerText('offer') },
    { key: 'calculation', label: t('printops.nav.calculation', { lng: locale }) },
    { key: 'customer', label: t('orders.customers.customer', { lng: locale }) },
    { key: 'revision', label: offerText('revisionLabel'), align: 'center' },
    { key: 'price', label: t('inventory.net', { lng: locale }), align: 'center' },
    { key: 'status', label: t('common.status', { lng: locale }), align: 'center' },
    { key: 'updated', label: offerText('updatedOffersPage'), align: 'center' },
  ];
  const openOffer = (id: number) => changeParams(next => next.set('offer', String(id)));

  function rowActions(offer: Offer): TableAction[] {
    const calculationId = offerCalculationId(offer);
    const busy = busyId !== null;
    return [
      { icon: Eye, label: t('orders.rowActions.openOffer'), onSelect: () => openOffer(offer.id) },
      ...(offer.quotation_document_id !== null ? [{
        icon: FileText, label: t('orders.rowActions.openDocument'), onSelect: () => setDocumentId(offer.quotation_document_id),
      }] : []),
      ...(canReadCalculations && calculationId !== null ? [{
        icon: Calculator, label: t('orders.runtimeDashboard.openCalculation'), onSelect: () => navigate(`/orders/calculation?open=${calculationId}`),
      }] : []),
      ...(canReadOrders && offer.order_id ? [{
        icon: ClipboardList, label: t('orders.rowActions.openOrder'), onSelect: () => navigate(`/orders/${offer.order_id}`),
      }] : []),
      ...(canSend && offer.status === 'draft' ? [{
        icon: Send, label: offerText('sendOffer'), disabled: busy, onSelect: () => void action(offer, 'send'),
      }] : []),
      ...(offer.status === 'sent' ? [
        ...(canAccept ? [{ icon: Check, label: offerText('acceptOffer'), disabled: busy, onSelect: () => setAcceptTarget(offer) }] : []),
        ...(canReject ? [{ icon: XCircle, label: offerText('rejectOffer'), disabled: busy, destructive: true, onSelect: () => void action(offer, 'reject') }] : []),
      ] : []),
    ];
  }

  return (
    <div className={orderPageClass}>
      <OrderHeader icon={FileText} title={title} description={offerText('draftSendAndAcceptWithBindingStockReservation')}>
        <div className="relative w-full min-w-0 sm:w-64">
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-table-secondary" />
          <TextField
            type="search"
            maxLength={200}
            aria-label={offerText('searchOffers')}
            placeholder={offerText('searchOffersPlaceholder')}
            value={search}
            onValueChange={setSearch}
            className={`${orderControlClass} pl-10 pr-11 placeholder:text-table-secondary! [&::-webkit-search-cancel-button]:appearance-none`}
          />
          {search && <IconButton type="button" size="sm" icon={X} label={offerText('clearSearch')}
            className="absolute inset-y-0 right-0 my-auto" onClick={() => {
              setSearch('');
              setSearchQuery('');
              setPosition({ scope, offset: 0 });
            }} />}
        </div>
        <Select
          ariaLabel={offerText('filterOfferStatus')}
          value={filter}
          onValueChange={value => {
            setFilter(value);
            setPosition({ scope, offset: 0 });
          }}
          options={[
            { value: '', label: t('printers.filter.allStatuses', { lng: locale }) },
            ...OFFER_STATUSES.map(value => ({ value, label: statusLabel(value) })),
          ]}
          className="max-w-full sm:min-w-44"
          controlClassName={orderControlClass}
        />
      </OrderHeader>
      {(customerFilter !== null || calculationFilter !== null) && <div className="flex flex-wrap gap-2">
        {customerFilter !== null && <OrderFilterChip label={`${t('orders.customers.customer')} #${customerFilter}`}
          onClear={() => changeParams(next => { next.delete('customer'); next.delete('profile'); })} />}
        {calculationFilter !== null && <OrderFilterChip label={`${t('printops.nav.calculation')} #${calculationFilter}`}
          onClear={() => changeParams(next => next.delete('calculation'))} />}
      </div>}
      {error && (
        <div role="alert" className="flex items-center justify-between rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-red-700 dark:text-red-300">
          <span>{error}</span>
          {listing.isError && <IconButton label={t('common.retry', { lng: locale })} icon={RefreshCw} onClick={() => void listing.refetch()} />}
        </div>
      )}
      <OrderTable label={title} footer={page && <TablePagination total={page.total} offset={page.offset} pageSize={pageSize}
          busy={listing.isPlaceholderData} sizes={PAGE_SIZES}
          onOffsetChange={offset => setPosition({ scope, offset })}
          onPageSizeChange={value => { setPageSize(value); setPosition({ scope, offset: 0 }); }} />}>
        <table className="w-full min-w-[860px] text-sm">
          <thead className={tableHeaderClass}>
            <tr className={tableHeaderRowClass}>
              {columns.map(({ key, label, align }) => (
                <OrderSortHeader key={key} label={label} align={align} direction={sort.key === key ? sort.direction : undefined}
                  onSort={() => {
                    setSort(current => nextOrderSort(current, key, key === 'price' || key === 'updated' ? 'desc' : 'asc'));
                    setPosition({ scope, offset: 0 });
                  }} />
              ))}
              <TableActionHeader />
            </tr>
          </thead>
          <tbody>
            {listing.isLoading || offers.length === 0 ? (
              <tr><td colSpan={8} className="p-10 text-center text-table-secondary">{offerText(listing.isLoading ? 'loadingOffers' : searchQuery ? 'noOffersMatchSearch' : 'noOffersYet')}</td></tr>
            ) : offers.map(offer => {
              const calculation = snapshotPart(offer.snapshot, 'calculation');
              const revision = snapshotPart(offer.snapshot, 'revision');
              const currency = String(revision.currency ?? calculation.currency ?? 'EUR');
              const tone = offer.status === 'accepted' ? 'positive' : offer.status === 'rejected' ? 'danger' : 'neutral';
              return (
                <OrderTableRow key={offer.id} onOpen={() => openOffer(offer.id)}>
                  <td className={tableBodyCellClass}>
                    <div className={`${tableIdentifierClass} text-white`}>{offer.number}</div>
                    {offer.quotation_document_id && <div className="mt-0.5 text-xs text-table-secondary">{offerText('document')} #{offer.quotation_document_id}</div>}
                  </td>
                  <td className={tableBodyCellClass}><span className={tablePrimaryTextClass}>{offerCalculationTitle(calculation)}</span></td>
                  <td className={tableBodyCellClass}>
                    <span className="block max-w-64 wrap-break-word">{offer.customer_display_name || offerText('noCustomerOffersPage')}</span>
                  </td>
                  <td className={`${tableBodyCellClass} text-center`}>{String(revision.revision_number ?? '–')}</td>
                  <td className={`${tableBodyCellClass} whitespace-nowrap text-center tabular-nums`}>{formatMoney(String(revision.selling_price ?? 0), locale, currency)}</td>
                  <td className={`${tableBodyCellClass} text-center`}><OrderStatus tone={tone}>{statusLabel(offer.status)}</OrderStatus></td>
                  <td className={`${tableBodyCellClass} whitespace-nowrap text-center tabular-nums`}>{new Date(offer.updated_at).toLocaleString(locale)}</td>
                  <TableRowActions subject={offer.number} actions={rowActions(offer)} />
                </OrderTableRow>
              );
            })}
          </tbody>
        </table>
      </OrderTable>
      {acceptTarget && canAccept && (
        <ConfirmModal
          title={offerText('acceptOfferConfirmTitle')}
          message={offerText('acceptOfferAndReserveStock')}
          confirmText={offerText('acceptOffer')}
          variant="warning"
          isLoading={busyId === acceptTarget.id}
          onConfirm={() => {
            if (busyId === null) void action(acceptTarget, 'accept').then(() => setAcceptTarget(null));
          }}
          onCancel={() => setAcceptTarget(null)}
        />
      )}
      {selectedId !== null && canRead && (
        <OfferDetailsDialog key={selectedId} id={selectedId} locale={locale} statusLabel={statusLabel}
          onClose={() => changeParams(next => next.delete('offer'))} />
      )}
      {documentId !== null && <CommercialDocumentDialog key={documentId} id={documentId} onClose={() => setDocumentId(null)} />}
    </div>
  );
}
