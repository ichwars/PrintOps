import { TablePagination } from '../components/ui/TablePagination';
import { useTablePagination } from '../hooks/useTablePagination';
import { TableActionHeader, TableRowActions, type TableAction } from '../components/ui/TableRowActions';
import { CommercialDocumentDialog } from '../components/orders/CommercialDocumentDialog';
import { OrderFilterChip } from '../components/orders/OrderFilterChip';
import { orderRecordId } from '../utils/orderLinks';
import { OrderSortHeader } from '../components/orders/OrderSortHeader';
import { nextOrderSort, orderValueComparator, type OrderSort } from '../utils/orderSorting';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Calculator, Check, ClipboardList, Eye, FileText, Receipt } from 'lucide-react';
import { OrderHeader, OrderStatus, OrderTable, OrderTableRow, orderPageClass } from '../components/orders/OrderLayout';
import { WarehouseSegment, WarehouseSegments } from '../components/warehouse/WarehouseLayout';
import { Button, LegacyDatePicker, Modal, Select, TextArea, TextField } from '../components/ui';
import { tableBodyCellClass, tableHeaderCellClass, tableHeaderClass, tableHeaderRowClass, tableIdentifierClass } from '../components/ui/tableStyles';
import { useAuth } from '../contexts/AuthContext';
import {
  documentManagementApi,
  type CommercialDocument,
  type DocumentFilters,
  type PaymentMethod,
  type RecordPaymentInput,
} from '../api/documentManagement';
import { formatMoney } from '../utils/calculationFormatting';

type OrderPageCopy = { "empty": string; "foundation": string; "page": { "overview": { "title": string; "subtitle": string; "columns": string[]; }; "calculation": { "title": string; "subtitle": string; "columns": string[]; }; "offers": { "title": string; "subtitle": string; "columns": string[]; }; "invoices": { "title": string; "subtitle": string; "columns": string[]; }; }; };

type OrderSectionId = 'overview' | 'calculation' | 'offers' | 'invoices';
type InvoiceSortMode = 'priority' | 'due' | 'amount' | 'created';
const invoiceColumns = ['number', 'customer', 'due'] as const;
type InvoiceColumn = typeof invoiceColumns[number];
type InvoiceFilterMode = 'all' | 'open' | 'overdue' | 'paid';

const invoiceTypes = new Set(['advance_invoice', 'progress_invoice', 'final_invoice', 'invoice']);
function amountValue(value: string | number | null | undefined) {
  const parsed = Number(String(value ?? '0').replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : 0;
}

function dateValue(value: string | null | undefined) {
  if (!value) return Number.POSITIVE_INFINITY;
  const parsed = parseBusinessDate(value)?.getTime() ?? Number.NaN;
  return Number.isFinite(parsed) ? parsed : Number.POSITIVE_INFINITY;
}

function invoicePriority(document: CommercialDocument) {
  const openAmount = amountValue(document.open_amount);
  if (openAmount <= 0 || document.payment_status === 'paid') return 4;
  if (document.due_date && dateValue(document.due_date) < Date.now()) return 0;
  if (document.payment_status === 'partially_paid') return 1;
  if (document.payment_status === 'unpaid') return 2;
  return 3;
}

function isInvoiceFilterMode(value: string | null): value is InvoiceFilterMode {
  return value === 'all' || value === 'open' || value === 'overdue' || value === 'paid';
}

function isInvoiceSortMode(value: string | null): value is InvoiceSortMode {
  return value === 'priority' || value === 'due' || value === 'amount' || value === 'created';
}

function isOpenInvoice(document: CommercialDocument) {
  return amountValue(document.open_amount) > 0 && document.payment_status !== 'paid';
}

function isOverdueInvoice(document: CommercialDocument) {
  return isOpenInvoice(document) && Boolean(document.due_date) && dateValue(document.due_date) < Date.now();
}

function paymentTone(status: string) {
  if (status === 'paid') return 'positive';
  if (status === 'partially_paid' || status === 'overpaid') return 'warning';
  return 'neutral';
}

function todayIso() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, '0');
  const day = String(today.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function parseBusinessDate(value: string | null | undefined) {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const date = match
    ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
    : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function normalizeDecimalInput(value: string) {
  return value.trim().replace(/\s/g, '').replace(',', '.');
}

function getSection(pathname: string): OrderSectionId {
  if (pathname.endsWith('/calculation')) return 'calculation';
  if (pathname.endsWith('/offers')) return 'offers';
  if (pathname.endsWith('/invoices')) return 'invoices';
  return 'overview';
}

export function OrdersPage() {
  const { t, i18n } = useTranslation();
  const { hasPermission } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const activeSection = getSection(location.pathname);
  const copy = t('orders.runtimeDomain.orderPage', { returnObjects: true }) as unknown as OrderPageCopy;
  const locale = i18n.language || 'de-DE';
  const invoiceText = (key: string, options?: Record<string, unknown>) => t(`orders.runtimeDomain.nativeInvoices.${key}`, options);
  const methodLabels = t('orders.runtimeDomain.paymentMethods', { returnObjects: true }) as unknown as Record<PaymentMethod, string>;
  const paymentStatusLabels = t('orders.runtimeDomain.paymentStatuses', { returnObjects: true }) as unknown as Record<string, string>;
  const invoiceSortOptions: Array<{ value: InvoiceSortMode; label: string }> = (['priority', 'due', 'amount', 'created'] as const).map((value) => ({ value, label: t(`orders.runtimeDomain.invoiceSort.${value}`) }));
  const invoiceFilterOptions: Array<{ value: InvoiceFilterMode; label: string }> = (['all', 'open', 'overdue', 'paid'] as const).map((value) => ({ value, label: t(`orders.runtimeDomain.invoiceFilter.${value}`) }));
  const documentNumber = (document: CommercialDocument) => document.number ?? invoiceText('documentNumber', { id: document.id });
  const columns = copy.page[activeSection].columns;
  const canManagePayments = hasPermission('payments:manage');
  const canReadDocuments = hasPermission('commercial_documents:read');
  const canReadOrders = hasPermission('orders:read');
  const [documentId, setDocumentId] = useState<number | null>(null);
  const [paymentTarget, setPaymentTarget] = useState<CommercialDocument | null>(null);
  const initialInvoiceParams = new URLSearchParams(location.search);
  const customerFilter = orderRecordId(initialInvoiceParams.get('customer'));
  const profileFilter = orderRecordId(initialInvoiceParams.get('profile'));
  const documentFilters: DocumentFilters | undefined = customerFilter === null ? undefined : {
    customerId: customerFilter,
    businessProfileId: profileFilter ?? undefined,
  };
  const [paymentDraft, setPaymentDraft] = useState<RecordPaymentInput>({
    amount: '',
    paid_at: todayIso(),
    method: 'bank_transfer',
    reference: '',
    note: '',
  });
  const [handledPaymentParam, setHandledPaymentParam] = useState<string | null>(null);
  const [invoiceSort, setInvoiceSort] = useState<InvoiceSortMode>(() => {
    const sortParam = initialInvoiceParams.get('sort');
    return isInvoiceSortMode(sortParam) ? sortParam : 'priority';
  });
  const [columnSort, setColumnSort] = useState<OrderSort<InvoiceColumn> | null>(null);
  const [invoiceFilter, setInvoiceFilter] = useState<InvoiceFilterMode>(() => {
    const filterParam = initialInvoiceParams.get('filter');
    return isInvoiceFilterMode(filterParam) ? filterParam : 'all';
  });
  const paymentParam = useMemo(() => new URLSearchParams(location.search).get('payment'), [location.search]);
  const invoiceFilterParam = useMemo(() => new URLSearchParams(location.search).get('filter'), [location.search]);
  const invoiceSortParam = useMemo(() => new URLSearchParams(location.search).get('sort'), [location.search]);
  const paymentDocumentId = useMemo(() => {
    if (!paymentParam) return null;
    const parsed = Number(paymentParam);
    return Number.isFinite(parsed) ? parsed : null;
  }, [paymentParam]);
  const clearPaymentParam = useCallback(() => {
    const next = new URLSearchParams(location.search);
    if (!next.has('payment')) return;
    next.delete('payment');
    navigate(
      {
        pathname: location.pathname,
        search: next.toString() ? `?${next.toString()}` : '',
      },
      { replace: true },
    );
  }, [location.pathname, location.search, navigate]);
  const activeIcons = {
    overview: ClipboardList,
    offers: FileText,
    calculation: Calculator,
    invoices: Receipt,
  } satisfies Record<OrderSectionId, typeof ClipboardList>;
  const ActiveIcon = activeIcons[activeSection];
  const documentsQuery = useQuery({
    queryKey: ['commercial-documents', 'invoices', documentFilters],
    queryFn: () => documentFilters ? documentManagementApi.listDocuments(documentFilters) : documentManagementApi.listDocuments(),
    enabled: activeSection === 'invoices',
  });
  const allInvoiceDocuments = useMemo(
    () => (documentsQuery.data ?? [])
      .filter((document) => invoiceTypes.has(document.document_type) && document.payment_status !== 'not_applicable'),
    [documentsQuery.data],
  );
  const invoiceFilterCounts = useMemo(() => ({
    all: allInvoiceDocuments.length,
    open: allInvoiceDocuments.filter(isOpenInvoice).length,
    overdue: allInvoiceDocuments.filter(isOverdueInvoice).length,
    paid: allInvoiceDocuments.filter((document) => !isOpenInvoice(document)).length,
  }), [allInvoiceDocuments]);
  const activeColumnSort = columnSort ?? (invoiceSort === 'due' ? { key: 'due', direction: 'asc' } as const : null);
  const invoiceDocuments = useMemo(
    () => {
      const filtered = allInvoiceDocuments.filter((document) => {
        if (paymentDocumentId !== null && document.id === paymentDocumentId) return true;
        if (invoiceFilter === 'open') return isOpenInvoice(document);
        if (invoiceFilter === 'overdue') return isOverdueInvoice(document);
        if (invoiceFilter === 'paid') return !isOpenInvoice(document);
        return true;
      });

      const sortValues = {
        number: (document: CommercialDocument) => document.number ?? `#${document.id}`,
        customer: (document: CommercialDocument) => document.customer_display_name,
        due: (document: CommercialDocument) => dateValue(document.due_date),
      };
      const compareColumn = columnSort && orderValueComparator(sortValues[columnSort.key], columnSort.direction, locale);
      return [...filtered].sort((left, right) => {
        if (paymentDocumentId !== null && columnSort?.key !== 'customer') {
          if (left.id === paymentDocumentId) return -1;
          if (right.id === paymentDocumentId) return 1;
        }

        if (compareColumn) return compareColumn(left, right);
        if (invoiceSort === 'due') {
          return dateValue(left.due_date) - dateValue(right.due_date);
        }
        if (invoiceSort === 'amount') {
          return amountValue(right.open_amount) - amountValue(left.open_amount);
        }
        if (invoiceSort === 'created') {
          return dateValue(right.created_at) - dateValue(left.created_at);
        }

        return invoicePriority(left) - invoicePriority(right)
          || dateValue(left.due_date) - dateValue(right.due_date)
          || amountValue(right.open_amount) - amountValue(left.open_amount);
      });
    },
    [allInvoiceDocuments, columnSort, invoiceFilter, invoiceSort, locale, paymentDocumentId],
  );
  const invoiceSummary = useMemo(() => {
    const openDocuments = allInvoiceDocuments.filter(isOpenInvoice);
    const overdueDocuments = allInvoiceDocuments.filter(isOverdueInvoice);
    const openAmount = openDocuments.reduce((sum, document) => sum + amountValue(document.open_amount), 0);
    return {
      openCount: openDocuments.length,
      overdueCount: overdueDocuments.length,
      openAmount,
      currency: openDocuments[0]?.currency ?? allInvoiceDocuments[0]?.currency ?? 'EUR',
    };
  }, [allInvoiceDocuments]);
  const recordPayment = useMutation({
    mutationFn: ({ documentId, input }: { documentId: number; input: RecordPaymentInput }) =>
      documentManagementApi.recordPayment(documentId, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['commercial-documents'] });
      await queryClient.invalidateQueries({ queryKey: ['business-dashboard', 'commercial-documents'] });
      setPaymentTarget(null);
      clearPaymentParam();
    },
  });

  const openPaymentDialog = useCallback((document: CommercialDocument) => {
    setPaymentTarget(document);
    setPaymentDraft({
      amount: String(document.open_amount ?? document.total_amount ?? ''),
      paid_at: todayIso(),
      method: 'bank_transfer',
      reference: '',
      note: '',
    });
  }, []);

  useEffect(() => {
    if (activeSection !== 'invoices') return;

    if (!paymentParam || handledPaymentParam === paymentParam) return;

    if (paymentDocumentId === null) {
      setHandledPaymentParam(paymentParam);
      return;
    }

    const document = invoiceDocuments.find((item) => item.id === paymentDocumentId);
    if (!document) return;

    setHandledPaymentParam(paymentParam);
    if (canManagePayments && document.open_amount !== '0.00' && document.payment_status !== 'paid') {
      openPaymentDialog(document);
    }
  }, [activeSection, canManagePayments, handledPaymentParam, invoiceDocuments, openPaymentDialog, paymentDocumentId, paymentParam]);

  useEffect(() => {
    const nextFilter = isInvoiceFilterMode(invoiceFilterParam) ? invoiceFilterParam : 'all';
    if (nextFilter !== invoiceFilter) setInvoiceFilter(nextFilter);

    const nextSort = isInvoiceSortMode(invoiceSortParam) ? invoiceSortParam : 'priority';
    if (nextSort !== invoiceSort) setInvoiceSort(nextSort);
  }, [invoiceFilter, invoiceFilterParam, invoiceSort, invoiceSortParam]);

  const updateInvoiceParam = useCallback((key: 'filter' | 'sort', value: InvoiceFilterMode | InvoiceSortMode) => {
    const next = new URLSearchParams(location.search);
    if ((key === 'filter' && value === 'all') || (key === 'sort' && value === 'priority')) {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    navigate(
      {
        pathname: location.pathname,
        search: next.toString() ? `?${next.toString()}` : '',
      },
      { replace: true },
    );
  }, [location.pathname, location.search, navigate]);

  const handleInvoiceFilterChange = (filter: InvoiceFilterMode) => {
    setInvoiceFilter(filter);
    updateInvoiceParam('filter', filter);
  };

  const handleInvoiceSortChange = (sort: InvoiceSortMode) => {
    setColumnSort(null);
    setInvoiceSort(sort);
    updateInvoiceParam('sort', sort);
  };

  function clearCustomerFilter() {
    const next = new URLSearchParams(location.search);
    next.delete('customer');
    next.delete('profile');
    navigate({ pathname: location.pathname, search: next.toString() }, { replace: true });
  }

  function rowActions(document: CommercialDocument): TableAction[] {
    return [
      ...(canReadDocuments ? [{ icon: Eye, label: t('orders.rowActions.openDocument'), onSelect: () => setDocumentId(document.id) }] : []),
      ...(canReadOrders && document.source_order_id ? [{
        icon: ClipboardList, label: t('orders.rowActions.openOrder'), onSelect: () => navigate(`/orders/${document.source_order_id}`),
      }] : []),
      ...(canManagePayments && isOpenInvoice(document) ? [{
        icon: Check, label: invoiceText('confirmPayment'), onSelect: () => openPaymentDialog(document),
      }] : []),
    ];
  }

  const closePaymentDialog = () => {
    setPaymentTarget(null);
    clearPaymentParam();
  };

  const submitPayment = () => {
    if (!canManagePayments || !paymentTarget || !paymentDraft.amount) return;
    recordPayment.mutate({
      documentId: paymentTarget.id,
      input: {
        amount: normalizeDecimalInput(paymentDraft.amount),
        paid_at: paymentDraft.paid_at,
        method: paymentDraft.method,
        reference: paymentDraft.reference?.trim() || null,
        note: paymentDraft.note?.trim() || null,
      },
    });
  };

  const isInvoices = activeSection === 'invoices';
  const title = copy.page[activeSection].title;

  const pagination = useTablePagination(invoiceDocuments, JSON.stringify([activeSection, customerFilter, profileFilter, invoiceFilter, invoiceSort, columnSort]));
  return (
    <div className={orderPageClass}>
      <OrderHeader icon={ActiveIcon} title={title} description={copy.page[activeSection].subtitle} />

      {isInvoices && (
        <div className="flex flex-wrap items-center gap-2">
          <OrderStatus>{invoiceText('openCount', { count: invoiceSummary.openCount })} · {formatMoney(invoiceSummary.openAmount, locale, invoiceSummary.currency)}</OrderStatus>
          {invoiceSummary.overdueCount > 0 && <OrderStatus tone="danger">{invoiceText('overdueCount', { count: invoiceSummary.overdueCount })}</OrderStatus>}
          <WarehouseSegments>
            {invoiceFilterOptions.map(option => (
              <WarehouseSegment key={option.value} active={invoiceFilter === option.value} onClick={() => handleInvoiceFilterChange(option.value)}>
                {option.label} {invoiceFilterCounts[option.value]}
              </WarehouseSegment>
            ))}
          </WarehouseSegments>
          <WarehouseSegments>
            {invoiceSortOptions.map(option => (
              <WarehouseSegment key={option.value} active={!columnSort && invoiceSort === option.value} onClick={() => handleInvoiceSortChange(option.value)}>
                {option.label}
              </WarehouseSegment>
            ))}
          </WarehouseSegments>
        </div>
      )}

      {isInvoices && customerFilter !== null && (
        <OrderFilterChip label={`${t('orders.customers.customer')} #${customerFilter}`} onClear={clearCustomerFilter} />
      )}
      <OrderTable label={title} footer={<TablePagination {...pagination.footer} label={title} />}>
        <table className="w-full min-w-[620px] text-sm">
          <thead className={tableHeaderClass}>
            <tr className={tableHeaderRowClass}>
              {columns.map((column, index) => {
                const key = isInvoices ? invoiceColumns[index] : undefined;
                return key ? (
                  <OrderSortHeader key={key} label={column} direction={activeColumnSort?.key === key ? activeColumnSort.direction : undefined}
                    onSort={() => setColumnSort(nextOrderSort(activeColumnSort, key))} />
                ) : <th key={column} scope="col" className={tableHeaderCellClass}>{column}</th>;
              })}
              {isInvoices && <TableActionHeader />}
            </tr>
          </thead>
          <tbody>
            {isInvoices && invoiceDocuments.length > 0 ? pagination.rows.map(document => {
              const paid = document.payments.reduce((sum, payment) => sum + Number(payment.amount ?? 0), 0);
              const isPaymentTarget = document.id === paymentDocumentId;
              return (
                <OrderTableRow key={document.id} onOpen={canReadDocuments ? () => setDocumentId(document.id) : undefined}
                  className={isPaymentTarget ? 'ring-1 ring-inset ring-bambu-green/70' : ''}>
                  <td className={tableBodyCellClass}>
                    <div className={`${tableIdentifierClass} text-white`}>{documentNumber(document)}</div>
                    <div className="mt-0.5 text-xs tabular-nums">{formatMoney(document.total_amount, locale, document.currency)}</div>
                    {isPaymentTarget && <div className="mt-1 text-xs font-medium text-accent-foreground">{invoiceText('fromDashboard')}</div>}
                  </td>
                  <td className={tableBodyCellClass}>
                    <span className="block max-w-64 wrap-break-word">{document.customer_display_name || invoiceText('noCustomer')}</span>
                  </td>
                  <td className={tableBodyCellClass}>
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className="tabular-nums">{document.due_date ?? invoiceText('noDueDate')}</span>
                      <OrderStatus tone={isOverdueInvoice(document) ? 'danger' : paymentTone(document.payment_status)}>
                        <span className="tabular-nums">
                          {paymentStatusLabels[document.payment_status] ?? document.payment_status}
                          {invoiceText('openSeparator')}{formatMoney(document.open_amount, locale, document.currency)}
                          {invoiceText('paidSeparator')}{formatMoney(paid, locale, document.currency)}
                        </span>
                      </OrderStatus>
                    </div>
                  </td>
                  <TableRowActions subject={documentNumber(document)} actions={rowActions(document)} />
                </OrderTableRow>
              );
            }) : (
              <tr>
                <td colSpan={columns.length + (isInvoices ? 1 : 0)} className="px-4 py-10 text-center text-table-secondary">
                  {documentsQuery.isLoading && isInvoices
                    ? invoiceText('loading')
                    : isInvoices && allInvoiceDocuments.length > 0 ? invoiceText('emptyFilter') : copy.empty}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </OrderTable>

      {documentId !== null && <CommercialDocumentDialog key={documentId} id={documentId} onClose={() => setDocumentId(null)} />}
      {paymentTarget && (
        <Modal open onClose={closePaymentDialog} title={invoiceText('paymentHeading')} closeLabel={invoiceText('closeDialog')}
          description={`${documentNumber(paymentTarget)}${invoiceText('openSeparator')}${formatMoney(paymentTarget.open_amount, locale, paymentTarget.currency)}`}
          className="max-w-lg"
          footer={(
            <>
              <Button type="button" variant="secondary" onClick={closePaymentDialog}>{invoiceText('cancel')}</Button>
              <Button type="button" className="text-black!" onClick={submitPayment}
                disabled={!canManagePayments || !paymentDraft.amount || !paymentDraft.paid_at || recordPayment.isPending}>
                <Check aria-hidden="true" className="h-4 w-4" />{invoiceText('save')}
              </Button>
            </>
          )}>
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField label={invoiceText('amount')} value={paymentDraft.amount} inputMode="decimal"
              onValueChange={value => setPaymentDraft(current => ({ ...current, amount: value }))} />
            <LegacyDatePicker label={invoiceText('paidAt')} value={paymentDraft.paid_at}
              onValueChange={value => setPaymentDraft(current => ({ ...current, paid_at: value }))} />
            <Select label={invoiceText('method')} value={paymentDraft.method}
              onValueChange={value => setPaymentDraft(current => ({ ...current, method: value as PaymentMethod }))}
              options={Object.entries(methodLabels).map(([value, label]) => ({ value, label }))} />
            <TextField label={invoiceText('reference')} value={paymentDraft.reference ?? ''}
              onValueChange={value => setPaymentDraft(current => ({ ...current, reference: value }))} />
            <div className="sm:col-span-2">
              <TextArea label={invoiceText('note')} value={paymentDraft.note ?? ''}
                onValueChange={value => setPaymentDraft(current => ({ ...current, note: value }))} />
            </div>
          </div>
          {recordPayment.isError && <p role="alert" className="mt-4 text-sm text-red-700 dark:text-red-300">{invoiceText('paymentFailed')}</p>}
        </Modal>
      )}
    </div>
  );
}
