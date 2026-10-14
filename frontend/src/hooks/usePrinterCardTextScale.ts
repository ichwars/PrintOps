import { useCallback, useSyncExternalStore } from 'react';
import { useAuth } from '../contexts/AuthContext';

export const CARD_TEXT_SCALES = [90, 100, 110, 120] as const;
export type CardTextScale = typeof CARD_TEXT_SCALES[number];
const CHANGE_EVENT = 'printops:card-text-scale-change';
const unsaved = new Map<string, CardTextScale>();
const isScale = (value: number): value is CardTextScale => CARD_TEXT_SCALES.some(scale => scale === value);

function readScale(key: string | null): CardTextScale {
  if (!key) return 100;
  if (unsaved.has(key)) return unsaved.get(key)!;
  try {
    const saved = localStorage.getItem(key);
    const value = Number(saved);
    return saved !== null && isScale(value) ? value : 100;
  } catch {
    return 100;
  }
}

/** Browser-local display preference; numeric SQLite IDs can be reused after deletion. */
export function usePrinterCardTextScale() {
  const { authEnabled, authStatusVerified, loading, preferenceSubject } = useAuth();
  const scope = loading || authStatusVerified !== true ? null : !authEnabled ? 'appliance'
    : preferenceSubject ? `user:${encodeURIComponent(preferenceSubject)}` : null;
  const key = scope ? `printops:card-text-scale:v1:${encodeURIComponent(window.location.origin)}:${scope}` : null;
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
  const getSnapshot = useCallback(() => readScale(key), [key]);
  // Read the new subject during render: an account switch never paints the old choice.
  const scale = useSyncExternalStore(subscribe, getSnapshot, () => 100 as CardTextScale);
  const setScale = useCallback((value: number) => {
    if (!key || !isScale(value)) return;
    try {
      if (value === 100) localStorage.removeItem(key);
      else localStorage.setItem(key, String(value));
      unsaved.delete(key);
    } catch {
      unsaved.set(key, value);
    }
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: key }));
  }, [key]);
  return { scale, setScale, ready: key !== null };
}
