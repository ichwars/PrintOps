import { describe, expect, it } from 'vitest';
import type { AppSettings } from '../../api/client';
import { adoptConfirmedSettingsSecrets, SECRET_PLACEHOLDER, settingsSecretsToReenter } from '../../utils/secrets';

const baseline = {
  mqtt_broker: 'mqtt.local',
  mqtt_port: 1883,
  mqtt_use_tls: false,
  mqtt_password: SECRET_PLACEHOLDER,
  ha_url: 'http://ha.local',
  ha_token: SECRET_PLACEHOLDER,
} as AppSettings;

describe('saved settings credentials', () => {
  it('requires reentry only for retained credentials at changed destinations', () => {
    expect(settingsSecretsToReenter(baseline, { ...baseline, mqtt_use_tls: true })).toEqual(['mqtt_password']);
    expect(settingsSecretsToReenter(baseline, { ...baseline, ha_url: 'http://elsewhere.local' })).toEqual(['ha_token']);
    expect(settingsSecretsToReenter(baseline, { ...baseline, mqtt_port: 8883, mqtt_password: 'new' })).toEqual([]);
    expect(settingsSecretsToReenter(baseline, { ...baseline, mqtt_broker: 'new.local', mqtt_password: '' })).toEqual([]);
  });

  it('uses the server placeholder only for the credential that was just confirmed', () => {
    const edited = { ...baseline, mqtt_password: 'submitted', ha_token: 'later edit' };
    const submitted = { mqtt_password: 'submitted', ha_token: 'earlier edit' };
    expect(adoptConfirmedSettingsSecrets(edited, submitted, baseline)).toEqual({
      ...edited,
      mqtt_password: SECRET_PLACEHOLDER,
    });
  });
});
