import { useTranslation } from 'react-i18next';
import type { Archive } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

export function ArchiveOutcomeBadge({ archive }: { archive: Archive }) {
  const { t } = useTranslation();
  const { canModify } = useAuth();
  if (archive.status !== 'completed' || !archive.outcome_run_id) return null;
  const label = archive.user_verdict
    ? t('productionQuality.partCounts', { good: archive.good_quantity ?? 0, reject: archive.reject_quantity ?? 0 })
    : t(archive.confirm_requested ? 'productionQuality.pending' : 'productionQuality.inspect');
  return <button type="button" disabled={!canModify('archives', 'update', archive.created_by_id)}
    className={`rounded px-2 py-1 text-xs ${archive.user_verdict ? 'bg-bambu-dark-tertiary text-white' : 'bg-amber-500/20 text-amber-700 dark:text-amber-300'}`}
    onClick={(event) => { event.stopPropagation(); window.dispatchEvent(new CustomEvent('printops:confirm-outcome', { detail: { archive_id: archive.id } })); }}>
    {label}
  </button>;
}
