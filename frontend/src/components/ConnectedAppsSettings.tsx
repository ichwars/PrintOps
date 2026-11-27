import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link2 } from 'lucide-react';
import { connectedAppsApi } from '../api/client/connected-apps';
import type { ConnectedApp, ConnectedAppSecret } from '../api/client/connected-apps';
import { useAuth } from '../contexts/AuthContext';
import { Button } from './Button';
import { TextField } from './ui/TextField';
import { SettingsDashboardCard } from './settings/SettingsDashboardCard';
import { dashboardStyles } from './dashboardStyles';

export function ConnectedAppsSettings() {
  const { t } = useTranslation();
  const { authEnabled, hasPermission, isAdmin } = useAuth();
  const allowed = authEnabled && isAdmin && hasPermission('settings:update');
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [callback, setCallback] = useState('');
  const [editing, setEditing] = useState<number | null>(null);
  const [secret, setSecret] = useState<ConnectedAppSecret | null>(null);
  const [confirm, setConfirm] = useState<{ app: ConnectedApp; action: 'rotate' | 'remove' } | null>(null);
  const [copyStatus, setCopyStatus] = useState('');
  const apps = useQuery({ queryKey: ['connected-apps'], queryFn: connectedAppsApi.list, enabled: allowed });
  const mutation = useMutation({ mutationFn: async (operation: () => Promise<unknown>) => operation(),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['connected-apps'] }); setConfirm(null); } });
  if (!hasPermission('settings:update') || (authEnabled && !isAdmin)) return null;
  const save = () => mutation.mutate(async () => {
    if (editing === null) { setSecret(await connectedAppsApi.create({ name, redirect_uri: callback })); setCopyStatus(''); }
    else await connectedAppsApi.update(editing, { name, redirect_uri: callback });
    setName(''); setCallback(''); setEditing(null);
  });
  const copy = async () => {
    try { await navigator.clipboard.writeText(secret!.client_secret); setCopyStatus(t('connectedApps.copied')); }
    catch { setCopyStatus(t('connectedApps.copyFailed')); }
  };
  return <SettingsDashboardCard id="card-connected-apps" title={t('connectedApps.title')} icon={Link2}>
    <p>{t('connectedApps.description')}</p>
    {!authEnabled ? <p>{t('connectedApps.authDisabled')}</p> : <>
      {(apps.isError || mutation.isError) && <p role="alert" className="text-red-700 dark:text-red-400">{t('connectedApps.requestFailed')}</p>}
      {secret && <div className="rounded-lg border border-bambu-green p-4 space-y-3" role="region" aria-label={t('connectedApps.credentials')}>
        <h3 className={dashboardStyles.cardTitle}>{t('connectedApps.credentials')}</h3>
        <p>{t('connectedApps.secretOnce')}</p>
        <TextField label={t('connectedApps.clientId')} className="font-mono text-sm" readOnly value={secret.client_id} />
        <TextField label={t('connectedApps.clientSecret')} className="font-mono text-sm" readOnly value={secret.client_secret} />
        <div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={() => void copy()}>{t('connectedApps.copySecret')}</Button>
          <Button variant="secondary" onClick={() => setSecret(null)}>{t('common.close')}</Button></div>
        <p role="status" className="text-sm">{copyStatus}</p>
      </div>}
      <form className="space-y-3" onSubmit={event => { event.preventDefault(); save(); }}>
        <TextField label={t('connectedApps.name')} required maxLength={100} className="text-sm" value={name} onChange={e => setName(e.target.value)} />
        <TextField label={t('connectedApps.callback')} required type="url" maxLength={500} className="font-mono text-sm" value={callback} onChange={e => setCallback(e.target.value)} />
        <div className="flex flex-wrap gap-2"><Button type="submit" disabled={mutation.isPending}>{editing === null ? t('connectedApps.register') : t('common.save')}</Button>
          {editing !== null && <Button type="button" variant="secondary" onClick={() => { setEditing(null); setName(''); setCallback(''); }}>{t('common.cancel')}</Button>}</div>
      </form>
      {apps.isPending ? <p>{t('common.loading')}</p> : apps.data?.length === 0 ? <p className="rounded-lg border border-bambu-dark-tertiary px-3 py-2">{t('connectedApps.empty')}</p> :
        <ul className="divide-y divide-bambu-dark-tertiary rounded-lg border border-bambu-dark-tertiary">{apps.data?.map(app => <li key={app.id} className="min-w-0 space-y-2 p-3">
          <div className="flex flex-wrap justify-between gap-2"><strong className="min-w-0 wrap-break-word font-medium text-white">{app.name}</strong><span>{app.enabled ? t('connectedApps.enabled') : t('connectedApps.disabled')}</span></div>
          <p className="wrap-anywhere font-mono text-xs">{app.redirect_uri}</p><p className="wrap-anywhere text-xs">{t('connectedApps.clientId')}: <code>{app.client_id}</code></p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" disabled={mutation.isPending} onClick={() => { setEditing(app.id); setName(app.name); setCallback(app.redirect_uri); }}>{t('common.edit')}</Button>
            <Button size="sm" variant="secondary" disabled={mutation.isPending} onClick={() => mutation.mutate(() => connectedAppsApi.update(app.id, { enabled: !app.enabled }))}>{app.enabled ? t('connectedApps.disable') : t('connectedApps.enable')}</Button>
            <Button size="sm" variant="secondary" disabled={mutation.isPending} onClick={() => setConfirm({ app, action: 'rotate' })}>{t('connectedApps.rotate')}</Button>
            <Button size="sm" variant="secondary" disabled={mutation.isPending} onClick={() => setConfirm({ app, action: 'remove' })}>{t('common.delete')}</Button>
          </div>
        </li>)}</ul>}
      {confirm && <div className="rounded-lg border border-amber-500 p-3 space-y-3" role="region" aria-label={t('connectedApps.confirmTitle')}>
        <p>{t(confirm.action === 'rotate' ? 'connectedApps.confirmRotate' : 'connectedApps.confirmRemove', { app: confirm.app.name })}</p>
        <div className="flex gap-2"><Button disabled={mutation.isPending} onClick={() => mutation.mutate(async () => {
          if (confirm.action === 'rotate') { setSecret(await connectedAppsApi.rotate(confirm.app.id)); setCopyStatus(''); }
          else { await connectedAppsApi.remove(confirm.app.id); if (secret?.id === confirm.app.id) setSecret(null); }
        })}>{t('common.confirm')}</Button><Button variant="secondary" disabled={mutation.isPending} onClick={() => setConfirm(null)}>{t('common.cancel')}</Button></div>
      </div>}
    </>}
  </SettingsDashboardCard>;
}
