import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { documentManagementApi } from '../../api/documentManagement';
import { useAuth } from '../../contexts/AuthContext';
import { formatMoney } from '../../utils/calculationFormatting';
import { downloadBlob } from '../../utils/clipboard';
import { Button, Modal } from '../ui';
import { DocumentAmounts } from './DocumentAmounts';

export function CommercialDocumentDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const { hasPermission } = useAuth();
  const canRead = hasPermission('commercial_documents:read');
  const canReadPayments = hasPermission('payments:read');
  const canExport = hasPermission('commercial_documents:export');
  const [downloading, setDownloading] = useState<number | null>(null);
  const [downloadFailed, setDownloadFailed] = useState(false);
  const query = useQuery({
    queryKey: ['commercial-documents', 'detail', id, canReadPayments],
    queryFn: () => documentManagementApi.getDocument(id),
    enabled: canRead,
  });
  if (!canRead) return null;
  const document = query.data;
  const artifacts = document?.artifacts.filter(item => item.validation_status === 'valid') ?? [];
  const type = document
    ? t(`settings.documents.documentTypes.${document.document_type}`)
    : t('orders.runtimeCalculation.document');
  const title = document?.number
    ? `${type} ${document.number}`
    : t('orders.runtimeDomain.nativeInvoices.documentNumber', { id });
  const isInvoice = document?.document_type.includes('invoice') || document?.document_type === 'self_billing';
  const positionsLabel = t(document?.document_type === 'quotation' ? 'orders.documentDetails.offerPositions'
    : isInvoice ? 'orders.documentDetails.invoicePositions' : 'orders.documentDetails.positions');
  const money = (value: string, currency = document?.currency ?? 'EUR') => formatMoney(value, i18n.language, currency);
  const labels = (key: string) => t(`orders.runtimeDomain.lexwareDocuments.${key}`);

  async function download(artifactId: number) {
    setDownloading(artifactId);
    setDownloadFailed(false);
    try {
      const file = await documentManagementApi.downloadDocumentArtifact(id, artifactId);
      downloadBlob(file.blob, file.filename);
    } catch {
      setDownloadFailed(true);
    } finally {
      setDownloading(null);
    }
  }

  return (
    <Modal open onClose={onClose} title={title} closeLabel={t('common.close')} className="max-w-2xl"
      footer={<Button variant="secondary" onClick={onClose}>{t('common.close')}</Button>}>
      <div className="space-y-5 text-sm text-table-secondary">
        {query.isPending && <p role="status">{t('common.loading')}</p>}
        {query.isError && <div role="alert" className="flex items-center gap-2">
          <span>{t('common.errorLoading')}</span><Button variant="ghost" onClick={() => void query.refetch()}>{t('common.retry')}</Button>
        </div>}
        {document && <>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div className="min-w-0"><dt>{t('orders.customers.customer')}</dt>
              <dd className="wrap-break-word font-semibold text-white">
                {document.customer_display_name || t('orders.runtimeDomain.nativeInvoices.noCustomer')}
              </dd>
            </div>
            <div><dt>{labels('date')}</dt><dd className="text-white">{document.issue_date ?? '—'}</dd></div>
            <div><dt>{labels('due')}</dt><dd className="text-white">{document.due_date ?? '—'}</dd></div>
          </dl>
          <DocumentAmounts lines={document.lines} currency={document.currency} locale={i18n.language}
            positionsLabel={positionsLabel}
            amounts={{ subtotal: document.subtotal_amount, tax: document.tax_amount, total: document.total_amount }} />
          {canReadPayments && document.payment_status !== 'not_applicable' && <section className="space-y-2">
            <h3 className="font-semibold text-white">{labels('payments')}</h3>
            <p>{labels('open')} <strong className="text-white">{money(document.open_amount)}</strong></p>
            {document.payments.length === 0 ? <p>{labels('noPayments')}</p> : (
              <ul className="divide-y divide-bambu-dark-tertiary">
                {document.payments.map(payment => <li key={payment.id} className="flex justify-between gap-4 py-2">
                  <span>{payment.paid_at} · {t(`orders.runtimeDomain.paymentMethods.${payment.method}`)}
                    {payment.reference && <span className="block wrap-break-word">{payment.reference}</span>}
                  </span>
                  <span className="whitespace-nowrap tabular-nums text-white">{money(payment.amount, payment.currency)}</span>
                </li>)}
              </ul>
            )}
          </section>}
          {canExport && <section className="space-y-2">
            <h3 className="font-semibold text-white">{t('common.download')}</h3>
            {artifacts.length === 0 ? <p>{labels('noFiles')}</p> : (
              <div className="flex flex-wrap gap-2">
                {artifacts.map(artifact => (
                  <Button key={artifact.id} variant="secondary" size="sm" className="max-[768px]:min-h-[44px]!"
                    disabled={downloading !== null} loading={downloading === artifact.id} onClick={() => void download(artifact.id)}>
                    <Download aria-hidden="true" className="h-4 w-4" />
                    {artifact.kind.replaceAll('_', ' ').toUpperCase()}
                  </Button>
                ))}
              </div>
            )}
            {downloadFailed && <p role="alert" className="text-red-700 dark:text-red-300">{labels('actionError')}</p>}
          </section>}
        </>}
      </div>
    </Modal>
  );
}
