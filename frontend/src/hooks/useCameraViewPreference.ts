import { useCallback, useState, useSyncExternalStore } from 'react';
import { useAuth } from '../contexts/AuthContext';

export type CameraViewPreference = 'stream' | 'snapshot';
export type CameraPlacement = 'window' | 'embedded';
type CameraPreference = CameraViewPreference | CameraPlacement;

const CHANGE_EVENT = 'printops:camera-view-change';
// Keep the selection usable in this tab when browser storage is unavailable.
// Every entry has the same origin/user/printer scope as its storage key.
const unsavedPreferences = new Map<string, CameraPreference | null>();

function readPreference<T extends CameraPreference>(key: string | null, choices: readonly T[]): T | null {
  if (!key) return null;
  if (unsavedPreferences.has(key)) return (unsavedPreferences.get(key) as T | null) ?? null;
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(key) ?? 'null');
    if (saved && typeof saved === 'object' && 'version' in saved && saved.version === 1
      && 'mode' in saved && choices.includes(saved.mode as T)) {
      return saved.mode as T;
    }
  } catch {
    // Missing storage, invalid JSON and old formats all use the default.
  }
  return null;
}

interface CameraPreferenceOptions<T> {
  /** Public camera links never read or change an authenticated user's defaults. */
  anonymous?: boolean;
  /** Nonsecret launch hint, including when the opener cannot persist storage. */
  initialMode?: T;
}

function useCameraPreference<T extends CameraPreference>(serialNumber: string | undefined, namespace: string, choices: readonly T[], fallback: T,
  { anonymous = false, initialMode }: CameraPreferenceOptions<T> = {}) {
  const { authEnabled, authStatusVerified, preferenceSubject, loading } = useAuth();
  const validPrinter = typeof serialNumber === 'string' && serialNumber.trim().length > 0;
  const scope = loading || anonymous || authStatusVerified !== true ? null
    : !authEnabled ? 'appliance' : preferenceSubject ? `user:${encodeURIComponent(preferenceSubject)}` : null;
  const key = scope && validPrinter ? `printops:${namespace}:${encodeURIComponent(window.location.origin)}:${scope}:printer:${encodeURIComponent(serialNumber)}` : null;
  // No numeric-ID migration: deleted accounts and printers can reuse IDs.
  // Anonymous state follows its route identity, independently of private auth/metadata resolution.
  const identity = `${anonymous ? `anonymous:${serialNumber ?? ''}` : key ?? `${loading}:${authStatusVerified}:${authEnabled}:${preferenceSubject ?? ''}:${anonymous}:${serialNumber ?? ''}`}:${initialMode ?? ''}`;
  const [local, setLocal] = useState<{ identity: string; value: T | null | undefined }>(() => ({ identity, value: initialMode }));
  if (local.identity !== identity) {
    setLocal({ identity, value: initialMode });
  }

  const subscribe = useCallback((notify: () => void) => {
    if (!key) return () => {};
    const preferenceChanged = () => {
      // A URL hint only chooses the opening view. Later changes to this exact
      // user's printer default also apply when the saved value stays null.
      setLocal(current => current.identity === identity && current.value !== undefined
        ? { identity, value: undefined }
        : current);
      notify();
    };
    const onChange = (event: Event) => {
      if ((event as CustomEvent<string>).detail === key) preferenceChanged();
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === key || event.key === null) {
        unsavedPreferences.delete(key);
        preferenceChanged();
      }
    };
    window.addEventListener(CHANGE_EVENT, onChange);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener(CHANGE_EVENT, onChange);
      window.removeEventListener('storage', onStorage);
    };
  }, [identity, key]);
  const getSnapshot = useCallback(() => readPreference(key, choices), [key, choices]);
  const savedPreference = useSyncExternalStore(subscribe, getSnapshot, () => null);
  // Derive the current identity's value during render, before effects run.
  const override = local.identity === identity ? local.value : initialMode;
  const preference = override === undefined ? savedPreference : override;

  const setPreference = useCallback((value: T | null) => {
    if (loading && !anonymous) return;
    if (!key) {
      setLocal({ identity, value });
      return;
    }
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, JSON.stringify({ version: 1, mode: value }));
      unsavedPreferences.delete(key);
    } catch {
      unsavedPreferences.set(key, value);
    }
    setLocal({ identity, value: undefined });
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: key }));
  }, [identity, key, loading, anonymous]);

  return { preference, mode: preference ?? fallback, setPreference, ready: anonymous || !loading, identity, verified: scope !== null };
}

const CONTENT_CHOICES = ['stream', 'snapshot'] as const;
const PLACEMENT_CHOICES = ['window', 'embedded'] as const;

export function useCameraViewPreference(serialNumber: string | undefined, options: CameraPreferenceOptions<CameraViewPreference> = {}) {
  return useCameraPreference(serialNumber, 'camera-view:v2', CONTENT_CHOICES, 'stream', options);
}

export function useCameraPlacementPreference(serialNumber: string | undefined, fallback: CameraPlacement) {
  const placement = useCameraPreference(serialNumber, 'camera-placement:v1', PLACEMENT_CHOICES, fallback);
  return { ...placement, ready: placement.ready && placement.verified };
}
