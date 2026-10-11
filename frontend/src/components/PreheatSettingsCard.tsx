import { Flame, RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { AppSettings } from '../api/client';
import { Card, CardContent, CardHeader } from './Card';
import { Button, NumberField, Switch } from './ui';
import { PreheatFilamentTargetsEditor } from './PreheatFilamentTargetsEditor';

interface Props {
  settings: AppSettings;
  onChange: <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => void;
}

export function PreheatSettingsCard({ settings, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <Card id="card-preheat">
      <CardHeader>
        <h3 className="text-base font-semibold text-white flex items-center gap-2">
          <Flame className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          {t('settings.preheatTitle', 'Preheat & Heat Soak')}
        </h3>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-bambu-gray">
          {t('settings.preheatDescription', 'Heat the bed (and chamber, if supported) and hold at temperature before each queued print starts. Helpful for engineering filaments (PA, ABS) on printers without an active chamber heater — the bed warms the chamber by radiation while the soak timer runs. The bed target is read from the print file; chamber behaviour depends on printer model.')}
        </p>
        <div className="flex items-center justify-between">
          <div className="flex-1 mr-4">
            <p className="text-sm text-white">
              {t('settings.preheatEnabled', 'Enable preheat & soak')}
            </p>
            <p className="text-xs text-bambu-gray mt-0.5">
              {t('settings.preheatEnabledDesc', 'When off, queued prints dispatch immediately.')}
            </p>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <Switch
              checked={settings.preheat_enabled ?? false}
              onChange={(e) => onChange('preheat_enabled', e.target.checked)}
            />
          </label>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
          <div>
            <label className="block text-xs text-bambu-gray mb-1">
              {t('settings.preheatMaxWait', 'Max wait (seconds)')}
            </label>
            <NumberField
              min={60}
              max={3600}
              value={settings.preheat_max_wait_seconds ?? 900}
              onChange={(e) => onChange('preheat_max_wait_seconds', Math.max(60, Math.min(3600, parseInt(e.target.value) || 900)))}
              className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm focus:outline-none focus:border-bambu-green disabled:opacity-50"
              disabled={!(settings.preheat_enabled ?? false)}
            />
            <p className="text-xs text-bambu-gray mt-1">
              {t('settings.preheatMaxWaitHelp', 'Cap on the chamber warm-up phase before falling through.')}
            </p>
          </div>
          <div>
            <label className="block text-xs text-bambu-gray mb-1">
              {t('settings.preheatSoak', 'Soak (seconds)')}
            </label>
            <NumberField
              min={0}
              max={1800}
              value={settings.preheat_soak_seconds ?? 300}
              onChange={(e) => onChange('preheat_soak_seconds', Math.max(0, Math.min(1800, parseInt(e.target.value) || 0)))}
              className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm focus:outline-none focus:border-bambu-green disabled:opacity-50"
              disabled={!(settings.preheat_enabled ?? false)}
            />
            <p className="text-xs text-bambu-gray mt-1">
              {t('settings.preheatSoakHelp', 'Hold time after target reached or max-wait elapsed.')}
            </p>
          </div>
        </div>
        <div className="pt-2 border-t border-bambu-dark-tertiary/50 space-y-2">
          <Switch
            checked={settings.queue_keep_bed_warm ?? false}
            onCheckedChange={(checked) => onChange('queue_keep_bed_warm', checked)}
            label={t('settings.queueKeepBedWarm')}
            disabled={!settings.preheat_enabled || !settings.require_plate_clear}
            helperText={t('settings.queueKeepBedWarmDesc')}
          />
          <NumberField
            id="queue-keep-warm-minutes"
            label={t('settings.queueKeepWarmMinutes')}
            min={1}
            max={30}
            value={settings.queue_keep_warm_max_minutes ?? 10}
            onChange={(event) => onChange('queue_keep_warm_max_minutes', Math.max(1, Math.min(30, parseInt(event.target.value, 10) || 10)))}
            disabled={!settings.queue_keep_bed_warm || !settings.preheat_enabled || !settings.require_plate_clear}
            helperText={t('settings.queueKeepWarmMinutesHelp')}
          />
        </div>
        {/* Per-filament chamber target editor (#1468) */}
        <div className="pt-2 border-t border-bambu-dark-tertiary/50">
          <div className="flex items-center justify-between mb-1">
            <label className="text-sm text-white">
              {t('settings.preheatFilamentTargetsLabel', 'Per-filament chamber target (°C)')}
            </label>
            <Button variant="unstyled"
              type="button"
              onClick={() => onChange('preheat_filament_targets', '')}
              title={t('settings.preheatFilamentTargetsReset', 'Reset to defaults')}
              className="text-bambu-gray hover:text-white transition-colors p-1 rounded hover:bg-bambu-dark-tertiary"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </Button>
          </div>
          <p className="text-xs text-bambu-gray mb-2">
            {t('settings.preheatFilamentTargetsHint', 'Uses only mapped filament consumed by the selected plate. PLA-only jobs skip chamber heating; unknown plate or mapping skips automatic chamber decisions.')}
          </p>
          <PreheatFilamentTargetsEditor
            value={settings.preheat_filament_targets ?? ''}
            onChange={(v) => onChange('preheat_filament_targets', v)}
            disabled={!(settings.preheat_enabled ?? false)}
          />
        </div>
        <p className="text-xs text-bambu-gray pt-1 border-t border-bambu-dark-tertiary/50">
          <span className="font-medium text-bambu-gray/90">{t('settings.preheatHardwareTitle', 'Per-printer behaviour:')}</span>{' '}
          {t('settings.preheatHardwareDetail', 'H2C/H2D/H2D Pro/H2S/X2D/X1E actively heat the chamber via M141. X1C/P2S read chamber temp but rely on bed-radiation heating. P1S/P1P/A1/A1 Mini have no chamber sensor — only the soak timer applies.')}
        </p>
      </CardContent>
    </Card>
  );
}
