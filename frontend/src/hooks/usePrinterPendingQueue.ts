import { useSyncExternalStore } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, getAuthSessionId, subscribeAuthSession } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

/** Share the card badge/preview snapshot without sharing another session's rows. */
export function usePrinterPendingQueue(printerId: number, printerModel?: string | null) {
  const { authEnabled, authStatusVerified, loading, user, preferenceSubject, hasAnyPermission } = useAuth();
  const session = useSyncExternalStore(subscribeAuthSession, getAuthSessionId);
  const enabled = !loading && authStatusVerified && (!authEnabled || user !== null)
    && hasAnyPermission('queue:read_all', 'queue:read_own');
  // The credential generation also isolates verified API-key sessions, which
  // have no user subject. Never use a reusable numeric user ID as identity.
  const subject = authEnabled ? preferenceSubject : 'appliance';
  const query = useQuery({
    queryKey: ['queue', printerId, 'pending', printerModel, subject, session],
    queryFn: () => api.getQueue(printerId, 'pending', printerModel || undefined),
    enabled,
    refetchInterval: 30000,
  });
  // A permissions refresh or rejected revalidation must hide cached rows too.
  return { data: enabled && !query.isError ? query.data : undefined };
}
