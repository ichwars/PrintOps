import { useTranslation } from 'react-i18next';
import { TextField } from './ui';
import { Toggle } from './Toggle';
import type { AppSettings } from '../api/client/types/settings-slicer';

interface HaDiscoverySettingsProps {
  localSettings: Partial<AppSettings>;
  updateSetting: <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => void;
}

/**
 * Home Assistant MQTT discovery toggle + discovery prefix field.
 * Rendered inside the MQTT Publishing card on the settings page.
 */
export function HaDiscoverySettings({ localSettings, updateSetting }: HaDiscoverySettingsProps) {
  const { t } = useTranslation();
  return (
    <div className="pt-3 mt-1 border-t border-bambu-dark-tertiary">
      <div className="flex items-center gap-3">
        <Toggle
          checked={localSettings.ha_discovery_enabled ?? false}
          onChange={(v) => updateSetting('ha_discovery_enabled', v)}
        />
        <div>
          <p className="text-white text-sm">{t('settings.haDiscovery')}</p>
          <p className="text-xs text-bambu-gray">{t('settings.haDiscoveryDescription')}</p>
        </div>
      </div>
      {localSettings.ha_discovery_enabled && (
        <div className="mt-3">
          <label className="block text-sm text-bambu-gray mb-1">
            {t('settings.discoveryPrefix')}
          </label>
          <TextField
            type="text"
            value={localSettings.ha_discovery_prefix ?? 'homeassistant'}
            onChange={(e) => updateSetting('ha_discovery_prefix', e.target.value)}
            placeholder="homeassistant"
            className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white focus:border-bambu-green focus:outline-none"
          />
          <p className="text-xs text-bambu-gray mt-1">{t('settings.discoveryPrefixHint')}</p>
        </div>
      )}
    </div>
  );
}
