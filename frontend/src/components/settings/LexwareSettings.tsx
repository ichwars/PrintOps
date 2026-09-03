import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, ShieldCheck, Unplug } from 'lucide-react';
import { api } from '../../api/client';
import { lexwareApi } from '../../api/client/lexware';
import { useAuth } from '../../contexts/AuthContext';
import { Button, Select } from '../ui';
import { LexwareConnectionDialog } from './lexware/LexwareConnectionDialog';
import { LexwareConnectionCard } from './lexware/LexwareConnectionCard';
import { LexwareResources } from './lexware/LexwareResources';
import { lexwareError, useLexwareMessages } from './lexware/lexwareMessages';

export function LexwareSettings() {
  const { hasPermission, loading } = useAuth();
  const { text } = useLexwareMessages();
  const client = useQueryClient();
  const [connectionId, setConnectionId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const canManage = hasPermission('accounting_integrations:manage');
  const fullProfiles = hasPermission('order_settings:read');
  const canReadProfiles = canManage;
  const connections = useQuery({
    queryKey: ['lexware', 'connections'], queryFn: lexwareApi.connections,
    enabled: !loading && canManage, retry: false,
    // No hidden-tab or focus-triggered polling; one local status request per five seconds while active.
    refetchInterval: (query) => query.state.status !== 'error' && query.state.data?.some((connection) => connection.connected && connection.enabled) ? 5000 : false,
    refetchIntervalInBackground: false, refetchOnWindowFocus: false,
  });
  const profiles = useQuery({
    queryKey: fullProfiles ? ['business-profiles', false] : ['business-profile-options'],
    queryFn: () => fullProfiles ? api.getBusinessProfiles() : api.getBusinessProfileOptions(),
    enabled: !loading && canManage && canReadProfiles, retry: false,
  });
  const availableProfiles = profiles.data?.filter((profile) => profile.is_active && !connections.data?.some((connection) => connection.business_profile_id === profile.id)) ?? [];
  const selected = connections.data?.find((connection) => connection.id === connectionId) ?? connections.data?.[0];
  const profileName = (id: number) => profiles.data?.find((profile) => profile.id === id)?.name ?? `${text.profile} #${id}`;

  if (loading) return <p role="status">{text.loading}</p>;
  if (!canManage) return <p role="alert">{text.permission}</p>;

  return (
    <div className="min-w-0 space-y-6 text-white">
      {connections.isPending && <p role="status">{text.loading}</p>}
      {connections.isError && <div role="alert"><p>{lexwareError(connections.error, text)}</p><Button variant="secondary" onClick={() => void connections.refetch()}>{text.retry}</Button></div>}
      {!canReadProfiles && <p role="alert">{text.profilePermission}</p>}
      {canReadProfiles && profiles.isPending && <p role="status">{text.loading}</p>}
      {profiles.isError && <div role="alert"><p>{lexwareError(profiles.error, text)}</p><Button variant="secondary" onClick={() => void profiles.refetch()}>{text.retry}</Button></div>}
      {profiles.isSuccess && profiles.data.length === 0 && <p>{text.emptyProfiles}</p>}
      {connections.isSuccess && !selected && <section className="space-y-4 rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary/40 px-6 py-8">
        <Unplug className="h-8 w-8 text-bambu-green" aria-hidden />
        <h2 className="text-lg font-semibold">{text.noConnections}</h2>
        <p className="max-w-2xl text-sm leading-relaxed text-bambu-gray">{text.intro}</p>
        {availableProfiles.length > 0 && <Button onClick={() => setCreating(true)}><Plus className="h-4 w-4" aria-hidden />{text.setupConnection}</Button>}
        <p className="flex items-center gap-2 text-xs text-bambu-gray"><ShieldCheck className="h-4 w-4" aria-hidden />{text.readonly}</p>
      </section>}
      {selected && <>
        {((connections.data?.length ?? 0) > 1 || availableProfiles.length > 0) && <div className="flex flex-wrap items-end justify-between gap-3">
          {(connections.data?.length ?? 0) > 1 && <div className="w-full max-w-lg"><Select label={text.connectedProfiles} value={selected.id} onValueChange={setConnectionId}
            options={(connections.data ?? []).map((connection) => ({ value: connection.id, label: `${profileName(connection.business_profile_id)} — ${connection.company_name}` }))} /></div>}
          {availableProfiles.length > 0 && <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setCreating(true)}><Plus className="h-4 w-4" aria-hidden />{text.setupConnection}</Button>}
        </div>}
        <LexwareConnectionCard key={`connection-${selected.id}`} connection={selected} profileName={profileName(selected.business_profile_id)} />
        <LexwareResources key={`resources-${selected.id}`} connection={selected} />
      </>}
      {creating && <LexwareConnectionDialog profiles={availableProfiles} onClose={() => setCreating(false)}
        onSaved={async () => { await client.invalidateQueries({ queryKey: ['lexware'] }); setCreating(false); }} />}
    </div>
  );
}
