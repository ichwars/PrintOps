import { useCallback, useEffect, useRef, useState } from 'react';

export type AutosaveStatus = 'idle' | 'pending' | 'saving' | 'saved' | 'error';

export type AutosaveAdapter<TDraft, TConfirmation> = (
  draft: TDraft,
  signal: AbortSignal,
) => Promise<TConfirmation>;

export interface UseAutosaveDraftOptions<TDraft, TConfirmation> {
  draft: TDraft;
  enabled: boolean;
  debounceMs?: number;
  fingerprint: (draft: TDraft) => string;
  adapter: AutosaveAdapter<TDraft, TConfirmation>;
  onConfirmed?: (confirmation: TConfirmation, draft: TDraft) => void;
}

export interface AutosaveController {
  status: AutosaveStatus;
  error: Error | null;
  retry: () => void;
}

export function useAutosaveDraft<TDraft, TConfirmation>({
  draft,
  enabled,
  debounceMs = 500,
  fingerprint,
  adapter,
  onConfirmed,
}: UseAutosaveDraftOptions<TDraft, TConfirmation>): AutosaveController {
  const [status, setStatus] = useState<AutosaveStatus>('idle');
  const [error, setError] = useState<Error | null>(null);
  const [retryVersion, setRetryVersion] = useState(0);
  const currentFingerprint = fingerprint(draft);
  const draftRef = useRef(draft);
  const adapterRef = useRef(adapter);
  const onConfirmedRef = useRef(onConfirmed);
  const sequenceRef = useRef(0);
  const retryImmediatelyRef = useRef(false);
  const confirmedFingerprintRef = useRef<string | null>(null);
  draftRef.current = draft;
  adapterRef.current = adapter;
  onConfirmedRef.current = onConfirmed;

  const retry = useCallback(() => {
    retryImmediatelyRef.current = true;
    setRetryVersion(version => version + 1);
  }, []);

  useEffect(() => {
    const sequence = ++sequenceRef.current;
    if (!enabled) {
      setStatus(current =>
        current === 'pending' || current === 'saving' ? 'idle' : current,
      );
      return;
    }
    if (confirmedFingerprintRef.current === currentFingerprint) {
      setError(null);
      setStatus('saved');
      return;
    }
    const controller = new AbortController();
    const delay = retryImmediatelyRef.current ? 0 : debounceMs;
    retryImmediatelyRef.current = false;
    setStatus('pending');
    setError(null);
    const timer = setTimeout(() => {
      setStatus('saving');
      const savingDraft = draftRef.current;
      void adapterRef.current(savingDraft, controller.signal).then(confirmation => {
        if (controller.signal.aborted || sequence !== sequenceRef.current) return;
        confirmedFingerprintRef.current = currentFingerprint;
        setStatus('saved');
        onConfirmedRef.current?.(confirmation, savingDraft);
      }).catch(cause => {
        if (controller.signal.aborted || sequence !== sequenceRef.current) return;
        setError(cause instanceof Error ? cause : new Error(String(cause)));
        setStatus('error');
      });
    }, delay);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [currentFingerprint, debounceMs, enabled, retryVersion]);

  return { status, error, retry };
}
