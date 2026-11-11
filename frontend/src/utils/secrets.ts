import type { FocusEvent } from 'react';
import type { AppSettings, AppSettingsUpdate } from '../api/client';

export const SECRET_PLACEHOLDER = '********';

export function selectPlaceholderOnFocus(event: FocusEvent<HTMLInputElement | HTMLTextAreaElement>) {
  if (event.currentTarget.value === SECRET_PLACEHOLDER) event.currentTarget.select();
}

const SETTINGS_DESTINATIONS = {
  mqtt_password: ['mqtt_broker', 'mqtt_port', 'mqtt_use_tls'],
  ha_token: ['ha_url'],
} as const;
const SETTINGS_SECRETS = ['mqtt_password', 'ha_token', 'prometheus_token'] as const;

export function settingsSecretsToReenter(before: AppSettings | undefined, now: AppSettings | null): string[] {
  if (!before || !now) return [];
  return Object.entries(SETTINGS_DESTINATIONS)
    .filter(([key, fields]) => (
      now[key as keyof typeof SETTINGS_DESTINATIONS] === SECRET_PLACEHOLDER &&
      fields.some(field => String(before[field] ?? '') !== String(now[field] ?? ''))
    ))
    .map(([key]) => key);
}

export function adoptConfirmedSettingsSecrets(
  current: AppSettings | null, submitted: AppSettingsUpdate, confirmed: AppSettings,
): AppSettings | null {
  if (!current) return current;
  const changes = SETTINGS_SECRETS.filter(key => (
    key in submitted && current[key] === submitted[key] &&
    current[key] !== confirmed[key] && confirmed[key] === SECRET_PLACEHOLDER
  ));
  if (changes.length === 0) return current;
  const next = { ...current };
  for (const key of changes) next[key] = confirmed[key];
  return next;
}
