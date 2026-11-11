import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Film, Images, Loader2 } from 'lucide-react';
import { api, type PrintLogEntry } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { ConfirmOutcomeDialog } from './ConfirmOutcomeDialog';
import { PhotoGalleryModal } from './PhotoGalleryModal';
import { TimelapseViewer } from './TimelapseViewer';
import { useState } from 'react';
import { parseUTCDate } from '../utils/date';

interface PrintLogTableProps {
  archiveId: number;
}

function formatDuration(seconds: number | null): string {
  if (!seconds || seconds <= 0) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function formatDate(isoString: string | null): string {
  if (!isoString) return '—';
  const d = parseUTCDate(isoString);
  return d ? d.toLocaleString() : '—';
}

export function PrintLogTable({ archiveId }: PrintLogTableProps) {
  const { t } = useTranslation();
  const { canModify } = useAuth();
  const [inspectRunId, setInspectRunId] = useState<number | null>(null);
  const [media, setMedia] = useState<{ run: PrintLogEntry; kind: 'photos' | 'timelapse' } | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ['archive-runs', archiveId],
    queryFn: () => api.getArchiveRuns(archiveId),
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-4">
        <Loader2 className="w-5 h-5 text-bambu-gray animate-spin" />
      </div>
    );
  }

  const runs = data?.items || [];
  if (runs.length === 0) {
    return (
      <p className="text-sm text-bambu-gray italic py-2">
        {t('archives.runLog.empty')}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-bambu-gray border-b border-bambu-dark-tertiary">
            <th className="text-left py-1.5 pr-2 font-medium">{t('archives.runLog.col.date')}</th>
            <th className="text-left py-1.5 pr-2 font-medium">{t('archives.runLog.col.status')}</th>
            <th className="text-right py-1.5 pr-2 font-medium">{t('archives.runLog.col.plate')}</th>
            <th className="text-right py-1.5 pr-2 font-medium">{t('archives.runLog.col.duration')}</th>
            <th className="text-right py-1.5 pr-2 font-medium">{t('archives.runLog.col.filament')}</th>
            <th className="text-right py-1.5 font-medium">{t('archives.runLog.col.cost')}</th>
            <th className="text-right py-1.5 pl-2 font-medium">{t('productionQuality.title')}</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const statusClass =
              run.status === 'completed'
                ? 'text-bambu-green'
                : run.status === 'failed'
                  ? 'text-red-700 dark:text-red-400'
                  : 'text-bambu-gray';
            return (
              <tr
                key={run.id}
                className="border-b border-bambu-dark-tertiary/40 last:border-0"
              >
                <td className="py-1.5 pr-2 text-bambu-gray-light">
                  {formatDate(run.started_at || run.created_at)}
                </td>
                <td className={`py-1.5 pr-2 font-medium ${statusClass}`}>
                  {t(`archives.runLog.status.${run.status}`, { defaultValue: run.status })}
                  {(run.has_timelapse || Boolean(run.photos?.length)) && (
                    <span className="flex gap-2 pt-1">
                      {run.has_timelapse && <button type="button" className="text-bambu-green"
                        title={t('archives.card.viewTimelapse')} aria-label={t('archives.card.viewTimelapse')}
                        onClick={() => setMedia({ run, kind: 'timelapse' })}>
                        <Film className="h-4 w-4" />
                      </button>}
                      {Boolean(run.photos?.length) && <button type="button" className="text-bambu-green"
                        title={run.photos?.length === 1 ? t('archives.card.viewPhoto') : t('archives.card.viewPhotos', { count: run.photos?.length })}
                        aria-label={run.photos?.length === 1 ? t('archives.card.viewPhoto') : t('archives.card.viewPhotos', { count: run.photos?.length })}
                        onClick={() => setMedia({ run, kind: 'photos' })}>
                        <Images className="h-4 w-4" />
                      </button>}
                    </span>
                  )}
                  {run.failure_reason && (
                    <span className="block text-[10px] text-bambu-gray font-normal">
                      {t(`editArchive.failureReasons.${run.failure_reason}`, { defaultValue: run.failure_reason })}
                    </span>
                  )}
                </td>
                <td className="py-1.5 pr-2 text-right text-bambu-gray-light">{run.plate_id ?? '—'}</td>
                <td className="py-1.5 pr-2 text-right text-bambu-gray-light">
                  {formatDuration(run.duration_seconds)}
                  {run.estimate_seconds != null && <span className="block text-bambu-gray">
                    {t('archives.runLog.estimate', { value: formatDuration(run.estimate_seconds) })}
                  </span>}
                </td>
                <td className="py-1.5 pr-2 text-right text-bambu-gray-light">
                  {run.filament_used_grams != null
                    ? `${run.filament_used_grams.toFixed(1)} g`
                    : '—'}
                  {run.estimate_grams != null && <span className="block text-bambu-gray">
                    {t('archives.runLog.estimate', { value: `${run.estimate_grams.toFixed(1)} g` })}
                  </span>}
                </td>
                <td className="py-1.5 text-right text-bambu-gray-light">
                  {run.cost != null ? run.cost.toFixed(2) : '—'}
                </td>
                <td className="py-1.5 pl-2 text-right">
                  {run.status === 'completed' && <button type="button" className="text-bambu-green hover:underline" onClick={() => setInspectRunId(run.id)}
                    disabled={!canModify('archives', 'update', run.created_by_id)}>
                    {run.good_quantity != null ? t('productionQuality.partCounts', { good: run.good_quantity, reject: run.reject_quantity ?? 0 })
                      : t(run.confirm_requested ? 'productionQuality.pending' : 'productionQuality.inspect')}
                  </button>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {media?.kind === 'photos' && <PhotoGalleryModal
        archiveName={media.run.print_name ?? ''}
        photos={media.run.photos ?? []}
        getPhotoUrl={(filename) => api.getArchivePhotoUrl(archiveId, filename, media.run.id)}
        onClose={() => setMedia(null)}
      />}
      {media?.kind === 'timelapse' && <TimelapseViewer
        src={api.getArchiveTimelapse(archiveId, media.run.id)}
        title={media.run.print_name ?? t('archives.card.viewTimelapse')}
        downloadFilename={`timelapse-${media.run.id}.mp4`}
        onClose={() => setMedia(null)}
      />}
      {inspectRunId !== null && <ConfirmOutcomeDialog archiveId={archiveId} runId={inspectRunId} onClose={() => setInspectRunId(null)} />}
    </div>
  );
}
