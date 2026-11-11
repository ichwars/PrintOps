import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import { filamentProfileDefaultsApi, type FilamentProfileDefault } from '../api/client/filament-profile-defaults';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import { Button } from './Button';
import { Card, CardContent, CardHeader } from './Card';
import { ConfirmModal } from './ConfirmModal';
import { Checkbox, LegacySelect } from './ui';

export function FilamentProfileDefaults({ spoolman }: { spoolman: boolean }) {
  const { t } = useTranslation();
  const { user, hasPermission } = useAuth();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const canRead = hasPermission('inventory:read');
  const canWrite = hasPermission('inventory:update');
  const [selected, setSelected] = useState('');
  const [forAllColors, setForAllColors] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<FilamentProfileDefault>();
  const key = ['filament-profile-defaults', user?.id];
  const defaults = useQuery({ queryKey: key, queryFn: filamentProfileDefaultsApi.list, enabled: canRead });
  const spoolQuery = useQuery({
    queryKey: ['filament-profile-source-spools', spoolman, user?.id],
    queryFn: () => spoolman ? api.getSpoolmanInventorySpools() : api.getSpools(),
    enabled: canRead && canWrite,
  });
  const spool = spoolQuery.data?.find(row => String(row.id) === selected);
  const reportError = (error: Error) => showToast(error.message, 'error');
  const save = useMutation({
    mutationFn: async () => {
      if (!spool) throw new Error(t('profileDefaults.pickSpool'));
      const [presets, calibrations] = await Promise.all([
        spoolman ? api.getSpoolmanFilamentPresets(spool.id) : api.getSpoolFilamentPresets(spool.id),
        spoolman ? api.getSpoolmanKProfiles(spool.id) : api.getSpoolKProfiles(spool.id),
      ]);
      return filamentProfileDefaultsApi.save({
        material: spool.material,
        brand: spool.brand ?? '',
        subtype: spool.subtype ?? '',
        color_name: forAllColors || spool.color_name_is_synthesized ? '' : spool.color_name ?? '',
        slicer_filament: spool.slicer_filament ?? null,
        slicer_filament_name: spool.slicer_filament_name ?? null,
        presets,
        k_profiles: calibrations.map(({ printer_id, extruder, nozzle_diameter, nozzle_type, k_value, name, cali_idx, setting_id }) =>
          ({ printer_id, extruder, nozzle_diameter, nozzle_type, k_value, name, cali_idx, setting_id })),
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: key });
      showToast(t('profileDefaults.saved'), 'success');
    },
    onError: reportError,
  });
  const apply = useMutation({
    mutationFn: (id: number) => filamentProfileDefaultsApi.apply(id, spoolman),
    onSuccess: ({ applied, failed }) => {
      for (const queryKey of ['inventory-spools', 'spoolman-inventory-spools', 'filament-profile-source-spools']) {
        void queryClient.invalidateQueries({ queryKey: [queryKey] });
      }
      showToast(t('profileDefaults.applied', { applied, failed }), failed ? 'warning' : 'success');
    },
    onError: reportError,
  });
  const remove = useMutation({
    mutationFn: filamentProfileDefaultsApi.remove,
    onSuccess: () => {
      setDeleteTarget(undefined);
      void queryClient.invalidateQueries({ queryKey: key });
    },
    onError: reportError,
  });
  const busy = save.isPending || apply.isPending || remove.isPending;

  if (!canRead) return null;
  return (
    <Card id="card-filament-profile-defaults">
      <CardHeader><h3 className="font-semibold">{t('profileDefaults.title')}</h3></CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-bambu-gray">{t('profileDefaults.description')}</p>
        {canWrite && (
          <div className="space-y-2">
            <LegacySelect aria-label={t('profileDefaults.pickSpool')} value={selected}
              onChange={event => setSelected(event.target.value)} disabled={busy || spoolQuery.isPending}>
              <option value="">{t('profileDefaults.pickSpool')}</option>
              {spoolQuery.data?.map(row => (
                <option key={row.id} value={row.id}>
                  {[row.brand, row.material, row.subtype, row.color_name].filter(Boolean).join(' ')} (#{row.id})
                </option>
              ))}
            </LegacySelect>
            <Checkbox label={t('profileDefaults.allColors')} checked={forAllColors}
              onCheckedChange={setForAllColors} disabled={busy} />
            <Button onClick={() => save.mutate()} disabled={!spool || busy}>{t('profileDefaults.save')}</Button>
          </div>
        )}
        {defaults.isError && <p role="alert">{defaults.error.message}</p>}
        <ul className="space-y-2">
          {defaults.data?.map(row => (
            <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-bambu-dark-tertiary p-2">
              <span>{[row.brand, row.material, row.subtype, row.color_name || t('profileDefaults.allColors')].filter(Boolean).join(' · ')}</span>
              {canWrite && row.can_edit && (
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" onClick={() => apply.mutate(row.id)} disabled={busy}>
                    {t('profileDefaults.apply')}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setDeleteTarget(row)} disabled={busy}>
                    {t('common.delete')}
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      </CardContent>
      {deleteTarget && <ConfirmModal title={t('common.delete')} message={t('profileDefaults.deleteMessage')}
        onConfirm={() => remove.mutate(deleteTarget.id)} onCancel={() => setDeleteTarget(undefined)}
        isLoading={remove.isPending} variant="danger" />}
    </Card>
  );
}
