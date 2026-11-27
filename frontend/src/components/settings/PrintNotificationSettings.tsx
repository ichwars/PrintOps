import { useTranslation } from 'react-i18next';
import { NumberField } from '../ui';

interface PrintNotificationSettingsProps {
  pauseWarningMinutes: number;
  onPauseWarningMinutesChange: (value: number) => void;
}

export function PrintNotificationSettings({
  pauseWarningMinutes,
  onPauseWarningMinutesChange,
}: PrintNotificationSettingsProps) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-bambu-dark-tertiary px-3 py-2">
      <span className="text-sm font-medium text-white">{t('settings.pauseWarningMinutes')}</span>
      <NumberField
        aria-label={t('settings.pauseWarningMinutes')}
        min={1}
        max={120}
        step={1}
        value={pauseWarningMinutes}
        onChange={(event) => onPauseWarningMinutesChange(Number(event.target.value))}
        onBlur={() => onPauseWarningMinutesChange(Math.max(1, Math.min(120, Math.round(pauseWarningMinutes))))}
        containerClassName="w-24"
        className="text-sm"
      />
    </div>
  );
}
