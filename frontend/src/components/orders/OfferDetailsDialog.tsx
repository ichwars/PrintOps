import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { offersApi, type OfferStatus } from '../../api/offers';
import { offerCalculationTitle, snapshotPart } from '../../utils/offerSnapshot';
import { Button, Modal } from '../ui';
import { DocumentAmounts } from './DocumentAmounts';
import { OrderStatus } from './OrderLayout';

export function OfferDetailsDialog({ id, locale, statusLabel, onClose }: {
  id: number;
  locale: string;
  statusLabel: (status: OfferStatus) => string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const detail = useQuery({
    queryKey: ['offers', 'detail', id],
    queryFn: () => offersApi.get(id),
  });
  const offer = detail.data;
  const quotation = offer?.quotation;
  const calculation = offer ? snapshotPart(offer.snapshot, 'calculation') : {};
  const revision = offer ? snapshotPart(offer.snapshot, 'revision') : {};
  const rawCurrency = quotation?.currency ?? revision.currency ?? calculation.currency;
  const currency = typeof rawCurrency === 'string' ? rawCurrency : null;
  const snapshotPrice = revision.selling_price;
  const subtotal = typeof snapshotPrice === 'string' || typeof snapshotPrice === 'number' ? snapshotPrice : null;
  const customerId = quotation ? quotation.customer_id : offer?.customer_id;
  const customer = offer?.customer_display_name
    || (customerId ? `#${customerId}` : t('orders.runtimeCalculation.noCustomerOffersPage'));
  const tone = offer?.status === 'accepted' ? 'positive' : offer?.status === 'rejected' ? 'danger' : 'neutral';

  return (
    <Modal open title={offer?.number ?? t('orders.rowActions.openOffer')} closeLabel={t('common.close')} onClose={onClose}
      footer={<Button variant="secondary" onClick={onClose}>{t('common.close')}</Button>}>
      <div className="space-y-5 text-sm text-table-secondary">
        {detail.isPending && <p role="status">{t('common.loading')}</p>}
        {detail.isError && <div role="alert" className="flex items-center gap-2">
          <span>{t('common.errorLoading')}</span><Button variant="ghost" onClick={() => void detail.refetch()}>{t('common.retry')}</Button>
        </div>}
        {offer && <>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div className="min-w-0"><dt>{t('orders.customers.customer')}</dt><dd className="wrap-break-word font-semibold text-white">{customer}</dd></div>
            <div><dt>{t('common.status')}</dt><dd><OrderStatus tone={tone}>{statusLabel(offer.status)}</OrderStatus></dd></div>
            <div className="min-w-0"><dt>{t('printops.nav.calculation')}</dt><dd className="wrap-break-word text-white">{offerCalculationTitle(calculation)}</dd></div>
            <div><dt>{t('orders.runtimeCalculation.revisionLabel')}</dt><dd className="text-white">{String(revision.revision_number ?? '—')}</dd></div>
            <div><dt>{t('orders.runtimeCalculation.updatedOffersPage')}</dt><dd className="text-white">{new Date(offer.updated_at).toLocaleString(locale)}</dd></div>
          </dl>
          <DocumentAmounts lines={quotation?.lines ?? []} currency={currency} locale={locale}
            positionsLabel={t('orders.documentDetails.offerPositions')} amounts={quotation
              ? { subtotal: quotation.subtotal_amount, tax: quotation.tax_amount, total: quotation.total_amount }
              : { subtotal }} />
        </>}
      </div>
    </Modal>
  );
}
