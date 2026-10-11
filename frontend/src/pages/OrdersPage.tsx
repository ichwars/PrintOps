import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Calculator, Check, ClipboardList, FileText, Receipt, X } from 'lucide-react';
import { Card, CardContent, CardHeader } from '../components/Card';
import { LegacyDatePicker, Select, TextArea, TextField } from '../components/ui';
import { tableHeaderCellClass, tableHeaderClass, tableHeaderRowClass } from '../components/ui/tableStyles';
import { useAuth } from '../contexts/AuthContext';
import {
  documentManagementApi,
  type CommercialDocument,
  type PaymentMethod,
  type RecordPaymentInput,
} from '../api/documentManagement';
import { formatMoney } from '../utils/calculationFormatting';

type OrderPageCopy = { "empty": string; "foundation": string; "page": { "overview": { "title": string; "subtitle": string; "columns": string[]; }; "calculation": { "title": string; "subtitle": string; "columns": string[]; }; "offers": { "title": string; "subtitle": string; "columns": string[]; }; "invoices": { "title": string; "subtitle": string; "columns": string[]; }; }; };

type OrderSectionId = 'overview' | 'calculation' | 'offers' | 'invoices';
type InvoiceSortMode = 'priority' | 'due' | 'amount' | 'created';
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

function statusClass(status: string) {
  if (status === 'paid') return 'text-bambu-green';
  if (status === 'partially_paid') return 'text-amber-300';
  if (status === 'overpaid') return 'text-cyan-300';
  return status === 'unpaid' ? 'text-bambu-gray' : 'text-red-300';
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
  const [paymentTarget, setPaymentTarget] = useState<CommercialDocument | null>(null);
  const initialInvoiceParams = new URLSearchParams(location.search);
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
    queryKey: ['commercial-documents', 'invoices'],
    queryFn: () => documentManagementApi.listDocuments(),
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
  const invoiceDocuments = useMemo(
    () => {
      const filtered = allInvoiceDocuments.filter((document) => {
        if (paymentDocumentId !== null && document.id === paymentDocumentId) return true;
        if (invoiceFilter === 'open') return isOpenInvoice(document);
        if (invoiceFilter === 'overdue') return isOverdueInvoice(document);
        if (invoiceFilter === 'paid') return !isOpenInvoice(document);
        return true;
      });

      return [...filtered].sort((left, right) => {
        if (paymentDocumentId !== null) {
          if (left.id === paymentDocumentId) return -1;
          if (right.id === paymentDocumentId) return 1;
        }

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
    [allInvoiceDocuments, invoiceFilter, invoiceSort, paymentDocumentId],
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
    setInvoiceSort(sort);
    updateInvoiceParam('sort', sort);
  };

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

  return (
    <div className="p-4 md:p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <ActiveIcon className="w-7 h-7 text-bambu-green" />
          {copy.page[activeSection].title}
        </h1>
        <p className="text-bambu-gray mt-1">{copy.page[activeSection].subtitle}</p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <ActiveIcon className="w-5 h-5 text-bambu-green" />
              <div>
                <h2 className="text-lg font-semibold text-white">
                  {copy.page[activeSection].title}
                </h2>
                <p className="text-sm text-bambu-gray">
                  {copy.page[activeSection].subtitle}
                </p>
              </div>
            </div>
            {activeSection === 'invoices' ? (
              <div className="flex flex-wrap items-center justify-end gap-2">
                <span className="rounded border border-bambu-dark-tertiary bg-bambu-dark px-2.5 py-1.5 text-xs font-medium text-bambu-gray">
                  {invoiceText('openCount', { count: invoiceSummary.openCount })} · {formatMoney(invoiceSummary.openAmount, locale, invoiceSummary.currency)}
                </span>
                {invoiceSummary.overdueCount > 0 ? (
                  <span className="rounded border border-red-500/40 bg-red-500/10 px-2.5 py-1.5 text-xs font-medium text-red-300">
                    {invoiceText('overdueCount', { count: invoiceSummary.overdueCount })}
                  </span>
                ) : null}
                <div className="flex overflow-hidden rounded border border-bambu-dark-tertiary">
                  {invoiceFilterOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      aria-pressed={invoiceFilter === option.value}
                      className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${invoiceFilter === option.value ? 'bg-bambu-green text-bambu-dark' : 'bg-bambu-dark text-bambu-gray hover:text-white'}`}
                      onClick={() => handleInvoiceFilterChange(option.value)}
                    >
                      {option.label} {invoiceFilterCounts[option.value]}
                    </button>
                  ))}
                </div>
                <div className="flex overflow-hidden rounded border border-bambu-dark-tertiary">
                  {invoiceSortOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      aria-pressed={invoiceSort === option.value}
                      className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${invoiceSort === option.value ? 'bg-bambu-green text-bambu-dark' : 'bg-bambu-dark text-bambu-gray hover:text-white'}`}
                      onClick={() => handleInvoiceSortChange(option.value)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <span className="text-xs px-2 py-1 rounded-full bg-bambu-dark-tertiary text-bambu-gray">
                {copy.foundation}
              </span>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-lg border border-bambu-dark-tertiary">
            <table className="w-full text-sm">
              <thead className={tableHeaderClass}>
                <tr className={tableHeaderRowClass}>
                  {columns.map((column) => (
                    <th key={column} className={tableHeaderCellClass}>
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {activeSection === 'invoices' && invoiceDocuments.length > 0 ? (
                  invoiceDocuments.map((document) => {
                    const paid = document.payments.reduce((sum, payment) => sum + Number(payment.amount ?? 0), 0);
                    const isPaymentTarget = document.id === paymentDocumentId;
                    return (
                      <tr
                        key={document.id}
                        className={`border-t border-bambu-dark-tertiary bg-bambu-dark-secondary ${isPaymentTarget ? 'ring-1 ring-inset ring-bambu-green/70' : ''}`}
                      >
                        <td className="px-4 py-3">
                          <div className="font-medium text-white">{documentNumber(document)}</div>
                          <div className="mt-1 text-xs text-bambu-gray">{formatMoney(document.total_amount, locale, document.currency)}</div>
                          {isPaymentTarget ? (
                            <div className="mt-2 text-xs font-medium text-bambu-green">{invoiceText('fromDashboard')}</div>
                          ) : null}
                        </td>
                        <td className="px-4 py-3 text-bambu-gray">
                          {document.customer_id ? `#${document.customer_id}` : invoiceText('noCustomer')}
                        </td>
                        <td className="px-4 py-3">
                          <div className="text-bambu-gray">{document.due_date ?? invoiceText('noDueDate')}</div>
                          <div className={`mt-1 text-xs font-medium ${statusClass(document.payment_status)}`}>
                            {paymentStatusLabels[document.payment_status] ?? document.payment_status}
                            {invoiceText('openSeparator')}
                            {formatMoney(document.open_amount, locale, document.currency)}
                            {invoiceText('paidSeparator')}
                            {formatMoney(paid, locale, document.currency)}
                          </div>
                          <button
                            type="button"
                            className="mt-3 inline-flex items-center gap-2 rounded bg-bambu-green px-3 py-2 text-xs font-semibold text-bambu-dark transition-colors hover:bg-bambu-green/90 disabled:cursor-not-allowed disabled:opacity-50"
                            disabled={!canManagePayments || document.open_amount === '0.00' || document.payment_status === 'paid'}
                            onClick={() => openPaymentDialog(document)}
                            title={!canManagePayments ? invoiceText('paymentPermission') : undefined}
                          >
                            <Check className="h-3.5 w-3.5" />
                            {invoiceText('confirmPayment')}
                          </button>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={columns.length} className="px-4 py-10 text-center text-bambu-gray">
                      {documentsQuery.isLoading && activeSection === 'invoices'
                        ? invoiceText('loading')
                        : activeSection === 'invoices' && allInvoiceDocuments.length > 0
                          ? invoiceText('emptyFilter')
                          : copy.empty}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {paymentTarget ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-lg rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary p-5 shadow-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white">{invoiceText('paymentHeading')}</h2>
                <p className="mt-1 text-sm text-bambu-gray">
                  {documentNumber(paymentTarget)}{invoiceText('openSeparator')}{formatMoney(paymentTarget.open_amount, locale, paymentTarget.currency)}
                </p>
              </div>
              <button
                type="button"
                className="rounded p-2 text-bambu-gray transition-colors hover:text-white"
                onClick={closePaymentDialog}
                aria-label={invoiceText('closeDialog')}
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <TextField
                label={invoiceText('amount')}
                value={paymentDraft.amount}
                inputMode="decimal"
                onValueChange={(value) => setPaymentDraft((current) => ({ ...current, amount: value }))}
              />
              <LegacyDatePicker
                label={invoiceText('paidAt')}
                value={paymentDraft.paid_at}
                onValueChange={(value) => setPaymentDraft((current) => ({ ...current, paid_at: value }))}
              />
              <Select
                label={invoiceText('method')}
                value={paymentDraft.method}
                onValueChange={(value) => setPaymentDraft((current) => ({ ...current, method: value as PaymentMethod }))}
                options={Object.entries(methodLabels).map(([value, label]) => ({
                  value,
                  label,
                }))}
              />
              <TextField
                label={invoiceText('reference')}
                value={paymentDraft.reference ?? ''}
                onValueChange={(value) => setPaymentDraft((current) => ({ ...current, reference: value }))}
              />
              <div className="sm:col-span-2">
                <TextArea
                  label={invoiceText('note')}
                  value={paymentDraft.note ?? ''}
                  onValueChange={(value) => setPaymentDraft((current) => ({ ...current, note: value }))}
                />
              </div>
            </div>

            {recordPayment.isError ? (
              <p className="mt-4 text-sm text-red-300">{invoiceText('paymentFailed')}</p>
            ) : null}

            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                className="rounded border border-bambu-dark-tertiary px-4 py-2 text-sm font-medium text-bambu-gray transition-colors hover:text-white"
                onClick={closePaymentDialog}
              >
                {invoiceText('cancel')}
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded bg-bambu-green px-4 py-2 text-sm font-semibold text-bambu-dark transition-colors hover:bg-bambu-green/90 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!canManagePayments || !paymentDraft.amount || !paymentDraft.paid_at || recordPayment.isPending}
                onClick={submitPayment}
              >
                <Check className="h-4 w-4" />
                {invoiceText('save')}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
