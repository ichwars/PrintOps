import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '../Card';
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
    <Card className="mb-4">
      <CardContent className="space-y-3 py-3">
        <div className="flex items-center justify-between gap-3">
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
      </CardContent>
    </Card>
  );
}
