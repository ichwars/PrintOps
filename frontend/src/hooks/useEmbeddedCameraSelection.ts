import { useCallback, useMemo, useSyncExternalStore } from 'react';
import type { Printer } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

const CHANGE_EVENT = 'printops:open-cameras-change';
const unsaved = new Map<string, string>();
function read(key: string | null): string {
  if (!key) return '[]';
  if (unsaved.has(key)) return unsaved.get(key)!;
  try { return localStorage.getItem(key) ?? '[]'; } catch { return '[]'; }
}
function decode(raw: string): string[] {
  try {
    const value: unknown = JSON.parse(raw);
    return Array.isArray(value) ? value.filter((serial): serial is string => typeof serial === 'string' && serial.trim().length > 0) : [];
  } catch { return []; }
}

/** Restore only cameras belonging to this verified account and accessible hardware. */
export function useEmbeddedCameraSelection(printers: Printer[] | undefined) {
  const { authEnabled, authStatusVerified, preferenceSubject, loading, hasPermission } = useAuth();
  const scope = loading || authStatusVerified !== true || !hasPermission('camera:view') ? null
    : !authEnabled ? 'appliance' : preferenceSubject ? `user:${encodeURIComponent(preferenceSubject)}` : null;
  const key = scope ? `printops:open-cameras:v1:${encodeURIComponent(window.location.origin)}:${scope}` : null;
  const subscribe = useCallback((notify: () => void) => {
    if (!key) return () => {};
    const onChange = (event: Event) => { if ((event as CustomEvent<string>).detail === key) notify(); };
    const onStorage = (event: StorageEvent) => {
      if (event.key === key || event.key === null) { unsaved.delete(key); notify(); }
    };
    window.addEventListener(CHANGE_EVENT, onChange);
    window.addEventListener('storage', onStorage);
    return () => { window.removeEventListener(CHANGE_EVENT, onChange); window.removeEventListener('storage', onStorage); };
  }, [key]);
  const snapshot = useCallback(() => read(key), [key]);
  const raw = useSyncExternalStore(subscribe, snapshot, () => '[]');
  const cameras = useMemo(() => {
    if (!key) return [];
    const selected = new Set(decode(raw));
    return (printers ?? []).filter(printer => selected.has(printer.serial_number));
  }, [key, printers, raw]);
  const update = useCallback((id: number, open: boolean) => {
    if (!key) return;
    const printer = printers?.find(candidate => candidate.id === id);
    if (!printer?.serial_number?.trim()) return;
    const serials = new Set(decode(read(key)));
    if (open) serials.add(printer.serial_number); else serials.delete(printer.serial_number);
    const value = JSON.stringify([...serials]);
    try {
      if (serials.size) localStorage.setItem(key, value); else localStorage.removeItem(key);
      unsaved.delete(key);
    } catch { unsaved.set(key, value); }
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: key }));
  }, [key, printers]);
  return { cameras, openCamera: (id: number) => update(id, true), closeCamera: (id: number) => update(id, false) };
}
