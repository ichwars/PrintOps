import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  Activity,
  AlertTriangle,
  DoorClosed,
  DoorOpen,
  Droplets,
  Gauge,
  Lock,
  LockOpen,
  Thermometer,
  Wind,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { api } from '../api/client';
import type { PrinterHASensorReading } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { TextField } from './ui';

/**
 * The Home Assistant sensors bound to a printer, on its card (#1148, #448).
 *
 * Sensor values are read-only. A queue supervisor can temporarily override an
 * unavailable fail-closed interlock here, with a mandatory audited reason;
 * positive unsafe readings remain non-bypassable.
 */

// Home Assistant's own device_class decides the wording, so a door reads
// "Open"/"Closed" rather than the "on"/"off" the API actually carries. Classes
// absent from this map fall through to on/off, which is what HA itself shows
// for a binary_sensor with no class.
const BINARY_LABELS: Record<string, { on: string; off: string }> = {
  door: { on: 'open', off: 'closed' },
  garage_door: { on: 'open', off: 'closed' },
  window: { on: 'open', off: 'closed' },
  opening: { on: 'open', off: 'closed' },
  lock: { on: 'unlocked', off: 'locked' },
  motion: { on: 'detected', off: 'clear' },
  occupancy: { on: 'detected', off: 'clear' },
  presence: { on: 'detected', off: 'clear' },
  smoke: { on: 'detected', off: 'clear' },
  gas: { on: 'detected', off: 'clear' },
  moisture: { on: 'wet', off: 'dry' },
  problem: { on: 'problem', off: 'ok' },
  safety: { on: 'problem', off: 'ok' },
  running: { on: 'running', off: 'stopped' },
};

const ICONS: Record<string, LucideIcon> = {
  door: DoorOpen,
  garage_door: DoorOpen,
  window: DoorOpen,
  opening: DoorOpen,
  lock: LockOpen,
  temperature: Thermometer,
  humidity: Droplets,
  moisture: Droplets,
  motion: Activity,
  occupancy: Activity,
  presence: Activity,
  smoke: AlertTriangle,
  gas: AlertTriangle,
  problem: AlertTriangle,
  safety: AlertTriangle,
  running: Wind,
};

function iconFor(reading: PrinterHASensorReading): LucideIcon {
  const deviceClass = reading.device_class ?? '';
  // A closed door wants the closed-door glyph — the map is keyed by class, so
  // the two states that have a distinct "off" icon are special-cased here.
  if (reading.state === 'off') {
    if (ICONS[deviceClass] === DoorOpen) return DoorClosed;
    if (ICONS[deviceClass] === LockOpen) return Lock;
  }
  return ICONS[deviceClass] ?? (reading.kind === 'numeric' ? Gauge : Activity);
}

interface Props {
  printerId: number;
}

export function PrinterHASensorRow({ printerId }: Props) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const [showOverrideForm, setShowOverrideForm] = useState(false);
  const [overrideReason, setOverrideReason] = useState('');

  const { data: readings } = useQuery({
    queryKey: ['haSensorReadings', printerId],
    queryFn: () => api.getHASensorReadings(printerId),
    // Served from the backend poller's cache, so this costs a local request
    // and never a Home Assistant round trip. Matched to the poller's own
    // cadence — refetching faster would only re-read the same reading.
    refetchInterval: 15000,
  });

  const { data: override } = useQuery({
    queryKey: ['haInterlockOverride', printerId],
    queryFn: () => api.getHAInterlockOverride(printerId),
    refetchInterval: 15000,
  });

  const refreshOverride = (status: Awaited<ReturnType<typeof api.getHAInterlockOverride>>) => {
    queryClient.setQueryData(['haInterlockOverride', printerId], status);
    queryClient.invalidateQueries({ queryKey: ['printQueue'] });
  };

  const overrideMutation = useMutation({
    mutationFn: () => api.setHAInterlockOverride(printerId, overrideReason.trim()),
    onSuccess: (status) => {
      refreshOverride(status);
      setOverrideReason('');
      setShowOverrideForm(false);
    },
  });

  const clearMutation = useMutation({
    mutationFn: () => api.clearHAInterlockOverride(printerId),
    onSuccess: refreshOverride,
  });

  const showOverride = Boolean(override?.overridden || override?.overrideable_sensors.length);
  if (!readings?.length && !showOverride) return null;

  const describe = (reading: PrinterHASensorReading): string => {
    if (!reading.reachable || reading.state === null) return t('haSensors.unavailable');
    if (reading.kind === 'numeric') {
      if (reading.value === null) return reading.state;
      return reading.unit ? `${reading.value} ${reading.unit}` : String(reading.value);
    }
    const labels = BINARY_LABELS[reading.device_class ?? ''];
    const key = labels ? labels[reading.state === 'on' ? 'on' : 'off'] : reading.state;
    return t(`haSensors.states.${key}`, { defaultValue: key });
  };

  return (
    <div className="mt-2 space-y-1.5">
      {readings?.length ? <div className="flex items-center gap-2">
        <Gauge className="w-[var(--pc-i35,0.875rem)] h-[var(--pc-i35,0.875rem)] text-blue-600 dark:text-blue-400 flex-shrink-0" />
        <span className="text-xs text-bambu-gray">{t('haSensors.label')}</span>
        <div className="h-[2px] w-5 bg-bambu-dark-tertiary/50" />
        <div className="flex flex-wrap gap-1">
          {readings.map((reading) => {
          const Icon = iconFor(reading);
          const unreachable = !reading.reachable || reading.state === null;
          return (
            <span
              key={reading.id}
              title={
                reading.block_print
                  ? t('haSensors.blocksPrints', { entity: reading.entity_id })
                  : reading.entity_id
              }
              className={`px-2 py-0.5 text-xs rounded flex items-center gap-1 ${
                unreachable
                  ? 'bg-bambu-dark-tertiary/50 text-bambu-gray'
                  : reading.alerting
                    ? 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-400'
                    : 'bg-bambu-dark-tertiary text-bambu-gray'
              }`}
            >
              <Icon className="w-[var(--pc-i25,0.625rem)] h-[var(--pc-i25,0.625rem)]" />
              <span>{reading.name}</span>
              <span className="font-medium">{describe(reading)}</span>
            </span>
          );
          })}
        </div>
      </div>
      : null}

      {showOverride && hasPermission('queue:update_all') ? (
        <div className="ml-6 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-xs text-amber-200">
          {override?.overridden ? (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>
                {t('haSensors.override.active', {
                  user: override.username ?? t('haSensors.override.unknownUser'),
                  reason: override.reason ?? '',
                })}
              </span>
              <button
                type="button"
                className="rounded bg-bambu-dark px-2 py-1 text-white hover:bg-bambu-dark-tertiary disabled:opacity-50"
                onClick={() => clearMutation.mutate()}
                disabled={clearMutation.isPending}
              >
                {t('haSensors.override.clear')}
              </button>
            </div>
          ) : showOverrideForm ? (
            <div className="space-y-1.5">
              <label className="block" htmlFor={`ha-override-reason-${printerId}`}>
                {t('haSensors.override.reasonLabel')}
              </label>
              <div className="flex flex-wrap gap-1.5">
                <TextField
                  id={`ha-override-reason-${printerId}`}
                  value={overrideReason}
                  onChange={(event) => setOverrideReason(event.target.value)}
                  maxLength={500}
                  className="min-w-48 flex-1 rounded border border-bambu-dark-tertiary bg-bambu-dark px-2 py-1 text-white"
                />
                <button
                  type="button"
                  className="rounded bg-amber-600 px-2 py-1 text-white disabled:opacity-50"
                  onClick={() => overrideMutation.mutate()}
                  disabled={overrideReason.trim().length < 3 || overrideMutation.isPending}
                >
                  {t('haSensors.override.confirm')}
                </button>
                <button
                  type="button"
                  className="rounded bg-bambu-dark px-2 py-1 text-white"
                  onClick={() => setShowOverrideForm(false)}
                >
                  {t('common.cancel')}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>
                {t('haSensors.override.unavailable', {
                  sensors: override?.overrideable_sensors.join(', '),
                })}
              </span>
              <button
                type="button"
                className="rounded bg-amber-600 px-2 py-1 text-white"
                onClick={() => setShowOverrideForm(true)}
              >
                {t('haSensors.override.open')}
              </button>
            </div>
          )}
          {overrideMutation.isError || clearMutation.isError ? (
            <p className="mt-1 text-red-300">{t('haSensors.override.error')}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
