import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Combine } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { archiveMergeApi } from '../api/client/archive-merge';
import { useAuth } from '../contexts/AuthContext';
import { Button } from './Button';
import { Checkbox, Modal } from './ui';

const MAX_GROUPS = 100;

export function ArchiveMergeButton() {
  const { t } = useTranslation();
  const { user, hasPermission } = useAuth();
  const [open, setOpen] = useState(false);
  const allowed = hasPermission('archives:read_all') && hasPermission('archives:update_all')
    && hasPermission('archives:delete_all');
  const count = useQuery({
    queryKey: ['archives', 'merge-count', user?.id],
    queryFn: archiveMergeApi.count,
    enabled: allowed,
  });

  if (!allowed || (!open && !count.data?.groups)) return null;
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <Combine className="h-4 w-4" />
        {t('archiveMerge.title')}
      </Button>
      {open && <ArchiveMergeDialog onClose={() => setOpen(false)} />}
    </>
  );
}

function ArchiveMergeDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const preview = useQuery({
    queryKey: ['archives', 'merge-preview', user?.id],
    queryFn: archiveMergeApi.preview,
    gcTime: 0,
  });
  const groups = preview.data?.groups ?? [];
  const selection = groups.filter(({ survivor, skipped }) => !skipped && selectedIds.includes(survivor.id));
  const merge = useMutation({
    mutationFn: () => archiveMergeApi.merge(selection.map(({ survivor, merged }) => ({
      survivor_id: survivor.id,
      merged_ids: merged.map(({ id }) => id),
    }))),
    onSuccess: () => {
      for (const key of ['archives', 'archive', 'archive-outcome', 'archiveStats', 'batches', 'queue', 'order-production', 'printLog', 'archive-runs', 'library']) {
        void queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
  const reason = (value: string) => t(`archiveMerge.reasons.${value}`, { defaultValue: t('archiveMerge.reasons.failed') });

  return (
    <Modal open title={t('archiveMerge.title')} closeLabel={t('common.close')} closeDisabled={merge.isPending}
      onClose={() => { if (!merge.isPending) onClose(); }}>
      <div className="space-y-3">
        {merge.data ? (
          <div role="status" className="space-y-2">
            <p>{t('archiveMerge.result', { count: merge.data.merged.length })}</p>
            {merge.data.skipped.length > 0 && (
              <ul className="list-inside list-disc text-sm text-yellow-400">
                {merge.data.skipped.map(({ survivor_id, reason: code }) => (
                  <li key={survivor_id}>#{survivor_id} · {reason(code)}</li>
                ))}
              </ul>
            )}
          </div>
        ) : preview.isPending ? <p role="status">{t('common.loading')}</p> : preview.isError ? (
          <div role="alert" className="flex items-center gap-2">
            <p>{t('archiveMerge.previewError')}</p>
            <Button variant="secondary" onClick={() => void preview.refetch()}>{t('common.retry')}</Button>
          </div>
        ) : groups.length === 0 ? <p>{t('archiveMerge.empty')}</p> : (
          <>
            <p className="text-sm text-bambu-gray">{t('archiveMerge.description')}</p>
            <ul className="space-y-2">
              {groups.map(({ survivor, merged, skipped }) => (
                <li key={survivor.id} className="rounded-lg border border-bambu-dark-tertiary p-3">
                  <Checkbox
                    label={t('archiveMerge.keep', { name: survivor.print_name || survivor.filename, id: survivor.id })}
                    checked={selectedIds.includes(survivor.id)}
                    disabled={Boolean(skipped) || merge.isPending
                      || (selection.length >= MAX_GROUPS && !selectedIds.includes(survivor.id))}
                    onCheckedChange={(checked) => setSelectedIds((ids) =>
                      checked ? [...ids, survivor.id] : ids.filter((id) => id !== survivor.id))}
                  />
                  <ul className="ml-6 text-sm text-bambu-gray">
                    {merged.map(({ id, print_name, filename }) => (
                      <li key={id}>{t('archiveMerge.move', { name: print_name || filename, id })}</li>
                    ))}
                  </ul>
                  {skipped && <p className="ml-6 text-sm text-yellow-400">{reason(skipped)}</p>}
                </li>
              ))}
            </ul>
            {selection.length >= MAX_GROUPS && <p>{t('archiveMerge.limit', { count: MAX_GROUPS })}</p>}
            {merge.isError && <p role="alert" className="text-sm text-red-400">{t('archiveMerge.submitError')}</p>}
          </>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={merge.isPending}>{t('common.close')}</Button>
          {!merge.data && groups.length > 0 && (
            <Button disabled={!selection.length || merge.isPending} onClick={() => merge.mutate()}>
              {merge.isPending ? t('common.loading') : t('archiveMerge.submit', { count: selection.length })}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
