import { useTranslation } from 'react-i18next';
import { NumberField, Switch } from '../ui';

type Props = {
  enabled: boolean;
  minutes: number;
  onEnabledChange: (enabled: boolean) => void;
  onMinutesChange: (minutes: number) => void;
};

export function AmbientDryingSettings({ enabled, minutes, onEnabledChange, onMinutesChange }: Props) {
  const { t } = useTranslation();
  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <div>
          <label className="block text-sm text-white" htmlFor="ambient-drying-enabled">
            {t('settings.ambientDryingEnabled')}
          </label>
          <p className="text-xs text-bambu-gray mt-0.5">{t('settings.ambientDryingEnabledDescription')}</p>
        </div>
        <Switch id="ambient-drying-enabled" checked={enabled} onChange={(e) => onEnabledChange(e.target.checked)} />
      </div>
      {enabled && (
        <div className="space-y-1">
          <label className="block text-sm text-white" htmlFor="ambient-drying-sustained-minutes">
            {t('settings.ambientDryingSustainedMinutes')}
          </label>
          <NumberField
            id="ambient-drying-sustained-minutes"
            min={0}
            max={240}
            step={1}
            value={minutes}
            onChange={(e) => {
              const next = Number(e.target.value);
              if (Number.isInteger(next) && next >= 0 && next <= 240) onMinutesChange(next);
            }}
            aria-describedby="ambient-drying-sustained-help"
            containerClassName="w-full sm:w-32"
            className="w-full px-3 py-2 min-h-11 bg-bambu-dark border border-bambu-gray/30 rounded-lg text-white focus:outline-none focus:border-bambu-green"
          />
          <p id="ambient-drying-sustained-help" className="text-xs text-bambu-gray">
            {t('settings.ambientDryingSustainedDescription')}
          </p>
        </div>
      )}
    </>
  );
}
