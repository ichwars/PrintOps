import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, PlayCircle } from 'lucide-react';
import { api, type Permission, type PrintQueueItem } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import { ConfirmModal } from './ConfirmModal';

const MODEL_GATE_WAIT_REASON = 'The last print failed on every free matching printer';

export function QueueFailureBanners({ queue }: { queue: PrintQueueItem[] | undefined }) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  // #1818: per-printer Resume-after-failure confirm modal. Tracks which
  // printer's gate the user is about to clear; null when no modal is open.
  const [resumeConfirm, setResumeConfirm] = useState<{
    printerId: number;
    printerName: string;
    skippedCount: number;
  } | null>(null);
  // Same for a model whose waiting jobs are held by failed last prints.
  const [resumeModelConfirm, setResumeModelConfirm] = useState<string | null>(null);
  const resumeAfterFailureMutation = useMutation({
    mutationFn: (printerId: number) => api.resumeQueueAfterFailure(printerId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['queue'] });
      setResumeConfirm(null);
      showToast(
        t('queue.toast.resumedAfterFailure', {
          restored: result.restored,
          acknowledged: result.acknowledged,
        }),
      );
    },
    onError: () => showToast(t('queue.toast.resumeAfterFailureFailed'), 'error'),
  });

  const resumeModelMutation = useMutation({
    mutationFn: (model: string) => api.resumeModelQueueAfterFailure(model),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['queue'] });
      setResumeModelConfirm(null);
      showToast(t('queue.toast.resumedModelAfterFailure', { count: result.acknowledged }));
    },
    onError: () => showToast(t('queue.toast.resumeAfterFailureFailed'), 'error'),
  });

  // #1818: printers whose queue is gated by a prior failure that's poisoning
  // downstream `require_previous_success` items. We surface a per-printer
  // Resume banner above the active queue so the user can clear the gate +
  // restore the skipped jobs in one click, without re-queuing each one.
  // Detection key: skipped + the scheduler's exact gate string. Other skip
  // reasons (filament deficit, etc.) get their own UX and stay untouched.
  const gateBlockedPrinters = useMemo<
    Array<{ printerId: number; printerName: string; skippedCount: number }>
  >(() => {
    const counts = new Map<number, { name: string; count: number }>();
    queue?.forEach((item) => {
      if (
        item.status === 'skipped' &&
        item.error_message === 'Previous print failed or was aborted' &&
        item.printer_id
      ) {
        const existing = counts.get(item.printer_id);
        if (existing) {
          existing.count += 1;
        } else {
          counts.set(item.printer_id, {
            name: item.printer_name || `Printer #${item.printer_id}`,
            count: 1,
          });
        }
      }
    });
    return Array.from(counts.entries())
      .map(([printerId, { name, count }]) => ({
        printerId,
        printerName: name,
        skippedCount: count,
      }))
      .sort((a, b) => a.printerName.localeCompare(b.printerName));
  }, [queue]);

  // Models whose "any printer" jobs wait because the last print failed on
  // every free printer of the model (the scheduler's MODEL_GATE_WAIT_REASON).
  const gateBlockedModels = useMemo<Array<{ model: string; waitingCount: number }>>(() => {
    const counts = new Map<string, number>();
    queue?.forEach((item) => {
      if (
        item.status === 'pending' &&
        !item.printer_id &&
        item.target_model &&
        item.waiting_reason === MODEL_GATE_WAIT_REASON
      ) {
        counts.set(item.target_model, (counts.get(item.target_model) ?? 0) + 1);
      }
    });
    return Array.from(counts.entries())
      .map(([model, waitingCount]) => ({ model, waitingCount }))
      .sort((a, b) => a.model.localeCompare(b.model));
  }, [queue]);

  return <>
      {/* #1818: Resume-after-failure banner. One row per printer whose queue
          is gated by a prior failed/aborted print. Visible regardless of
          tab/layout so the user can clear the gate without hunting for
          skipped items. Hidden entirely when no gates are active. */}
      {gateBlockedPrinters.length > 0 && hasPermission('queue:update_all' as Permission) && (
        <div className="mb-4 space-y-2">
          {gateBlockedPrinters.map(({ printerId, printerName, skippedCount }) => (
            <div
              key={printerId}
              className="flex items-center gap-3 px-4 py-3 bg-orange-50 dark:bg-orange-500/10 border border-orange-300 dark:border-orange-500/30 rounded-lg"
            >
              <AlertCircle className="w-5 h-5 text-orange-600 dark:text-orange-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-sm text-orange-800 dark:text-orange-200">
                  {t('queue.resumeAfterFailure.banner', {
                    printer: printerName,
                    count: skippedCount,
                  })}
                </div>
                <div className="text-xs text-orange-800/80 dark:text-orange-200/70 mt-0.5">
                  {t('queue.resumeAfterFailure.bannerHint')}
                </div>
              </div>
              <button
                onClick={() =>
                  setResumeConfirm({ printerId, printerName, skippedCount })
                }
                className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-100 dark:bg-orange-500/20 hover:bg-orange-200 dark:hover:bg-orange-500/30 text-orange-900 dark:text-orange-100 text-sm rounded-md border border-orange-300 dark:border-orange-500/40 transition-colors flex-shrink-0"
              >
                <PlayCircle className="w-4 h-4" />
                {t('queue.resumeAfterFailure.button')}
              </button>
            </div>
          ))}
        </div>
      )}

      {gateBlockedModels.length > 0 && hasPermission('queue:update_all' as Permission) && (
        <div className="mb-4 space-y-2">
          {gateBlockedModels.map(({ model, waitingCount }) => (
            <div
              key={model}
              className="flex items-center gap-3 px-4 py-3 bg-orange-50 dark:bg-orange-500/10 border border-orange-300 dark:border-orange-500/30 rounded-lg"
            >
              <AlertCircle className="w-5 h-5 text-orange-600 dark:text-orange-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-sm text-orange-800 dark:text-orange-200">
                  {t('queue.resumeModelAfterFailure.banner', { model, count: waitingCount })}
                </div>
                <div className="text-xs text-orange-800/80 dark:text-orange-200/70 mt-0.5">
                  {t('queue.resumeModelAfterFailure.bannerHint', { model })}
                </div>
              </div>
              <button
                onClick={() => setResumeModelConfirm(model)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-100 dark:bg-orange-500/20 hover:bg-orange-200 dark:hover:bg-orange-500/30 text-orange-900 dark:text-orange-100 text-sm rounded-md border border-orange-300 dark:border-orange-500/40 transition-colors flex-shrink-0"
              >
                <PlayCircle className="w-4 h-4" />
                {t('queue.resumeAfterFailure.button')}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* #1818: Resume-after-failure confirm */}
      {resumeConfirm && (
        <ConfirmModal
          title={t('queue.resumeAfterFailure.confirmTitle')}
          message={t('queue.resumeAfterFailure.confirmMessage', {
            printer: resumeConfirm.printerName,
            count: resumeConfirm.skippedCount,
          })}
          confirmText={t('queue.resumeAfterFailure.button')}
          variant="warning"
          onConfirm={() => resumeAfterFailureMutation.mutate(resumeConfirm.printerId)}
          onCancel={() => setResumeConfirm(null)}
        />
      )}

      {resumeModelConfirm && (
        <ConfirmModal
          title={t('queue.resumeAfterFailure.confirmTitle')}
          message={t('queue.resumeModelAfterFailure.confirmMessage', { model: resumeModelConfirm })}
          confirmText={t('queue.resumeAfterFailure.button')}
          variant="warning"
          onConfirm={() => resumeModelMutation.mutate(resumeModelConfirm)}
          onCancel={() => setResumeModelConfirm(null)}
        />
      )}

  </>;
}
