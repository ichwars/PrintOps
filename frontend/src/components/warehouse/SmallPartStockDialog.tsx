import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError } from '../../api/client';
import { smallPartsApi, type SmallPart } from '../../api/smallParts';
import { Modal } from '../ui/Modal';

interface SmallPartStockDialogProps {
  part: SmallPart;
  onClose: () => void;
}

export function SmallPartStockDialog({ part, onClose }: SmallPartStockDialogProps) {
  const queryClient = useQueryClient();
  const [entryKind, setEntryKind] = useState<'receipt' | 'correction'>('receipt');
  const [quantity, setQuantity] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const ledger = useQuery({
    queryKey: ['small-part', part.id, 'ledger'],
    queryFn: () => smallPartsApi.ledger(part.id),
  });
  const mutation = useMutation({
    mutationFn: () => smallPartsApi.addLedger(part.id, {
      entry_kind: entryKind,
      quantity,
      reason,
      idempotency_key: `${entryKind}-${part.id}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    }),
    onSuccess: async () => {
      setQuantity('');
      setReason('');
      setError('');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['small-parts'] }),
        queryClient.invalidateQueries({ queryKey: ['small-part', part.id, 'ledger'] }),
        queryClient.invalidateQueries({ queryKey: ['warehouse'] }),
      ]);
    },
    onError: (caught) => {
      if (caught instanceof ApiError && caught.code === 'insufficient_stock') {
        setError('Die Buchung würde den verfügbaren Bestand unterschreiten.');
      } else {
        setError(caught instanceof Error ? caught.message : 'Buchung fehlgeschlagen');
      }
    },
  });

  return (
    <Modal open onClose={onClose} title={`Bestand · ${part.sku}`} description={part.name} closeLabel="Schließen">
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          setError('');
          mutation.mutate();
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-sm text-gray-300">
            <span>Buchungsart</span>
            <select
              value={entryKind}
              onChange={(event) => setEntryKind(event.target.value as 'receipt' | 'correction')}
              className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-white"
            >
              <option value="receipt">Zugang</option>
              <option value="correction">Korrektur</option>
            </select>
          </label>
          <label className="space-y-1 text-sm text-gray-300">
            <span>Menge</span>
            <input
              aria-label="Menge"
              type="number"
              step="any"
              required
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-white"
            />
          </label>
        </div>
        <label className="block space-y-1 text-sm text-gray-300">
          <span>Grund</span>
          <textarea
            aria-label="Grund"
            required
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className="min-h-20 w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-white"
          />
        </label>
        {error && <p role="alert" className="rounded-lg bg-red-950/60 px-3 py-2 text-sm text-red-300">{error}</p>}
        <button
          type="submit"
          disabled={mutation.isPending || !quantity || !reason.trim()}
          className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Buchung speichern
        </button>
      </form>

      <div className="mt-6 border-t border-gray-700 pt-4">
        <h3 className="font-medium text-white">Buchungsjournal</h3>
        {ledger.isLoading && <p className="mt-3 text-sm text-gray-400">Wird geladen …</p>}
        {!ledger.isLoading && !ledger.data?.length && <p className="mt-3 text-sm text-gray-400">Noch keine Buchungen.</p>}
        <div className="mt-3 space-y-2">
          {ledger.data?.map((entry) => (
            <div key={entry.id} className="rounded-lg border border-gray-700 p-3 text-sm">
              <div className="flex justify-between gap-3 text-white">
                <span>{entry.entry_kind}</span>
                <span>{Number(entry.physical_delta).toLocaleString('de-DE')}</span>
              </div>
              <p className="mt-1 text-gray-400">{entry.reason}</p>
            </div>
          ))}
        </div>
      </div>
    </Modal>
  );
}
