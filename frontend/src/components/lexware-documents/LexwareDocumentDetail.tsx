import { TablePagination } from '../../components/ui/TablePagination';
import { useTablePagination } from '../../hooks/useTablePagination';
import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, X } from 'lucide-react';
import { ApiError } from '../../api/client/core';
import { lexwareDocumentsApi, type LexwareDocument } from '../../api/client/lexware-documents';
import { documentManagementApi } from '../../api/documentManagement';
import { Button } from '../Button';
import { Select } from '../ui';
import { dashboardStyles } from '../dashboardStyles';
import { OrderTable, orderPanelClass } from '../orders/OrderLayout';
import { tableBodyCellClass, tableBodyRowClass, tableHeaderCellClass, tableHeaderClass, tableHeaderRowClass } from '../ui/tableStyles';
import { displayMoney, documentCodeLabel, useLexwareDocumentLabels } from './labels';

export function LexwareDocumentDetail({ document, canFinance, canLink, onClose }: { document: LexwareDocument; canFinance: boolean; canLink: boolean; onClose: () => void }) {
  const labels = useLexwareDocumentLabels();
  const client = useQueryClient();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const heading = headingRef.current;
    if (!heading) return;
    const active = heading.ownerDocument.activeElement;
    if (active instanceof HTMLElement && active !== heading) previousFocus.current = active;
    heading.focus();
  }, []);
  function closeDetails() {
    onClose();
    previousFocus.current?.focus();
  }
  const [localId, setLocalId] = useState('');
  const [actionError, setActionError] = useState('');
  const [downloading, setDownloading] = useState<string | null>(null);
  const local = useQuery({
    queryKey: ['lexware-local-documents', document.business_profile_id],
    queryFn: () => documentManagementApi.listDocuments({ businessProfileId: document.business_profile_id }),
    enabled: canLink,
  });
  const linking = useMutation({
    mutationFn: (id: number | null) => lexwareDocumentsApi.link(document.id, id, document.version),
    onSuccess: async () => {
      setActionError('');
      await client.invalidateQueries({ queryKey: ['lexware-documents'] });
      await client.invalidateQueries({ queryKey: ['lexware-finance'] });
    },
    onError: (error) => setActionError(error instanceof ApiError && error.status === 409 ? labels.conflict : labels.actionError),
  });
  async function download(fileId: string) {
    setDownloading(fileId);
    setActionError('');
    try {
      const file = await lexwareDocumentsApi.download(document.id, fileId);
      const url = URL.createObjectURL(file.blob);
      const anchor = window.document.createElement('a');
      anchor.href = url;
      anchor.download = file.filename;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      await client.invalidateQueries({ queryKey: ['lexware-documents'] });
    } catch { setActionError(labels.actionError); }
    finally { setDownloading(null); }
  }
  const finance = canFinance ? document.finance : undefined;
  const pagination = useTablePagination(finance?.payment_items ?? [], String(document.id), 15);
  return <section className={`${orderPanelClass} space-y-5`} aria-label={labels.details}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 ref={headingRef} tabIndex={-1} className={`${dashboardStyles.cardTitle} min-w-0 wrap-break-word`}>{document.voucher_number || document.external_id}</h2>
      <Button variant="ghost" onClick={closeDetails}><X size={16} />{labels.close}</Button>
    </div>
    <p>{document.contact_name} · {document.company_name} · Lexware</p>
    <p className="text-sm text-table-secondary">{labels.updated}: {new Date(document.updated_at).toLocaleString()} · {documentCodeLabel(labels, 'status', document.voucher_status)}</p>
    {!document.supported && <p role="status" className="text-amber-800 dark:text-amber-300">{labels.unsupported}</p>}
    {!document.in_latest_sync && <p role="status" className="text-amber-800 dark:text-amber-300">{labels.missing}</p>}
    {(!document.connection_enabled || ['error', 'failed'].includes(document.sync_status)) && <p role="status" className="text-amber-800 dark:text-amber-300">{labels.stale}</p>}
    {actionError && <p role="alert" className="text-red-700 dark:text-red-400">{actionError}</p>}
    {finance ? <>
      <dl className="grid gap-4 sm:grid-cols-3">
        <div><dt className="text-table-secondary">{labels.total}</dt><dd>{displayMoney(finance.total_amount, finance.currency, labels.unknown)}</dd></div>
        <div><dt className="text-table-secondary">{labels.open}</dt><dd>{finance.payment_state === 'not_applicable' ? labels.notApplicable : displayMoney(finance.open_amount, finance.currency, labels.unknown)}</dd></div>
        <div><dt className="text-table-secondary">{labels.due}</dt><dd>{document.due_date || '—'} {finance.overdue && <span className="text-amber-800 dark:text-amber-300">{labels.overdue}</span>}</dd></div>
      </dl>
      <p>{finance.payment_state === 'unknown' ? labels.unknown : finance.payment_status === 'balanced' ? labels.balanced : finance.payment_state === 'not_applicable' ? labels.notApplicable : documentCodeLabel(labels, 'status', finance.payment_status ?? '')}</p>
      <div><h3 className="font-medium mb-2">{labels.payments}</h3>
        {finance.payment_items.length === 0 ? <p className="text-table-secondary">{labels.noPayments}</p> : <OrderTable label={labels.payments} footer={<TablePagination {...pagination.footer} />}><table className="w-full min-w-[320px] text-sm">
          <thead className={tableHeaderClass}><tr className={tableHeaderRowClass}><th scope="col" className={tableHeaderCellClass}>{labels.paymentKind}</th><th scope="col" className={`${tableHeaderCellClass} text-center`}>{labels.date}</th><th scope="col" className={`${tableHeaderCellClass} text-center`}>{labels.amount}</th></tr></thead>
          <tbody>{pagination.rows.map((item, index) => <tr key={`${item.item_type}-${index}`} className={tableBodyRowClass}>
            <td className={tableBodyCellClass}>{labels[item.category as keyof typeof labels] || item.item_type}</td><td className={`${tableBodyCellClass} text-center`}>{item.posting_date || '—'}</td><td className={`${tableBodyCellClass} whitespace-nowrap text-center tabular-nums`}>{displayMoney(item.amount, item.currency, labels.unknown)}</td>
          </tr>)}</tbody>
        </table></OrderTable>}
      </div>
      <div><h3 className="font-medium mb-2">{labels.originals}</h3>
        {!document.files?.length && <p className="text-table-secondary">{labels.noFiles}</p>}
        {document.files?.map(file => <div key={file.file_id} className="mb-3 rounded-lg bg-bambu-dark p-3 space-y-2">
          <p className="break-all text-sm">{file.filename || file.file_id} · {file.cached ? labels.cached : labels.uncached}</p>
          {file.sha256 && <p className="break-all text-xs text-table-secondary">SHA-256: {file.sha256}</p>}
          <Button variant="secondary" size="sm" loading={downloading === file.file_id} disabled={!!downloading || (!file.cached && !document.connection_enabled)} onClick={() => void download(file.file_id)}><Download size={14} />{labels.download}</Button>
        </div>)}
      </div>
    </> : <p className="text-table-secondary">{labels.financeDenied}</p>}
    {document.local_document_id && <p>{labels.localId}: #{document.local_document_id}</p>}
    {canLink && <div className="border-t border-bambu-dark-tertiary pt-4 space-y-3">
      <h3 className="font-medium">{labels.linkTitle}</h3><p className="text-sm text-table-secondary">{labels.linkNote}</p>
      {local.isLoading && <p>{labels.localLoading}</p>}
      {local.isError && <p role="alert">{labels.error} <Button variant="ghost" onClick={() => void local.refetch()}>{labels.retry}</Button></p>}
      {local.data?.length === 0 && <p>{labels.localEmpty}</p>}
      <Select
        label={labels.selectLocal}
        value={localId}
        options={[
          { value: '', label: '—' },
          ...(local.data ?? []).map(item => ({
            value: String(item.id),
            label: `${item.number || `#${item.id}`} · ${item.document_type} · ${item.total_amount} ${item.currency} · ${item.technical_status}`,
          })),
        ]}
        onValueChange={setLocalId}
      />
      <div className="flex flex-wrap gap-2"><Button disabled={!localId} loading={linking.isPending} onClick={() => linking.mutate(Number(localId))}>{labels.link}</Button>
        {document.local_document_id && <Button variant="secondary" loading={linking.isPending} onClick={() => linking.mutate(null)}>{labels.unlink}</Button>}
      </div>
    </div>}
  </section>;
}
