import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { calculationsApi, type CalculationDetail } from '../../api/calculations';
import { formatMoney } from '../../utils/calculationFormatting';
import { Button, Modal } from '../ui';

export function CalculationHistoryDialog({ item, locale, onClose }: {
  item: CalculationDetail;
  locale: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const text = (key: string) => t(`orders.runtimeCalculation.${key}`);
  const history = useQuery({
    queryKey: ['calculations', 'revisions', item.id],
    queryFn: () => calculationsApi.revisions(item.id),
  });
  return (
    <Modal open title={text('revisionHistory')} description={item.title} closeLabel={t('common.close')}
      onClose={onClose} className="max-w-xl"
      footer={<Button variant="secondary" onClick={onClose}>{t('common.close')}</Button>}>
      <div className="space-y-3 text-sm text-table-secondary">
        {history.isPending && <p role="status">{t('common.loading')}</p>}
        {history.isError && <div role="alert" className="flex items-center gap-2">
          <span>{t('common.errorLoading')}</span><Button variant="ghost" onClick={() => void history.refetch()}>{t('common.retry')}</Button>
        </div>}
        {history.data?.length === 0 && <p>{text('noApprovedRevisionYet')}</p>}
        {history.data?.map(revision => (
          <div key={revision.id} className="flex flex-wrap justify-between gap-2 rounded-md bg-bambu-dark p-3">
            <div><p className="font-medium text-white">{text('revisionLabel')} {revision.revision_number}</p>
              <time dateTime={revision.approved_at}>{new Date(revision.approved_at).toLocaleString(locale)}</time>
            </div>
            <div><p>{text('productionSelling')}</p>
              <p className="tabular-nums text-white">
                {formatMoney(revision.production_cost, locale, revision.currency)} / {formatMoney(revision.selling_price, locale, revision.currency)}
              </p>
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
}
