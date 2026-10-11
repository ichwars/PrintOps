import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api, type StorageHASensor } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { Button } from './Button';
import { Checkbox, LegacySelect, Modal, NumberField, TextField } from './ui';

export function StorageLocationSensors({ locationId, locationName }: { locationId: number; locationName: string }) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [open, setOpen] = useState(false);
  const { data: readings = [], isError } = useQuery({
    queryKey: ['storageHASensorReadings'], queryFn: api.getStorageHASensorReadings,
    enabled: hasPermission('inventory:read'), refetchInterval: 15000,
  });
  return <div className="space-y-1">
    {isError && <span className="text-bambu-gray">{t('storageSensors.loadFailed')}</span>}
    {readings.filter((reading) => reading.location_id === locationId).map((reading) => (
      <div key={reading.id} className={reading.alerting ? 'text-amber-500' : 'text-bambu-gray'}>
        {reading.name}: {reading.value === null ? '—' : `${reading.value} ${reading.unit}`}
        <span className="ml-1 text-xs">{t(`storageSensors.${reading.status}`)}</span>
        {reading.last_read_at && <time className="block text-xs" dateTime={`${reading.last_read_at}Z`}>
          {t('storageSensors.lastRead', { time: new Date(`${reading.last_read_at}Z`).toLocaleString() })}
        </time>}
      </div>
    ))}
    {hasPermission('inventory:update') && <Button variant="secondary" size="sm" onClick={(event) => { event.stopPropagation(); setOpen(true); }}>
      {t('storageSensors.manage')}
    </Button>}
    {open && <StorageSensorEditor locationId={locationId} locationName={locationName} onClose={() => setOpen(false)} />}
  </div>;
}

function StorageSensorEditor({ locationId, locationName, onClose }: { locationId: number; locationName: string; onClose: () => void }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [editing, setEditing] = useState<StorageHASensor | null>(null);
  const [entityId, setEntityId] = useState('');
  const [name, setName] = useState('');
  const [above, setAbove] = useState('');
  const [below, setBelow] = useState('');
  const [notify, setNotify] = useState(false);
  const [error, setError] = useState('');
  const { data: sensors = [], isError: sensorsError } = useQuery({ queryKey: ['storageHASensors', locationId], queryFn: () => api.getStorageHASensors(locationId) });
  const { data: entities = [], isLoading, isError: entitiesError } = useQuery({ queryKey: ['storageHAEntities'], queryFn: api.getStorageHAEntities, retry: false });
  const selected = entities.find((entity) => entity.entity_id === entityId);
  const reset = () => { setEditing(null); setEntityId(''); setName(''); setAbove(''); setBelow(''); setNotify(false); setError(''); };
  const invalidate = () => { client.invalidateQueries({ queryKey: ['storageHASensors'] }); client.invalidateQueries({ queryKey: ['storageHASensorReadings'] }); };
  const save = useMutation({
    mutationFn: async () => {
      const device_class = selected?.device_class ?? editing?.device_class;
      const unit = selected?.unit_of_measurement ?? editing?.unit;
      if (!entityId || !name.trim() || !device_class || !unit) throw new Error(t('haSensors.error.pickEntity'));
      if (notify && above === '' && below === '') throw new Error(t('haSensors.error.alertRequired'));
      const payload = { name: name.trim(), entity_id: entityId, device_class: device_class as 'temperature' | 'humidity', unit: unit as '°C' | '°F' | 'K' | '%', alert_above: above === '' ? null : Number(above), alert_below: below === '' ? null : Number(below), notify_on_alert: notify };
      return editing ? api.updateStorageHASensor(editing.id, payload) : api.createStorageHASensor({ ...payload, location_id: locationId });
    },
    onSuccess: () => { invalidate(); reset(); }, onError: (err: Error) => setError(err.message),
  });
  const remove = useMutation({ mutationFn: api.deleteStorageHASensor, onSuccess: () => { invalidate(); reset(); }, onError: (err: Error) => setError(err.message) });
  const busy = save.isPending || remove.isPending;
  const edit = (sensor: StorageHASensor) => { setEditing(sensor); setEntityId(sensor.entity_id); setName(sensor.name); setAbove(sensor.alert_above?.toString() ?? ''); setBelow(sensor.alert_below?.toString() ?? ''); setNotify(sensor.notify_on_alert); setError(''); };
  return <div onClick={(event) => event.stopPropagation()}>
    <Modal open onClose={() => { if (!busy) onClose(); }} closeDisabled={busy} closeLabel={t('common.close')} title={t('storageSensors.title', { location: locationName })} description={t('storageSensors.hint')} className="max-w-lg">
      {(error || sensorsError) && <p role="alert" className="text-red-500">{error || t('storageSensors.loadFailed')}</p>}
      {sensors.map((sensor) => <div key={sensor.id} className="flex items-center justify-between gap-2 text-white">
        <span>{sensor.name} <span className="text-xs text-bambu-gray">{sensor.entity_id}</span></span>
        <Button variant="secondary" size="sm" disabled={busy} onClick={() => edit(sensor)}>{t('common.edit')}</Button>
      </div>)}
      <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        {entitiesError && <p className="text-sm text-amber-500">{t('storageSensors.entitiesFailed')}</p>}
        <LegacySelect label={t('haSensors.entity')} value={entityId} disabled={busy || isLoading} onChange={(event) => {
          const entity = entities.find((item) => item.entity_id === event.target.value);
          setEntityId(event.target.value); setAbove(''); setBelow(''); setNotify(false);
          if (entity) setName(entity.friendly_name.slice(0, 100));
        }}>
          <option value="">{t('haSensors.error.pickEntity')}</option>
          {editing && !entities.some((entity) => entity.entity_id === editing.entity_id) && <option value={editing.entity_id}>{editing.entity_id}</option>}
          {entities.map((entity) => <option key={entity.entity_id} value={entity.entity_id}>{entity.friendly_name} ({entity.unit_of_measurement})</option>)}
        </LegacySelect>
        <TextField label={t('haSensors.name')} value={name} required maxLength={100} disabled={busy} onChange={(event) => setName(event.target.value)} />
        <NumberField label={t('haSensors.alertAbove')} value={above} suffix={selected?.unit_of_measurement ?? editing?.unit} step="any" disabled={busy} onValueChange={setAbove} />
        <NumberField label={t('haSensors.alertBelow')} value={below} suffix={selected?.unit_of_measurement ?? editing?.unit} step="any" disabled={busy} onValueChange={setBelow} />
        <Checkbox label={t('haSensors.notifyOnAlert')} checked={notify} disabled={busy} onChange={(event) => setNotify(event.target.checked)} />
        <p className="text-xs text-bambu-gray">{t('storageSensors.notifyHint')}</p>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={busy || (!selected && !editing)}>{t('common.save')}</Button>
          {editing && <Button type="button" variant="danger" disabled={busy} onClick={() => remove.mutate(editing.id)}>{t('common.delete')}</Button>}
          <Button type="button" variant="secondary" disabled={busy} onClick={reset}>{t('common.add')}</Button>
          <Button type="button" variant="secondary" disabled={busy} onClick={onClose}>{t('common.close')}</Button>
        </div>
      </form>
    </Modal>
  </div>;
}
