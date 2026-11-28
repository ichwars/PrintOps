import { smallPartsText as text, useSmallPartsText, smallPartsLocale } from './smallPartsCopy';
import { skipToken, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../../api/client';
import { smallPartsApi, type SmallPart, type SmallPartLedgerInput } from '../../api/smallParts';
import { cryptoRandomUuid } from '../../utils/random';
import { Button, Modal, NumberField, Select, TextArea } from '../ui';
import { useWarehouseCopy } from './warehouseGoodsCopy';
import { warehouseUnit } from './warehouseTableValues';

type MovementKind = SmallPartLedgerInput['entry_kind'];
type PendingMovement = { input: SmallPartLedgerInput; uncertain?: boolean };

interface StockFormProps {
  part: SmallPart;
  onClose: () => void;
  readOnly?: boolean;
  quickKind?: Exclude<MovementKind, 'correction'>;
}

type SmallPartStockDialogProps = Omit<StockFormProps, 'part'> & (
  { part: SmallPart; partId?: never } | { part?: never; partId: number }
);

function formatQuantity(value: string, decimalPlaces: number): string {
  if (!value.trim()) return '';
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  if (decimalPlaces <= 0) return String(Math.round(parsed));
  return parsed.toFixed(decimalPlaces).replace(/\.?0+$/, '');
}

export function SmallPartStockDialog({ part, partId, ...formProps }: SmallPartStockDialogProps) {
  useSmallPartsText();
  const copy = useWarehouseCopy();
  const detail = useQuery({
    queryKey: ['small-part', partId],
    queryFn: partId === undefined ? skipToken : () => smallPartsApi.get(partId),
  });
  const material = part ?? detail.data;
  if (material) return <SmallPartStockForm key={material.id} part={material} {...formProps} />;
  return (
    <Modal open onClose={formProps.onClose} title={formProps.quickKind ? copy[formProps.quickKind] : text('stock')} closeLabel={text('close')}>
      {detail.isError ? (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 text-sm text-red-800 dark:text-red-300">
          {copy.error}<Button type="button" variant="secondary" onClick={() => void detail.refetch()}>{copy.retry}</Button>
        </div>
      ) : <p role="status" className="text-sm text-table-secondary">{text('loading')}</p>}
    </Modal>
  );
}

function SmallPartStockForm({ part, onClose, readOnly = false, quickKind }: StockFormProps) {
  const { t } = useTranslation();
  const copy = useWarehouseCopy();
  const queryClient = useQueryClient();
  const [commandKey] = useState(() => {
    const key = ['small-part', part.id, 'pending-ledger-command'] as const;
    queryClient.setQueryDefaults(key, { gcTime: Infinity });
    return key;
  });
  const [remembered, setRemembered] = useState(() => queryClient.getQueryData<PendingMovement>(commandKey));
  const [entryKind, setEntryKind] = useState<MovementKind>(remembered?.input.entry_kind ?? quickKind ?? 'receipt');
  const [quantity, setQuantity] = useState(remembered?.input.quantity ?? '');
  const [reason, setReason] = useState(remembered?.input.reason ?? part.default_consumption_reason);
  const busy = useRef(false);
  const quantityRef = useRef<HTMLInputElement>(null);
  const submitRef = useRef<HTMLButtonElement>(null);
  const quantityStep = part.unit.decimal_places > 0 ? String(1 / (10 ** part.unit.decimal_places)) : '1';
  const canBook = !readOnly && (!quickKind || part.is_active);
  const compact = quickKind === entryKind;
  const ledger = useQuery({
    queryKey: ['small-part', part.id, 'ledger'],
    queryFn: () => smallPartsApi.ledger(part.id),
    enabled: !compact,
  });
  const mutation = useMutation({
    mutationFn: (command: PendingMovement) => smallPartsApi.addLedger(part.id, command.input),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: commandKey, exact: true });
      setRemembered(undefined);
      setEntryKind(quickKind ?? entryKind);
      setQuantity('');
      setReason(part.default_consumption_reason);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['small-parts'] }),
        queryClient.invalidateQueries({ queryKey: ['small-part', part.id] }),
        queryClient.invalidateQueries({ queryKey: ['warehouse-articles'] }),
        queryClient.invalidateQueries({ queryKey: ['warehouse'] }),
      ]);
    },
    onError: (error, command) => {
      const rejected = error instanceof ApiError && error.status >= 400 && error.status < 500 &&
        error.status !== 408 && error.status !== 429;
      if (rejected && !command.uncertain) {
        queryClient.removeQueries({ queryKey: commandKey, exact: true });
        setRemembered(undefined);
      } else {
        const uncertain = { ...command, uncertain: true };
        queryClient.setQueryData(commandKey, uncertain);
        setRemembered(uncertain);
      }
    },
    onSettled: () => { busy.current = false; },
  });
  useEffect(() => {
    if (mutation.isSuccess || mutation.isError) {
      (remembered ? submitRef : quantityRef).current?.focus();
    }
  }, [mutation.isError, mutation.isSuccess, remembered]);

  const movementLabel = (kind: string) => {
    if (kind === 'issue') return copy.issue;
    if (kind === 'receipt' || kind === 'correction') return text(kind);
    return kind;
  };
  const amount = Number(quantity);
  const valid = Number.isFinite(amount) && (entryKind === 'correction' ? amount !== 0 : amount > 0) && Boolean(reason.trim());
  const unit = warehouseUnit(part.unit_code, t('common.unitShortPiece'), part.unit.label);
  const error = mutation.error;
  const errorMessage = error instanceof ApiError && error.code === 'insufficient_stock' ? text('stockShortfall')
    : error?.message || text('bookingFailed');
  function submit() {
    if (!canBook || busy.current || (!remembered && !valid)) return;
    const pending = remembered ?? {
      input: { entry_kind: entryKind, quantity, reason, idempotency_key: `${entryKind}-${part.id}-${cryptoRandomUuid()}` },
    };
    busy.current = true;
    queryClient.setQueryData(commandKey, pending);
    mutation.mutate(pending);
  }

  return (
    <Modal open
      onClose={() => { if (!busy.current) onClose(); }}
      closeOnBackdrop={!mutation.isPending}
      closeDisabled={mutation.isPending}
      title={quickKind ? `${copy[entryKind]} · ${part.sku}` : text('stockTitle', { sku: part.sku })}
      description={<span className="text-table-secondary">{part.name}</span>}
      closeLabel={text('close')}
      initialFocusRef={quickKind && canBook ? quantityRef : undefined}
    >
      {quickKind && !part.is_active && <p role="status" className="text-sm text-table-secondary">{text('inactive')}</p>}
      {canBook && <form
        className="space-y-4 [&_.text-red-400]:text-red-700 dark:[&_.text-red-400]:text-red-300"
        onSubmit={(event) => { event.preventDefault(); submit(); }}
      >
        <fieldset disabled={mutation.isPending || Boolean(remembered)} className="min-w-0 space-y-4">
          <div className={compact ? 'space-y-3' : 'grid gap-3 sm:grid-cols-2'}>
            {!compact && <Select<MovementKind> label={text('movementKind')} value={entryKind} onValueChange={setEntryKind}
              options={(['receipt', ...(part.is_active ? ['issue'] : []), 'correction'] as MovementKind[])
                .map(value => ({ value, label: movementLabel(value) }))} />}
            <NumberField ref={quantityRef} label={text('quantity')} aria-label={text('quantity')} suffix={<span className="text-table-secondary">{unit}</span>} step={quantityStep} required
              value={quantity} onValueChange={setQuantity} onBlur={compact ? undefined : () => setQuantity(formatQuantity(quantity, part.unit.decimal_places))} />
          </div>
          <TextArea label={text('reason')} aria-label={text('reason')} required maxLength={2000} value={reason} onValueChange={setReason}
            className={compact ? 'min-h-11' : 'min-h-20'} />
        </fieldset>
        {error && <p role="alert" className="rounded-lg bg-red-100 px-3 py-2 text-sm text-red-900 dark:bg-red-950/60 dark:text-red-300">{errorMessage}</p>}
        {remembered?.uncertain && <p role="status" className="text-sm text-amber-800 dark:text-amber-300">{copy.uncertainMovement}</p>}
        {mutation.isSuccess && <p role="status" className="text-sm text-accent-foreground">{t('orders.runtimeDomain.warehouseGoods.quickBookingSaved')}{mutation.data.receipt_number && ` · ${mutation.data.receipt_number}`}</p>}
        <Button ref={submitRef} type="submit" className={quickKind ? 'text-black!' : undefined} loading={mutation.isPending}
          disabled={!remembered && !valid}>{text('saveBooking')}</Button>
      </form>}

      {!compact && <div className="mt-6 border-t border-bambu-dark-tertiary pt-4">
        <h3 className="font-medium text-white">{text('ledger')}</h3>
        {ledger.isLoading && <p className="mt-3 text-sm text-bambu-gray">{text('loading')}</p>}
        {!ledger.isLoading && !ledger.data?.length && <p className="mt-3 text-sm text-bambu-gray">{text('noBookings')}</p>}
        <div className="mt-3 space-y-2">
          {ledger.data?.map((entry) => (
            <div key={entry.id} className="rounded-lg border border-bambu-dark-tertiary p-3 text-sm">
              <div className="flex justify-between gap-3 text-white">
                <span>{movementLabel(entry.entry_kind)}{entry.receipt_number && ` · ${entry.receipt_number}`}</span>
                <span>{Number(entry.physical_delta).toLocaleString(smallPartsLocale())}</span>
              </div>
              <p className="mt-1 text-bambu-gray">{entry.reason}</p>
            </div>
          ))}
        </div>
      </div>}
    </Modal>
  );
}
