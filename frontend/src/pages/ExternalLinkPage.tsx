import { useSyncExternalStore } from 'react';
import { useParams } from 'react-router';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Loader2, AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api, getAuthSessionId, subscribeAuthSession } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { SidebarAppFrame } from '../components/SidebarAppFrame';

export function ExternalLinkPage() {
  const { id } = useParams<{ id: string }>();
  const { authEnabled, authStatusVerified, loading, user, preferenceSubject, authenticationEpoch, hasPermission } = useAuth();
  const session = useSyncExternalStore(subscribeAuthSession, getAuthSessionId);
  const allowed = authStatusVerified && (!authEnabled || user !== null) && hasPermission('external_links:read');
  if (loading) return <LinkLoading />;
  if (!allowed || !id) return <LinkNotFound />;
  // Only proven same-login renewal preserves the document, never an explicit
  // re-login, different account, or unknown/synthetic identity's new credentials.
  const identity = authEnabled && preferenceSubject && authenticationEpoch !== null
    ? [preferenceSubject, authenticationEpoch] : [authEnabled ? 'session' : 'appliance', session];
  const scope = JSON.stringify([id, identity]);
  return <RegisteredLink key={scope} id={id} scope={scope} session={session} />;
}

function RegisteredLink({ id, scope, session }: { id: string; scope: string; session: number }) {
  const { data: link, isPending, isFetchedAfterMount, isPlaceholderData, error } = useQuery({
    queryKey: ['external-link', id, scope, session],
    queryFn: () => api.getExternalLink(Number(id)),
    // A permission regrant must verify the registered URL again, not resurrect
    // the previous mount's cached link. Existing active queries can revalidate.
    // Keep the same verified login's document visible during renewal, without
    // granting its old registration any authority in the new credential session.
    placeholderData: keepPreviousData,
    gcTime: 0,
    refetchOnMount: 'always',
  });
  if (error) return <LinkNotFound />;
  if (isPending) return <LinkLoading />;
  if (!link || link.id !== Number(id)) return <LinkNotFound />;
  const authorizedSession = !isPlaceholderData && isFetchedAfterMount ? session : null;
  return <SidebarAppFrame key={link.url} link={link} session={authorizedSession} />;
}

function LinkLoading() {
  return <div className="flex items-center justify-center h-full">
    <Loader2 className="w-8 h-8 text-bambu-green animate-spin" />
  </div>;
}

function LinkNotFound() {
  const { t } = useTranslation();
  return <div className="flex flex-col items-center justify-center h-full gap-4 text-bambu-gray">
    <AlertTriangle className="w-12 h-12" />
    <p>{t('common.linkNotFound')}</p>
  </div>;
}
