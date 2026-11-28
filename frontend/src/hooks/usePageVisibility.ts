import { useSyncExternalStore } from 'react';

const subscribe = (onChange: () => void) => {
  document.addEventListener('visibilitychange', onChange);
  return () => document.removeEventListener('visibilitychange', onChange);
};

/**
 * True while this tab is the visible, foreground document.
 *
 * Camera streams, snapshot polling and stall checks gate on this so a
 * background tab stops pulling data: an idle MJPEG connection still costs
 * transcoder CPU server-side and keeps the radio busy on battery-powered
 * clients. useSyncExternalStore keeps concurrent renders consistent.
 */
export function usePageVisibility(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => document.visibilityState === 'visible',
    () => true,
  );
}
