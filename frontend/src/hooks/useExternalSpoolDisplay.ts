import { useCallback, useSyncExternalStore } from 'react';
import { useAuth } from '../contexts/AuthContext';

const CHANGE_EVENT = 'printops:external-spool-display-change';
const unsaved = new Map<string, boolean>();

function readHidden(key: string | null): boolean {
  if (!key) return false;
  if (unsaved.has(key)) return unsaved.get(key)!;
  try {
    return localStorage.getItem(key) === 'true';
  } catch {
    return false;
  }
}

/** Hardware serials are unique; SQLite printer IDs can be reused after deletion. */
export function useExternalSpoolDisplay(serialNumber: string | undefined) {
  const { authEnabled, authStatusVerified, loading, preferenceSubject } = useAuth();
  const scope = loading || authStatusVerified !== true ? null : !authEnabled ? 'appliance'
    : preferenceSubject ? `user:${encodeURIComponent(preferenceSubject)}` : null;
  const validSerial = typeof serialNumber === 'string' && serialNumber.trim().length > 0;
  const key = scope && validSerial
    ? `printops:external-spool-hidden:v1:${encodeURIComponent(window.location.origin)}:${scope}:printer:${encodeURIComponent(serialNumber)}`
    : null;
  const subscribe = useCallback((notify: () => void) => {
    if (!key) return () => {};
    const onChange = (event: Event) => {
      if ((event as CustomEvent<string>).detail === key) notify();
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === key || event.key === null) {
        unsaved.delete(key);
        notify();
      }
    };
    window.addEventListener(CHANGE_EVENT, onChange);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener(CHANGE_EVENT, onChange);
      window.removeEventListener('storage', onStorage);
    };
  }, [key]);
  const getSnapshot = useCallback(() => readHidden(key), [key]);
  // A different account or printer reads its own value during the first render.
  const hidden = useSyncExternalStore(subscribe, getSnapshot, () => false);
  const setHidden = useCallback((value: boolean) => {
    if (!key) return;
    try {
      if (value) localStorage.setItem(key, 'true');
      else localStorage.removeItem(key);
      unsaved.delete(key);
    } catch {
      unsaved.set(key, value);
    }
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: key }));
  }, [key]);
  return { hidden, setHidden, ready: key !== null };
}
