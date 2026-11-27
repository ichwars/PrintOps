import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Button, Checkbox, Modal } from '../ui';
import { tableHeaderCellCompactClass } from '../ui/tableStyles';

export function WarehouseSelectionHeader({ checked, partial, disabled, onChange }: {
  checked: boolean; partial: boolean; disabled?: boolean; onChange: (checked: boolean) => void;
}) {
  const { t } = useTranslation();
  return (
    <th scope="col" className={`w-10 ${tableHeaderCellCompactClass}`}>
      <Checkbox ariaLabel={t('inventory.bulk.selectAllVisible')} checked={checked} indeterminate={partial} disabled={disabled} onCheckedChange={onChange} />
    </th>
  );
}

export function WarehouseSelectionCell({ checked, disabled, onChange }: {
  checked: boolean; disabled?: boolean; onChange: (checked: boolean) => void;
}) {
  const { t } = useTranslation();
  return (
    <td className="w-10 px-3 py-3" onClick={event => event.stopPropagation()}>
      <Checkbox ariaLabel={t('inventory.bulk.selectRow')} checked={checked} disabled={disabled} onCheckedChange={onChange} />
    </td>
  );
}

export function WarehouseRemaining({ physical, consumed, label }: {
  physical: string; consumed: string; label: string;
}) {
  const remaining = Math.max(0, Number(physical));
  const total = remaining + Math.max(0, Number(consumed));
  const percent = total > 0 ? remaining / total * 100 : 0;
  return (
    <div className="mx-auto flex min-w-32 max-w-44 items-center gap-2">
      <span aria-hidden="true" className="h-2 flex-1 overflow-hidden rounded-full bg-bambu-dark-tertiary">
        <span className={`block h-full rounded-full ${percent > 50 ? 'bg-bambu-green' : percent > 20 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${percent}%` }} />
      </span>
      <span className="min-w-12 whitespace-nowrap text-right text-xs tabular-nums text-table-secondary">{label}</span>
    </div>
  );
}

export function WarehouseStockCheckDialog({ ids, confirm, onClose, onSaved }: {
  ids: number[];
  confirm: (ids: number[]) => Promise<unknown>;
  onClose: () => void;
  onSaved: () => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const mutation = useMutation({
    mutationFn: () => confirm(ids),
    onSuccess: async () => {
      await onSaved();
      onClose();
    },
  });
  return (
    <Modal open title={t('common.confirmStockCheck')} closeLabel={t('common.close')} onClose={onClose} closeDisabled={mutation.isPending}>
      <p className="text-sm text-table-secondary">{t('common.stockCheckDescription')}</p>
      <p className="mt-2 text-sm text-table-secondary">{t('inventory.bulk.selectionCount', { count: ids.length })}</p>
      {mutation.isError && <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-300">{t('common.stockCheckFailed')}</p>}
      <div className="mt-5 flex flex-wrap justify-end gap-2">
        <Button variant="secondary" disabled={mutation.isPending} onClick={onClose}>{t('common.cancel')}</Button>
        <Button loading={mutation.isPending} onClick={() => mutation.mutate()}>{t('common.confirm')}</Button>
      </div>
    </Modal>
  );
}
