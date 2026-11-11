import { useCallback, useEffect, useRef, useState } from 'react';

const RENEWAL_MS = 60_000;
const MAX_ATTEMPTS = 3;

/** Renew MJPEG feeds that can stop delivering frames without an image event. */
export function useCameraFeedRecovery(enabled: boolean, identity: string) {
  const [imageKey, setImageKey] = useState(0);
  const [waiting, setWaiting] = useState(false);
  const [failed, setFailed] = useState(false);
  const attempts = useRef(0);
  const retrying = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clear = useCallback(() => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
    retrying.current = false;
  }, []);
  const scheduleRenewal = useCallback(() => {
    clear();
    if (!enabled) return;
    const renew = () => {
      if (document.hidden) {
        timer.current = setTimeout(renew, RENEWAL_MS);
        return;
      }
      timer.current = null;
      if (attempts.current < MAX_ATTEMPTS) {
        attempts.current += 1;
        setImageKey(key => key + 1);
        timer.current = setTimeout(renew, RENEWAL_MS);
      } else {
        setFailed(true);
      }
    };
    timer.current = setTimeout(renew, RENEWAL_MS);
  }, [clear, enabled]);
  useEffect(() => {
    attempts.current = 0;
    setWaiting(false);
    setFailed(false);
    scheduleRenewal();
    return clear;
  }, [identity, scheduleRenewal, clear]);
  return {
    imageKey,
    waiting,
    failed,
    onError: () => {
      if (!enabled || retrying.current || failed) return;
      clear();
      if (attempts.current >= MAX_ATTEMPTS) {
        setFailed(true);
        return;
      }
      retrying.current = true;
      setWaiting(true);
      const delay = 3000 * 2 ** attempts.current;
      const reopen = () => {
        if (document.hidden) {
          timer.current = setTimeout(reopen, delay);
          return;
        }
        attempts.current += 1;
        setImageKey(key => key + 1);
        setWaiting(false);
        scheduleRenewal();
      };
      timer.current = setTimeout(reopen, delay);
    },
    onLoad: () => {
      attempts.current = 0;
      scheduleRenewal();
    },
  };
}
