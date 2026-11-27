import { TablePagination } from '../components/ui/TablePagination';
import { TableActionHeader, TableRowActions, type TableAction } from '../components/ui/TableRowActions';
import { CommercialDocumentDialog } from '../components/orders/CommercialDocumentDialog';
import { downloadBlob } from '../utils/clipboard';
import { useTranslation } from 'react-i18next';
import { OrderSortHeader } from '../components/orders/OrderSortHeader';
import { nextOrderSort, type OrderSort } from '../utils/orderSorting';
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, Eye, FileText, Receipt, RefreshCw } from 'lucide-react';
import { api } from '../api/client';
import { lexwareDocumentsApi, type LexwareDocument, type LexwareDocumentSortKey } from '../api/client/lexware-documents';
import { Button } from '../components/Button';
import { dashboardStyles } from '../components/dashboardStyles';
import { OrderHeader, OrderStatus, OrderTable, OrderTableRow, orderControlClass, orderPageClass, orderPanelClass } from '../components/orders/OrderLayout';
import { tableBodyCellClass, tableHeaderClass, tableHeaderRowClass, tableIdentifierClass } from '../components/ui/tableStyles';
import { LexwareDocumentDetail } from '../components/lexware-documents/LexwareDocumentDetail';
import { displayMoney, documentCodeLabel, useLexwareDocumentLabels } from '../components/lexware-documents/labels';
import { Select } from '../components/ui';
import { WarehouseToolbar } from '../components/warehouse/WarehouseLayout';
import { useAuth } from '../contexts/AuthContext';

const types = ['invoice', 'creditnote', 'quotation', 'orderconfirmation', 'salesinvoice', 'salescreditnote', 'purchaseinvoice', 'purchasecreditnote', 'downpaymentinvoice', 'deliverynote'];

export default function LexwareDocumentsPage() {
  const labels = useLexwareDocumentLabels();
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canRead = hasPermission('commercial_documents:read');
  const canFinance = hasPermission('payments:read');
  const canLink = canFinance && hasPermission('commercial_documents:draft');
  const [search, setSearch] = useState('');
  const [voucherType, setVoucherType] = useState('');
  const [profile, setProfile] = useState('');
  const [sort, setSort] = useState<OrderSort<LexwareDocumentSortKey>>({ key: 'date', direction: 'desc' });
  const activeSort = !canFinance && sort.key === 'open' ? { key: 'date', direction: 'desc' } as const : sort;
  const [offset, setOffset] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [selected, setSelected] = useState<number | null>(null);
  const [localDocument, setLocalDocument] = useState<number | null>(null);
  const [downloadError, setDownloadError] = useState(false);
  const [downloading, setDownloading] = useState<number | null>(null);
  const filters = { search, voucher_type: voucherType, business_profile_id: profile ? Number(profile) : undefined, offset, limit: pageSize, sort: activeSort.key, direction: activeSort.direction };
  const profiles = useQuery({ queryKey: ['business-profile-options'], queryFn: () => api.getBusinessProfileOptions(), enabled: canRead });
  const documentFilters = [search, voucherType, profile, canFinance] as const;
  const listing = useQuery({
    queryKey: ['lexware-documents', 'list', ...documentFilters, offset, pageSize, activeSort],
    queryFn: () => lexwareDocumentsApi.list(filters),
    enabled: canRead,
    placeholderData: (previous, query) =>
      documentFilters.every((value, index) => query?.queryKey[index + 2] === value) ? previous : undefined,
  });
  const total = listing.data?.total;
  useEffect(() => {
    if (!listing.isPlaceholderData && total !== undefined && offset > 0 && offset >= total) {
      setOffset(Math.max(0, Math.ceil(total / pageSize) - 1) * pageSize);
    }
  }, [listing.isPlaceholderData, offset, pageSize, total]);
  const finance = useQuery({ queryKey: ['lexware-finance', profile], queryFn: () => lexwareDocumentsApi.finance({ business_profile_id: filters.business_profile_id }), enabled: canRead && canFinance });
  const detail = useQuery({ queryKey: ['lexware-documents', 'detail', selected, canFinance], queryFn: () => lexwareDocumentsApi.detail(selected!), enabled: canRead && selected !== null });
  function resetFilter(action: () => void) { action(); setOffset(0); setSelected(null); }
  const sortHeader = (key: LexwareDocumentSortKey, label: string, align?: 'center') => (
    <OrderSortHeader label={label} align={align} direction={activeSort.key === key ? activeSort.direction : undefined}
      onSort={() => resetFilter(() => setSort(nextOrderSort(activeSort, key, key === 'date' || key === 'open' ? 'desc' : 'asc')))} />
  );
  async function reload() { await Promise.all([listing.refetch(), ...(canFinance ? [finance.refetch()] : []), ...(selected !== null ? [detail.refetch()] : [])]); }
  async function downloadOriginal(document: LexwareDocument, fileId: string) {
    if (!canFinance || downloading !== null) return;
    setDownloading(document.id);
    setDownloadError(false);
    try {
      const file = await lexwareDocumentsApi.download(document.id, fileId);
      downloadBlob(file.blob, file.filename);
    } catch {
      setDownloadError(true);
    } finally {
      setDownloading(null);
    }
  }

  function rowActions(document: LexwareDocument): TableAction[] {
    const files = document.files?.filter(file => file.cached || document.connection_enabled) ?? [];
    return [
      { icon: Eye, label: labels.details, onSelect: () => setSelected(document.id) },
      ...(document.local_document_id !== null ? [{
        icon: FileText, label: t('orders.rowActions.openDocument'), onSelect: () => setLocalDocument(document.local_document_id),
      }] : []),
      ...(canFinance && files.length === 1 ? [{
        icon: Download, label: labels.download, disabled: downloading !== null,
        onSelect: () => void downloadOriginal(document, files[0]!.file_id),
      }] : []),
    ];
  }
  if (!canRead) return <p className="p-6">{labels.denied}</p>;
  return <div className={orderPageClass}>
    <OrderHeader icon={Receipt} title={labels.title} description={labels.description}>
      <Button variant="secondary" className="max-[768px]:min-h-[44px]!" onClick={() => void reload()} loading={listing.isFetching}><RefreshCw aria-hidden="true" size={16} />{labels.refresh}</Button>
    </OrderHeader>
    <Select
      className="max-w-sm"
      controlClassName={orderControlClass}
      label={labels.profile}
      value={profile}
      options={[
        { value: '', label: labels.allProfiles },
        ...(profiles.data ?? []).map(item => ({ value: String(item.id), label: item.name })),
      ]}
      onValueChange={value => resetFilter(() => setProfile(value))}
    />
    {canFinance && <section className={`${orderPanelClass} space-y-3`} aria-label={labels.financeTitle}>
      <h2 className={dashboardStyles.cardTitle}>{labels.financeTitle}</h2><p className="text-sm text-table-secondary">{labels.financeNote}</p>
      {finance.isLoading && <p role="status">{labels.loading}</p>}
      {finance.isError && <p role="alert">{labels.error} <Button variant="ghost" onClick={() => void finance.refetch()}>{labels.retry}</Button></p>}
      {finance.data && <>
        {finance.data.totals.map(total => <div key={total.currency} className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg bg-bambu-dark p-4"><p>{labels.receivables}</p><p className={dashboardStyles.metricValue}>{total.receivables} {total.currency}</p><p className="text-xs text-amber-800 dark:text-amber-300">{labels.overdue}: {total.overdue_receivables} {total.currency}</p></div>
          <div className="rounded-lg bg-bambu-dark p-4"><p>{labels.payables}</p><p className={dashboardStyles.metricValue}>{total.payables} {total.currency}</p><p className="text-xs text-amber-800 dark:text-amber-300">{labels.overdue}: {total.overdue_payables} {total.currency}</p></div>
        </div>)}
        <p className="text-sm">{labels.linked}: {finance.data.linked_count} · {labels.unknownCount}: {finance.data.unknown_count} · {labels.excluded}: {finance.data.excluded_count}</p>
        <p className="text-sm text-table-secondary">{labels.credits}</p>
        {finance.data.stale_connection_count > 0 && <p className="text-amber-800 dark:text-amber-300" role="status">{labels.stale}</p>}
      </>}
    </section>}
    <WarehouseToolbar searchLabel={labels.search} value={search} onSearch={value => resetFilter(() => setSearch(value))}>
      <Select
        className="w-full sm:w-64"
        controlClassName={orderControlClass}
        ariaLabel={labels.type}
        value={voucherType}
        options={[
          { value: '', label: labels.allTypes },
          ...types.map(type => ({ value: type, label: documentCodeLabel(labels, 'type', type) })),
        ]}
        onValueChange={value => resetFilter(() => setVoucherType(value))}
      />
    </WarehouseToolbar>
    {downloadError && <p role="alert" className="text-red-700 dark:text-red-300">{labels.actionError}</p>}
    {listing.isLoading && <p role="status">{labels.loading}</p>}
    {listing.isError && <p role="alert">{labels.error} <Button variant="ghost" onClick={() => void listing.refetch()}>{labels.retry}</Button></p>}
    {listing.data?.items.length === 0 && <p className={orderPanelClass}>{labels.empty}</p>}
    {!!listing.data?.items.length && (
      <OrderTable label={labels.title} footer={<TablePagination total={listing.data.total} offset={offset} pageSize={pageSize}
        sizes={[15, 25, 30, 50, 100]} busy={listing.isPlaceholderData}
        onOffsetChange={setOffset} onPageSizeChange={value => resetFilter(() => setPageSize(value))} />}>
        <table aria-busy={listing.isPlaceholderData || undefined} className="w-full min-w-[800px] text-sm">
          <thead className={tableHeaderClass}>
            <tr className={tableHeaderRowClass}>
              {sortHeader('number', labels.number)}
              {sortHeader('type', labels.type)}
              {sortHeader('contact', labels.contact)}
              {sortHeader('date', labels.date, 'center')}
              {sortHeader('status', labels.status, 'center')}
              {canFinance && sortHeader('open', labels.open, 'center')}
              <TableActionHeader />
            </tr>
          </thead>
          <tbody>
            {listing.data.items.map(document => (
              <OrderTableRow key={document.id} onOpen={() => setSelected(document.id)}>
                <td className={tableBodyCellClass}>
                  <span className={`${tableIdentifierClass} text-white`}>{document.voucher_number || '—'}</span>
                  <small className="block text-xs text-table-secondary">Lexware · {document.company_name}</small>
                  {document.local_document_id && <small className="block text-xs text-table-secondary">PrintOps #{document.local_document_id}</small>}
                </td>
                <td className={tableBodyCellClass}>
                  {documentCodeLabel(labels, 'type', document.voucher_type)}
                  {!document.supported && <div className="mt-1"><OrderStatus tone="warning">{labels.unsupported}</OrderStatus></div>}
                </td>
                <td className={tableBodyCellClass}>{document.contact_name || '—'}</td>
                <td className={`${tableBodyCellClass} whitespace-nowrap text-center tabular-nums`}>{document.voucher_date || '—'}</td>
                <td className={`${tableBodyCellClass} text-center`}>
                  <OrderStatus tone={document.finance?.overdue ? 'danger' : document.finance?.payment_status === 'balanced' ? 'positive' : 'neutral'}>
                    {documentCodeLabel(labels, 'status', document.voucher_status)}
                  </OrderStatus>
                  {document.archived && <small className="mt-1 block text-xs">{labels.archived}</small>}
                  {!document.connection_enabled && <small className="mt-1 block text-xs text-amber-800 dark:text-amber-300">{labels.stale}</small>}
                  {!document.in_latest_sync && <small className="mt-1 block text-xs text-amber-800 dark:text-amber-300">{labels.missing}</small>}
                </td>
                {canFinance && <td className={`${tableBodyCellClass} whitespace-nowrap text-center tabular-nums`}>{document.finance?.payment_state === 'not_applicable' ? labels.notApplicable : displayMoney(document.finance?.open_amount, document.finance?.currency || '', labels.unknown)}</td>}
                <TableRowActions subject={document.voucher_number || document.external_id} actions={rowActions(document)} />
              </OrderTableRow>
            ))}
          </tbody>
        </table>
      </OrderTable>
    )}
    {localDocument !== null && <CommercialDocumentDialog key={localDocument} id={localDocument} onClose={() => setLocalDocument(null)} />}
    {selected !== null && detail.isLoading && <p role="status">{labels.loading}</p>}
    {selected !== null && detail.isError && <p role="alert">{labels.error} <Button variant="ghost" onClick={() => void detail.refetch()}>{labels.retry}</Button></p>}
    {selected !== null && detail.data && <LexwareDocumentDetail key={detail.data.id} document={detail.data} canFinance={canFinance} canLink={canLink} onClose={() => setSelected(null)} />}
  </div>;
}
