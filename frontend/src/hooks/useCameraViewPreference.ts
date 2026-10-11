import { useCallback, useState, useSyncExternalStore } from 'react';
import { useAuth } from '../contexts/AuthContext';

export type CameraViewPreference = 'stream' | 'snapshot';

const CHANGE_EVENT = 'printops:camera-view-change';
// Keep the selection usable in this tab when browser storage is unavailable.
// Every entry has the same origin/user/printer scope as its storage key.
const unsavedPreferences = new Map<string, CameraViewPreference | null>();

function readPreference(key: string | null): CameraViewPreference | null {
  if (!key) return null;
  if (unsavedPreferences.has(key)) return unsavedPreferences.get(key) ?? null;
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(key) ?? 'null');
    if (saved && typeof saved === 'object' && 'version' in saved && saved.version === 1
      && 'mode' in saved && (saved.mode === 'stream' || saved.mode === 'snapshot')) {
      return saved.mode;
    }
  } catch {
    // Missing storage, invalid JSON and old formats all use the default.
  }
  return null;
}

interface CameraViewPreferenceOptions {
  /** Public camera links never read or change an authenticated user's defaults. */
  anonymous?: boolean;
  /** Nonsecret launch hint, including when the opener cannot persist storage. */
  initialMode?: CameraViewPreference;
}

export function useCameraViewPreference(printerId: number, { anonymous = false, initialMode }: CameraViewPreferenceOptions = {}) {
  const { authEnabled, user, loading } = useAuth();
  const validPrinter = Number.isSafeInteger(printerId) && printerId > 0;
  const scope = loading || anonymous || !validPrinter
    ? null
    : !authEnabled ? 'appliance' : user && Number.isSafeInteger(user.id) && user.id > 0 ? `user:${user.id}` : null;
  const key = scope ? `printops:camera-view:v1:${encodeURIComponent(window.location.origin)}:${scope}:${printerId}` : null;
  // Volatile selections are private to this hook and reset with identity too.
  const identity = `${key ?? `${loading ? 'loading' : authEnabled ? `signed-out:${user?.id ?? ''}` : 'local'}:${anonymous}:${printerId}`}:${initialMode ?? ''}`;
  const [local, setLocal] = useState<{ identity: string; value: CameraViewPreference | null | undefined }>(() => ({ identity, value: initialMode }));
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
  const getSnapshot = useCallback(() => readPreference(key), [key]);
  const savedPreference = useSyncExternalStore(subscribe, getSnapshot, () => null);
  // Derive the current identity's value during render, before effects run.
  const override = local.identity === identity ? local.value : initialMode;
  const preference = override === undefined ? savedPreference : override;

  const setPreference = useCallback((value: CameraViewPreference | null) => {
    if (loading || !validPrinter) return;
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
  }, [identity, key, loading, validPrinter]);

  return { preference, mode: preference ?? 'stream', setPreference, ready: !loading, identity };
}
