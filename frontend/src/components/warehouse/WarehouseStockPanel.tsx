import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { api } from '../../api/client';
import { warehouseArticlesApi, type WarehouseArticle, type WarehouseMovementInput, type WarehouseMovementKind } from '../../api/client/warehouse-articles';
import { cryptoRandomUuid } from '../../utils/random';
import { Button, NumberField, Select, TextArea } from '../ui';
import { useWarehouseCopy, warehouseQuantity } from './warehouseGoodsCopy';

export function WarehouseStockPanel({ article, canBook }: { article: WarehouseArticle; canBook: boolean }) {
  const copy = useWarehouseCopy();
  const cache = useQueryClient();
  const [kind, setKind] = useState<WarehouseMovementKind>('receipt');
  const [locationId, setLocationId] = useState(0);
  const [targetId, setTargetId] = useState(0);
  const [quantity, setQuantity] = useState('');
  const [reason, setReason] = useState('');
  const [orderId, setOrderId] = useState('');
  const [reservationId, setReservationId] = useState(0);
  const [reversesId, setReversesId] = useState(0);
  const [offset, setOffset] = useState(0);
  const retryCommand = useRef<{ command: string; key: string } | null>(null);
  const locations = useQuery({ queryKey: ['warehouse', 'locations'], queryFn: api.getLocations });
  const ledger = useQuery({ queryKey: ['warehouse-articles', article.id, 'ledger', offset], queryFn: () => warehouseArticlesApi.ledger(article.id, offset) });
  const reservations = useQuery({ queryKey: ['warehouse-articles', article.id, 'reservations'], queryFn: () => warehouseArticlesApi.reservations(article.id) });
  const usesReservation = kind === 'release' || kind === 'reserved_issue';
  const selectedReservation = reservations.data?.find((entry) => entry.id === reservationId);
  const mutation = useMutation({
    mutationFn: () => {
      const payload: Omit<WarehouseMovementInput, 'idempotency_key'> = { entry_kind: kind, reason };
      if (kind === 'counter') payload.reverses_id = reversesId;
      else {
        payload.quantity = quantity;
        payload.location_id = usesReservation ? selectedReservation?.location_id : locationId;
        if (kind === 'transfer') payload.target_location_id = targetId;
        if (usesReservation) payload.reservation_id = reservationId;
        else if (orderId) payload.order_id = Number(orderId);
      }
      const command = JSON.stringify(payload);
      if (retryCommand.current?.command !== command) retryCommand.current = { command, key: cryptoRandomUuid() };
      return warehouseArticlesApi.addLedger(article.id, { ...payload, idempotency_key: retryCommand.current.key });
    },
    onSuccess: async () => {
      retryCommand.current = null;
      setQuantity(''); setReason(''); setReversesId(0); setKind('receipt');
      await cache.invalidateQueries({ queryKey: ['warehouse-articles'] });
    },
  });
  function changeKind(value: WarehouseMovementKind) { setKind(value); mutation.reset(); }
  const locationName = (id: number) => locations.data?.find((item) => item.id === id)?.name ?? `#${id}`;
  const valid = !!reason.trim() && (kind === 'counter' ? reversesId > 0 : !!quantity && (usesReservation ? !!selectedReservation : locationId > 0) && (kind !== 'transfer' || (targetId > 0 && targetId !== locationId)));
  return <div className="space-y-6 text-sm">
    {canBook && article.is_active && <form className="space-y-4 border-t border-bambu-dark-tertiary pt-4" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
      <h3 className="text-sm font-semibold text-white">{copy.booking}</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <Select<WarehouseMovementKind> label={copy.booking} value={kind} onValueChange={changeKind} options={(['opening', 'receipt', 'issue', 'transfer', 'correction', 'reservation', 'release', 'reserved_issue', ...(reversesId ? ['counter'] : [])] as WarehouseMovementKind[]).map((value) => ({ value, label: copy[value] }))} />
        {kind !== 'counter' && <NumberField label={`${copy.quantity} (${article.unit_code})`} step="any" required value={quantity} onValueChange={setQuantity} />}
        {kind !== 'counter' && !usesReservation && <Select label={copy.location} value={locationId} placeholder={copy.choose} onValueChange={setLocationId} options={(locations.data ?? []).map((item) => ({ value: item.id, label: item.name }))} />}
        {kind === 'transfer' && <Select label={copy.destination} value={targetId} placeholder={copy.choose} onValueChange={setTargetId} options={(locations.data ?? []).filter((item) => item.id !== locationId).map((item) => ({ value: item.id, label: item.name }))} />}
        {usesReservation && <Select label={copy.reservationSelect} value={reservationId} placeholder={copy.choose} onValueChange={setReservationId} options={(reservations.data ?? []).map((entry) => ({ value: entry.id, label: `#${entry.id} · ${locationName(entry.location_id)} · ${warehouseQuantity(entry.remaining)} ${article.unit_code}${entry.order_id ? ` · ${copy.order}: ${entry.order_id}` : ''}` }))} />}
        {kind !== 'counter' && !usesReservation && <NumberField label={copy.order} min="1" step="1" value={orderId} onValueChange={setOrderId} />}
      </div>
      {kind === 'correction' && <p className="text-sm text-bambu-gray">{copy.quantityNote}</p>}
      {kind === 'counter' && <p className="text-sm text-bambu-gray">#{reversesId} · {copy.counterNote}</p>}
      <TextArea label={copy.reason} className="min-h-20" required maxLength={2000} value={reason} onValueChange={setReason} />
      {locations.isLoading && <p role="status" className="text-bambu-gray">{copy.loading}</p>}
      {locations.isSuccess && !locations.data.length && <p role="alert" className="text-amber-300">{copy.noLocations}</p>}
      {(locations.isError || reservations.isError) && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-950/50 p-3 text-red-300">{copy.error}<Button type="button" size="sm" variant="secondary" onClick={() => { void locations.refetch(); void reservations.refetch(); }}>{copy.retry}</Button></div>}
      {mutation.isError && <p role="alert" className="rounded-lg bg-red-950/50 p-3 text-red-300">{mutation.error.message}</p>}
      <div className="flex justify-end">
        <Button type="submit" loading={mutation.isPending} disabled={!valid || locations.isError || (usesReservation && reservations.isError)}>{copy.book}</Button>
      </div>
    </form>}
    <section className="space-y-3 border-t border-bambu-dark-tertiary pt-4" aria-label={copy.history}>
      <h3 className="text-sm font-semibold text-white">{copy.history}</h3>
      {ledger.isLoading && <p role="status" className="text-bambu-gray">{copy.loading}</p>}
      {ledger.isError && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-950/50 p-3 text-red-300">{copy.error}<Button type="button" size="sm" variant="secondary" onClick={() => void ledger.refetch()}>{copy.retry}</Button></div>}
      {ledger.isSuccess && !ledger.data.length && <p className="text-bambu-gray">{copy.noHistory}</p>}
      {ledger.data?.map((entry) => <div key={entry.id} className="space-y-2 rounded-lg border border-bambu-dark-tertiary p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-medium text-white">#{entry.id} · {copy[entry.entry_kind]}</span>
          <span className="text-xs text-bambu-gray">{new Date(entry.created_at).toLocaleString()}</span>
        </div>
        <p className="tabular-nums text-bambu-gray-light">{locationName(entry.location_id)}{entry.target_location_id && ` → ${locationName(entry.target_location_id)}`} · {warehouseQuantity(entry.quantity)} {entry.unit_code}</p>
        <p className="text-xs tabular-nums text-bambu-gray">{copy.physical}: {warehouseQuantity(entry.physical_delta)} · {copy.reserved}: {warehouseQuantity(entry.reserved_delta)}</p>
        <p className="whitespace-pre-wrap text-bambu-gray-light">{entry.reason}</p>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-bambu-dark-tertiary/50 pt-2">
          <p className="text-xs text-bambu-gray">{copy.actor}: {entry.actor_id ?? copy.localActor}{entry.order_id && ` · ${copy.order}: ${entry.order_id}`}{entry.reverses_id && ` · ${copy.counter} #${entry.reverses_id}`}</p>
          {canBook && article.is_active && entry.entry_kind !== 'counter' && <Button type="button" size="sm" variant="secondary" onClick={() => { setReversesId(entry.id); setKind('counter'); setReason(''); mutation.reset(); }}>{copy.counter} #{entry.id}</Button>}
        </div>
      </div>)}
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>{copy.previous}</Button>
        <Button type="button" size="sm" variant="secondary" disabled={(ledger.data?.length ?? 0) < 50} onClick={() => setOffset(offset + 50)}>{copy.next}</Button>
      </div>
    </section>
  </div>;
}
