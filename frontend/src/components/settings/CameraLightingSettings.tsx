import { useTranslation } from 'react-i18next';
import type { AppSettings, Printer } from '../../api/client';
import { NumberField, Select, Switch } from '../ui';

type LightingMode = AppSettings['camera_light_mode'];

interface CameraLightingSettingsProps {
  mode: LightingMode;
  delay: number;
  printers: Printer[] | undefined;
  printerChangesDisabled: boolean;
  onModeChange: (mode: LightingMode) => void;
  onDelayChange: (delay: number) => void;
  onPrinterChange: (id: number, enabled: boolean) => void;
}

export function CameraLightingSettings({
  mode, delay, printers, printerChangesDisabled, onModeChange, onDelayChange, onPrinterChange,
}: CameraLightingSettingsProps) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2 border-t border-bambu-dark-tertiary pt-3">
      <label className="text-sm text-bambu-gray">{t('settings.cameraLight')}</label>
      <Select ariaLabel={t('settings.cameraLight')} value={mode}
        onValueChange={(value) => onModeChange(value as LightingMode)}
        options={[
          { value: 'off', label: t('settings.cameraLightOff') },
          { value: 'all', label: t('settings.cameraLightAll') },
          { value: 'selected', label: t('settings.cameraLightSelected') },
        ]} />
      {mode !== 'off' && (
        <NumberField label={t('settings.cameraLightDelay')} min={0} max={5} step={0.5} value={delay}
          onValueChange={(raw) => {
            const value = Number(raw);
            if (raw.trim() && Number.isFinite(value) && value >= 0 && value <= 5) onDelayChange(value);
          }} />
      )}
      {mode === 'selected' && printers?.map((printer) => (
        <label key={printer.id} className="flex items-center justify-between gap-2 text-sm">
          {printer.name}
          <Switch checked={printer.camera_light_auto === true}
            disabled={printerChangesDisabled}
            onChange={(event) => onPrinterChange(printer.id, event.target.checked)} />
        </label>
      ))}
    </div>
  );
}
