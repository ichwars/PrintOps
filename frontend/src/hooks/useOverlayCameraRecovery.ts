import { useCallback, useEffect, useRef, useState } from 'react';

/** MJPEG images expose no frame clock. A bounded lease also replaces silently stalled connections. */
export function useOverlayCameraRecovery(enabled: boolean, identity: string) {
  const [imageKey, setImageKey] = useState(0);
  const attempts = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clear = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
  }, []);
  const schedule = useCallback((delay: number) => {
    clear();
    if (!enabled || attempts.current >= 3) return;
    timer.current = setTimeout(() => {
      timer.current = null;
      attempts.current += 1;
      setImageKey(key => key + 1);
    }, delay);
  }, [clear, enabled]);
  useEffect(() => {
    attempts.current = 0;
    schedule(60000);
    return clear;
  }, [identity, enabled, schedule, clear]);
  useEffect(() => {
    if (imageKey > 0) schedule(60000);
    return clear;
  }, [imageKey, schedule, clear]);
  return {
    imageKey,
    onError: () => schedule(3000 * 2 ** attempts.current),
    onLoad: () => { attempts.current = 0; schedule(60000); },
  };
}
