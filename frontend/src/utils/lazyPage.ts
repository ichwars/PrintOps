import { lazy } from 'react';

const RELOAD_KEY = 'printops:chunk-reload-at';
const RELOAD_WINDOW_MS = 10_000;
const PROBE_INTERVAL_MS = 3_000;
let recovery: Promise<boolean> | undefined;

export function isChunkLoadError(error: unknown): boolean {
  return error instanceof Error && /failed to fetch dynamically imported module|error loading dynamically imported module|importing a module script failed|unable to preload css|loading chunk.*failed/i.test(error.message);
}

async function waitForServer(): Promise<void> {
  for (;;) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), PROBE_INTERVAL_MS);
    try {
      const response = await fetch('/health', {
        cache: 'no-store',
        redirect: 'manual',
        signal: controller.signal,
      });
      if (response.status < 500) return;
    } catch {
      // Continue waiting while a restart leaves the endpoint unreachable.
    } finally {
      clearTimeout(timeout);
    }
    await new Promise<void>((resolve) => setTimeout(resolve, PROBE_INTERVAL_MS));
  }
}

export function recoverFromMissingChunk(): Promise<boolean> {
  if (!recovery) {
    recovery = waitForServer().then(() => {
      try {
        const last = Number(sessionStorage.getItem(RELOAD_KEY));
        if (last && Date.now() - last < RELOAD_WINDOW_MS) return false;
        sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
        window.location.reload();
        return true;
      } catch {
        return false;
      }
    }).then((reloaded) => {
      if (!reloaded) recovery = undefined;
      return reloaded;
    });
  }
  return recovery;
}

export const lazyPage: typeof lazy = (load) => lazy(async () => {
  try {
    return await load();
  } catch (error) {
    if (isChunkLoadError(error) && await recoverFromMissingChunk()) {
      return new Promise<never>(() => {});
    }
    throw error;
  }
});
