import type { TFunction } from 'i18next';
import type { useToast } from '../contexts/ToastContext';

type BulkResult = { not_found?: number[]; errors?: Array<{ id: number }> };

export const failedCount = (data: BulkResult): number =>
  (data.not_found?.length ?? 0) + (data.errors?.length ?? 0);

export function notifyResetResult(data: BulkResult & { reset: number }, t: TFunction, showToast: ReturnType<typeof useToast>['showToast']): boolean {
  const failed = failedCount(data);
  if (data.reset === 0 && failed > 0) {
    showToast(t('inventory.bulk.resetAllFailed', { count: failed }), 'error');
    return false;
  }
  if (failed > 0) {
    showToast(t('inventory.bulk.resetPartial', { ok: data.reset, failed }), 'warning');
  } else {
    showToast(t('inventory.allConsumedCountersReset', { count: data.reset }), 'success');
  }
  return true;
}
