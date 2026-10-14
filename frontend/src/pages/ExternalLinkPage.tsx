import { useSyncExternalStore } from 'react';
import { useParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { Loader2, AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api, getAuthSessionId, subscribeAuthSession } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { SidebarAppFrame } from '../components/SidebarAppFrame';

export function ExternalLinkPage() {
  const { id } = useParams<{ id: string }>();
  const { authEnabled, authStatusVerified, loading, user, preferenceSubject, hasPermission } = useAuth();
  const session = useSyncExternalStore(subscribeAuthSession, getAuthSessionId);
  const allowed = authStatusVerified && (!authEnabled || user !== null) && hasPermission('external_links:read');
  if (loading) return <LinkLoading />;
  if (!allowed || !id) return <LinkNotFound />;
  // Reusable numeric account IDs cannot identify a registration's authority.
  // Remount on credential changes too, including synthetic API-key sessions.
  const scope = JSON.stringify([id, session, authEnabled ? preferenceSubject : 'appliance']);
  return <RegisteredLink key={scope} id={id} scope={scope} session={session} />;
}

function RegisteredLink({ id, scope, session }: { id: string; scope: string; session: number }) {
  const { data: link, isPending, isFetchedAfterMount, error } = useQuery({
    queryKey: ['external-link', id, scope],
    queryFn: () => api.getExternalLink(Number(id)),
    // A permission regrant must verify the registered URL again, not resurrect
    // the previous mount's cached link. Existing active queries can revalidate.
    gcTime: 0,
    refetchOnMount: 'always',
  });
  if (error) return <LinkNotFound />;
  if (isPending || !isFetchedAfterMount) return <LinkLoading />;
  if (!link || link.id !== Number(id)) return <LinkNotFound />;
  return <SidebarAppFrame key={link.url} link={link} session={session} />;
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
