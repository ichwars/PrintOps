import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api, ApiError } from '../../api/client';
import { dryingSchedulesApi, type DryingScheduleWrite } from '../../api/client/drying-schedules';
import { useAuth } from '../../contexts/AuthContext';
import { registerSettingsSearch } from '../../lib/settingsSearch';
import { Button, Checkbox, NumberField, Select, TextField, TimeField } from '../ui';

registerSettingsSearch({ labelKey: 'scheduledDrying.title', tab: 'warehouse-material', warehouseMaterialSubTab: 'filament',
  keywords: 'drying schedule ams timezone trocknung zeitplan', anchor: 'scheduled-drying' });

function defaultPlan(): DryingScheduleWrite {
  return { ams_id: 0, local_time: '06:30', timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    filament: 'PLA', temperature: 45, duration_hours: 4, rotate_tray: false, enabled: false };
}

export function ScheduledDryingSettings() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canRead = hasPermission('printers:read');
  const canControl = hasPermission('printers:control');
  const queryClient = useQueryClient();
  const [printerId, setPrinterId] = useState('');
  const [draft, setDraft] = useState(defaultPlan);
  const [editingId, setEditingId] = useState<number>();
  const [error, setError] = useState<string | null>(null);
  const printers = useQuery({ queryKey: ['printers'], queryFn: api.getPrinters, enabled: canRead });
  const queryKey = ['drying-schedules', printerId];
  const plans = useQuery({ queryKey, queryFn: () => dryingSchedulesApi.list(Number(printerId)),
    enabled: canRead && !!printerId, refetchInterval: 15_000 });
  const reasonText = (reason: string | null | undefined) => t(`scheduledDrying.reasons.${reason || 'unknown'}`,
    { defaultValue: t('scheduledDrying.reasons.unknown') });
  const mutation = useMutation({
    mutationFn: (action: () => Promise<unknown>) => action(),
    onSuccess: () => { setError(null); void queryClient.invalidateQueries({ queryKey }); },
    onError: (cause) => setError(cause instanceof ApiError && cause.code ? reasonText(cause.code) : t('scheduledDrying.saveFailed')),
  });
  const update = <K extends keyof DryingScheduleWrite>(key: K, value: DryingScheduleWrite[K]) => {
    setDraft(previous => ({ ...previous, [key]: value }));
  };
  const capability = plans.data?.capabilities.find(item => item.ams_id === draft.ams_id);
  const blockReason = capability?.reason ?? (capability ? null : 'capability_unknown');
  const canEnable = blockReason === null && !!capability?.max_temperature && draft.temperature <= capability.max_temperature;
  const busy = mutation.isPending;
  if (!canRead) return null;
  return (
    <section id="scheduled-drying" aria-labelledby="scheduled-drying-title" className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4 space-y-4">
      <h3 id="scheduled-drying-title" className="font-semibold">{t('scheduledDrying.title')}</h3>
      <p className="text-sm text-bambu-gray">{t('scheduledDrying.description')}</p>
      <p className="text-sm text-bambu-gray">{t('scheduledDrying.timingHelp')}</p>
      <Select label={t('scheduledDrying.printer')} value={printerId} options={(printers.data || []).map(printer => ({ value: String(printer.id), label: printer.name }))}
        onValueChange={value => { setPrinterId(value); setEditingId(undefined); setDraft(defaultPlan()); setError(null); }} />
      {(error || plans.isError || printers.isError) && <p role="alert" className="text-sm text-red-400">{error || t('scheduledDrying.saveFailed')}</p>}
      {printerId && <>
        <form className="space-y-3" onSubmit={event => {
          event.preventDefault();
          if (canControl) mutation.mutate(() => dryingSchedulesApi.save(Number(printerId), draft, editingId));
        }}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <NumberField label={t('scheduledDrying.ams')} min={0} max={135} step={1} required value={draft.ams_id}
              disabled={!canControl || busy} onValueChange={value => update('ams_id', Number(value))} />
            <TimeField label={t('scheduledDrying.localTime')} required value={draft.local_time} disabled={!canControl || busy}
              onChange={event => update('local_time', event.target.value)} />
            <TextField label={t('scheduledDrying.timezone')} required maxLength={100} value={draft.timezone} disabled={!canControl || busy}
              onChange={event => update('timezone', event.target.value)} />
            <TextField label={t('scheduledDrying.filament')} required maxLength={100} value={draft.filament} disabled={!canControl || busy}
              onChange={event => update('filament', event.target.value)} />
            <NumberField label={t('scheduledDrying.temperature')} suffix="°C" required min={45} max={capability?.max_temperature || 85}
              value={draft.temperature} disabled={!canControl || busy} onValueChange={value => update('temperature', Number(value))} />
            <NumberField label={t('scheduledDrying.hours')} suffix="h" required min={1} max={24} value={draft.duration_hours}
              disabled={!canControl || busy} onValueChange={value => update('duration_hours', Number(value))} />
          </div>
          <Checkbox label={t('scheduledDrying.rotate')} checked={draft.rotate_tray} disabled={!canControl || busy}
            onCheckedChange={value => update('rotate_tray', value)} />
          <Checkbox label={t('scheduledDrying.enabled')} checked={draft.enabled} disabled={!canControl || busy || !draft.enabled && !canEnable}
            onCheckedChange={value => update('enabled', value)} />
          {blockReason && <p role="status" className="text-sm text-amber-300">{reasonText(blockReason)}</p>}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={!canControl || busy || plans.isLoading}>{t('scheduledDrying.save')}</Button>
            {editingId !== undefined && <Button variant="secondary" onClick={() => { setEditingId(undefined); setDraft(defaultPlan()); }}>
              {t('scheduledDrying.newPlan')}
            </Button>}
          </div>
        </form>
        <p className="text-xs text-bambu-gray">{t('scheduledDrying.stopHelp')}</p>
        <ul className="space-y-3" aria-label={t('scheduledDrying.plans')}>
          {plans.data?.schedules.map(plan => {
            const target = plans.data.capabilities.find(item => item.ams_id === plan.ams_id);
            const enableBlocked = !target || !!target.reason || !target.max_temperature || plan.temperature > target.max_temperature;
            const { id } = plan;
            const config: DryingScheduleWrite = { ams_id: plan.ams_id, local_time: plan.local_time, timezone: plan.timezone,
              filament: plan.filament, temperature: plan.temperature, duration_hours: plan.duration_hours,
              rotate_tray: plan.rotate_tray, enabled: plan.enabled };
            return <li key={id} className="rounded-lg border border-bambu-dark-tertiary p-3 space-y-2">
              <p className="text-sm break-words">{plan.local_time} · {plan.timezone} · AMS {plan.ams_id} · {plan.filament} · {plan.temperature} °C · {plan.duration_hours} h</p>
              <p className="text-sm">{t(plan.enabled ? 'scheduledDrying.enabled' : 'scheduledDrying.disabled')}</p>
              {target?.reason && <p className="text-sm text-amber-300">{reasonText(target.reason)}</p>}
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" disabled={!canControl || busy} onClick={() => { setDraft(config); setEditingId(id); }}>{t('scheduledDrying.edit')}</Button>
                <Button variant="secondary" disabled={!canControl || busy || !plan.enabled && enableBlocked}
                  onClick={() => mutation.mutate(() => dryingSchedulesApi.save(Number(printerId), { ...config, enabled: !plan.enabled }, id))}>
                  {t(plan.enabled ? 'scheduledDrying.disable' : 'scheduledDrying.enable')}
                </Button>
                <Button variant="secondary" disabled={!canControl || busy}
                  onClick={() => mutation.mutate(() => dryingSchedulesApi.remove(Number(printerId), id))}>{t('scheduledDrying.delete')}</Button>
              </div>
            </li>;
          })}
        </ul>
        <h4 className="font-medium">{t('scheduledDrying.history')}</h4>
        <ul className="space-y-2">
          {plans.data?.runs.map(run => <li key={run.id} className="text-sm space-y-1">
            <p>{run.occurrence_day} · AMS {run.ams_id} · {t(`scheduledDrying.status.${run.status}`, { defaultValue: t('scheduledDrying.status.uncertain') })}</p>
            {run.reason && <p className="text-bambu-gray">{reasonText(run.reason)}</p>}
            {run.status === 'uncertain' && run.active_printer_id !== null && <Button variant="secondary" disabled={!canControl || busy}
              onClick={() => mutation.mutate(() => dryingSchedulesApi.resolve(Number(printerId), run.id))}>{t('scheduledDrying.resolve')}</Button>}
          </li>)}
        </ul>
        <p className="text-xs text-bambu-gray">{t('scheduledDrying.resolveHelp')}</p>
      </>}
    </section>
  );
}
