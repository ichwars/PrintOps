import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api, type Archive } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import { Checkbox, Modal, NumberField, TextField } from './ui';
import { Button } from './Button';
import { PrintModal } from './PrintModal';

export function ConfirmOutcomeDialog({ archiveId, runId, onClose }: { archiveId: number; runId?: number; onClose: () => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const query = useQuery({
    queryKey: ['archive-outcome', user?.id ?? 'local', archiveId, runId ?? 'current'],
    queryFn: async () => {
      const archive = await api.getArchive(archiveId);
      if (runId === undefined || (runId === archive.outcome_run_id && archive.status === 'completed')) return { archive, historical: false };
      const history = await api.getArchiveRuns(archiveId);
      const run = history.items.find((entry) => entry.id === runId);
      if (!run) throw new Error('Print run not found');
      return { historical: true, archive: { ...archive, status: run.status, quantity: run.quantity ?? 1,
        outcome_run_id: run.id, outcome_expected_parts: run.quantity ?? 1, outcome_batch_id: null,
        good_quantity: run.good_quantity, reject_quantity: run.reject_quantity,
        user_verdict: run.user_verdict, user_verdict_at: run.user_verdict_at,
        user_verdict_source: run.user_verdict_source, failure_reason: run.failure_reason,
      } };
    }, staleTime: 0, gcTime: 0,
  });
  return query.data ? <OutcomeForm key={query.data.archive.outcome_run_id ?? 'no-run'} archive={query.data.archive} historical={query.data.historical} onClose={onClose} /> : (
    <Modal open title={t('productionQuality.title')} onClose={onClose}>
      <p role={query.isError ? 'alert' : undefined}>{t(query.isError ? 'productionQuality.loadFailed' : 'common.loading')}</p>
    </Modal>
  );
}

function OutcomeForm({ archive, historical, onClose }: { archive: Archive; historical: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const { canModify, hasPermission } = useAuth();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const total = archive.outcome_expected_parts ?? archive.quantity;
  const [good, setGood] = useState(String(archive.good_quantity ?? total));
  const [reject, setReject] = useState(String(archive.reject_quantity ?? 0));
  const [reason, setReason] = useState(archive.failure_reason ?? '');
  const [reproduce, setReproduce] = useState(false);
  const [showReprint, setShowReprint] = useState(false);
  const [replacementFailed, setReplacementFailed] = useState(false);
  const goodCount = Number(good), rejectCount = Number(reject);
  const valid = good !== '' && reject !== '' && Number.isInteger(goodCount) && Number.isInteger(rejectCount)
    && goodCount >= 0 && rejectCount >= 0 && goodCount + rejectCount === total;
  const canConfirm = archive.status === 'completed' && !!archive.outcome_run_id
    && canModify('archives', 'update', archive.created_by_id);
  const canReproduce = !historical && hasPermission('queue:create') && canModify('archives', 'reprint', archive.created_by_id);
  const mutation = useMutation({
    mutationFn: () => {
      const data = { run_id: archive.outcome_run_id!, good_quantity: goodCount, reject_quantity: rejectCount,
        ...(reason ? { failure_reason: reason } : {}) };
      return historical ? api.confirmRunOutcome(archive.id, archive.outcome_run_id!, data) : api.confirmOutcome(archive.id, data);
    },
    onSuccess: async () => {
      for (const key of ['archives', 'archive', 'archive-outcome', 'archiveStats', 'batches', 'queue', 'order-production', 'printLog', 'archive-runs']) {
        void queryClient.invalidateQueries({ queryKey: [key] });
      }
      showToast(t('productionQuality.saved'), 'success');
      if (reproduce && rejectCount > 0 && canReproduce) {
        if (archive.outcome_batch_id) {
          try {
            const batch = await api.getBatch(archive.outcome_batch_id);
            const wholeJob = batch.plates.length === 1 && batch.plates[0].plate_id == null;
            await api.dispatchBatch(archive.outcome_batch_id, {
              limit: 1, ...(wholeJob ? {} : { plate_id: archive.plate_id, only_plate: true }),
            });
            void queryClient.invalidateQueries({ queryKey: ['batches'] });
            void queryClient.invalidateQueries({ queryKey: ['queue'] });
          } catch {
            // The inspection is committed. Leave the dialog open and describe
            // the separate failed queue operation without retrying the verdict.
            setReplacementFailed(true);
            return;
          }
        } else {
          setShowReprint(true);
          return;
        }
      }
      onClose();
    },
    onError: (error: Error) => showToast(error.message, 'error'),
  });
  const name = archive.print_name || archive.filename;
  if (showReprint) return <PrintModal mode="create" archiveId={archive.id} archiveName={name} projectId={archive.project_id ?? undefined} onClose={onClose} />;
  return (
    <Modal open title={t('productionQuality.title')} description={name} onClose={onClose} closeDisabled={mutation.isPending}>
      <div className="space-y-4 text-white">
        <p className="text-sm text-bambu-gray">{t('productionQuality.intended', { count: total })}</p>
        {archive.user_verdict_at && <p className="text-xs text-bambu-gray">{t('productionQuality.recorded', {
          date: new Date(archive.user_verdict_at).toLocaleString(),
          source: t(archive.user_verdict_source === 'link' ? 'productionQuality.sourceLink' : 'productionQuality.sourceApp'),
        })}</p>}
        <div className="grid grid-cols-2 gap-3">
          <label>{t('productionQuality.good')}<NumberField aria-label={t('productionQuality.good')} min="0" step="1" value={good} onValueChange={setGood} disabled={!canConfirm || mutation.isPending} /></label>
          <label>{t('productionQuality.reject')}<NumberField aria-label={t('productionQuality.reject')} min="0" step="1" value={reject} onValueChange={setReject} disabled={!canConfirm || mutation.isPending} /></label>
        </div>
        {!valid && <p role="alert" className="text-sm text-red-300">{t('productionQuality.totalRequired', { count: total })}</p>}
        {canConfirm && <div className="flex gap-2">
          <Button variant="secondary" onClick={() => { setGood(String(total)); setReject('0'); }}>{t('productionQuality.allGood')}</Button>
          <Button variant="secondary" onClick={() => { setGood('0'); setReject(String(total)); }}>{t('productionQuality.allReject')}</Button>
        </div>}
        <TextField label={t('productionQuality.reason')} aria-label={t('productionQuality.reason')} value={reason} maxLength={100} onValueChange={setReason} disabled={!canConfirm || mutation.isPending} />
        {rejectCount > 0 && canReproduce && <Checkbox label={t('productionQuality.reproduce')} checked={reproduce} onCheckedChange={setReproduce} disabled={mutation.isPending} />}
        {archive.outcome_batch_id && <p className="text-xs text-bambu-gray">{t('productionQuality.runReplacement')}</p>}
        {replacementFailed && <p role="alert" className="text-sm text-red-300">{t('productionQuality.replacementFailed')}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={mutation.isPending}>{t('common.close')}</Button>
          <Button onClick={() => mutation.mutate()} disabled={!canConfirm || !valid || mutation.isPending || replacementFailed}>{t('productionQuality.save')}</Button>
        </div>
      </div>
    </Modal>
  );
}
