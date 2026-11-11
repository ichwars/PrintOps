import { useTranslation } from 'react-i18next';
import type { AppSettings } from '../api/client';
import { NumberField } from './ui';

const retentionFields = [
  ['ams_history_retention_days', 'settings.keepSensorHistory'],
  ['printer_sensor_history_retention_days', 'settings.keepPrinterTemperatureHistory'],
] as const;

type RetentionKey = typeof retentionFields[number][0];

export function SensorHistoryRetentionFields({ settings, update }: {
  settings: Pick<AppSettings, RetentionKey>;
  update: (key: RetentionKey, value: number) => void;
}) {
  const { t } = useTranslation();
  return retentionFields.map(([key, label]) => (
    <div key={key}>
      <label htmlFor={key} className="mb-1 block text-sm text-bambu-gray">{t(label)}</label>
      <div className="flex items-center gap-2">
        <NumberField id={key} min="1" max="365" value={settings[key] ?? 30}
          onChange={(event) => update(key, Math.max(1, parseInt(event.target.value, 10) || 30))}
          className="w-24 px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none" />
        <span className="text-bambu-gray">{t('common.days')}</span>
      </div>
    </div>
  ));
}
