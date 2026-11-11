import { useCallback, useMemo, useSyncExternalStore } from 'react';
import type { Printer } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

const CHANGE_EVENT = 'printops:open-cameras-change';
const unsaved = new Map<string, string>();
type CameraPlacement = 'printers' | 'app';

export function useCameraOverlayAccount(): string | null {
  const { authEnabled, authStatusVerified, preferenceSubject, loading, hasPermission } = useAuth();
  if (loading || authStatusVerified !== true || !hasPermission('camera:view')) return null;
  return !authEnabled ? 'appliance' : preferenceSubject ? `user:${encodeURIComponent(preferenceSubject)}` : null;
}

function read(key: string, placement: CameraPlacement): string {
  if (unsaved.has(key)) return unsaved.get(key)!;
  try {
    const storage = placement === 'app' ? sessionStorage : localStorage;
    return storage.getItem(key) ?? '[]';
  } catch {
    return '[]';
  }
}

function decode(raw: string): string[] {
  try {
    const value: unknown = JSON.parse(raw);
    return Array.isArray(value) ? value.filter((serial): serial is string => typeof serial === 'string' && serial.trim().length > 0) : [];
  } catch {
    return [];
  }
}

function useStoredCameras(account: string | null, placement: CameraPlacement) {
  const prefix = placement === 'app' ? 'printops:app-cameras:v1' : 'printops:open-cameras:v1';
  const key = account ? `${prefix}:${encodeURIComponent(window.location.origin)}:${account}` : null;
  const subscribe = useCallback((notify: () => void) => {
    if (!key) return () => {};
    const onChange = (event: Event) => { if ((event as CustomEvent<string>).detail === key) notify(); };
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
  const snapshot = useCallback(() => key ? read(key, placement) : '[]', [key, placement]);
  const raw = useSyncExternalStore(subscribe, snapshot, () => '[]');
  const serials = useMemo(() => new Set(decode(raw)), [raw]);

  const update = useCallback((serial: string, open: boolean) => {
    if (!key || !serial.trim()) return false;
    const previous = new Set(decode(read(key, placement)));
    if (previous.has(serial) === open) return true;
    if (open) previous.add(serial); else previous.delete(serial);
    const value = JSON.stringify([...previous]);
    try {
      const storage = placement === 'app' ? sessionStorage : localStorage;
      if (previous.size) storage.setItem(key, value); else storage.removeItem(key);
      unsaved.delete(key);
    } catch {
      unsaved.set(key, value);
    }
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: key }));
    return true;
  }, [key, placement]);

  return { serials, update };
}

export function useCameraOverlayStore() {
  const account = useCameraOverlayAccount();
  const page = useStoredCameras(account, 'printers');
  const app = useStoredCameras(account, 'app');
  return { account, page, app };
}

/** Restore only cameras belonging to this verified account and accessible hardware. */
export function useEmbeddedCameraSelection(printers: Printer[] | undefined) {
  const { account, page, app } = useCameraOverlayStore();
  const cameras = useMemo(() => (printers ?? []).filter(printer =>
    page.serials.has(printer.serial_number) && !app.serials.has(printer.serial_number),
  ), [printers, page.serials, app.serials]);
  return {
    cameras,
    ready: account !== null,
    openCamera: (id: number) => {
      const printer = printers?.find(candidate => candidate.id === id);
      return printer ? app.serials.has(printer.serial_number) || page.update(printer.serial_number, true) : false;
    },
    closeCamera: (id: number) => {
      const printer = printers?.find(candidate => candidate.id === id);
      return printer ? page.update(printer.serial_number, false) : false;
    },
  };
}
