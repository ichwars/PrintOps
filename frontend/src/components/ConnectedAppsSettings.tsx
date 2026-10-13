import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link2 } from 'lucide-react';
import { connectedAppsApi } from '../api/client/connected-apps';
import type { ConnectedApp, ConnectedAppSecret } from '../api/client/connected-apps';
import { useAuth } from '../contexts/AuthContext';
import { Button } from './Button';
import { TextField } from './ui/TextField';

const inputClass = 'w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-2 text-white';

export function ConnectedAppsSettings() {
  const { t } = useTranslation();
  const { authEnabled, hasPermission } = useAuth();
  const allowed = authEnabled && hasPermission('settings:update');
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
  if (!hasPermission('settings:update')) return null;
  const save = () => mutation.mutate(async () => {
    if (editing === null) { setSecret(await connectedAppsApi.create({ name, redirect_uri: callback })); setCopyStatus(''); }
    else await connectedAppsApi.update(editing, { name, redirect_uri: callback });
    setName(''); setCallback(''); setEditing(null);
  });
  const copy = async () => {
    try { await navigator.clipboard.writeText(secret!.client_secret); setCopyStatus(t('connectedApps.copied')); }
    catch { setCopyStatus(t('connectedApps.copyFailed')); }
  };
  return <section id="card-connected-apps" className="rounded-xl bg-bambu-dark-secondary border border-bambu-dark-tertiary p-5 space-y-4">
    <h2 className="text-lg font-semibold text-white flex gap-2 items-center"><Link2 className="text-bambu-green" aria-hidden />{t('connectedApps.title')}</h2>
    <p className="text-sm text-bambu-gray">{t('connectedApps.description')}</p>
    {!authEnabled ? <p>{t('connectedApps.authDisabled')}</p> : <>
      {(apps.isError || mutation.isError) && <p role="alert" className="text-red-400">{t('connectedApps.requestFailed')}</p>}
      {secret && <div className="rounded-lg border border-bambu-green p-4 space-y-3" role="region" aria-label={t('connectedApps.credentials')}>
        <h3 className="font-semibold">{t('connectedApps.credentials')}</h3>
        <p className="text-sm">{t('connectedApps.secretOnce')}</p>
        <label className="block text-sm">{t('connectedApps.clientId')}<TextField className={inputClass} readOnly value={secret.client_id} /></label>
        <label className="block text-sm">{t('connectedApps.clientSecret')}<TextField className={inputClass} readOnly value={secret.client_secret} /></label>
        <div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={() => void copy()}>{t('connectedApps.copySecret')}</Button>
          <Button variant="secondary" onClick={() => setSecret(null)}>{t('common.close')}</Button></div>
        <p role="status" className="text-sm">{copyStatus}</p>
      </div>}
      <form className="space-y-3" onSubmit={event => { event.preventDefault(); save(); }}>
        <label className="block text-sm">{t('connectedApps.name')}<TextField required maxLength={100} className={inputClass} value={name} onChange={e => setName(e.target.value)} /></label>
        <label className="block text-sm">{t('connectedApps.callback')}<TextField required type="url" maxLength={500} className={inputClass} value={callback} onChange={e => setCallback(e.target.value)} /></label>
        <div className="flex flex-wrap gap-2"><Button type="submit" disabled={mutation.isPending}>{editing === null ? t('connectedApps.register') : t('common.save')}</Button>
          {editing !== null && <Button type="button" variant="secondary" onClick={() => { setEditing(null); setName(''); setCallback(''); }}>{t('common.cancel')}</Button>}</div>
      </form>
      {apps.isPending ? <p>{t('common.loading')}</p> : apps.data?.length === 0 ? <p className="text-sm text-bambu-gray">{t('connectedApps.empty')}</p> :
        <ul className="space-y-3">{apps.data?.map(app => <li key={app.id} className="rounded-lg border border-bambu-dark-tertiary p-3 space-y-2">
          <div className="flex justify-between gap-2"><strong className="break-words min-w-0">{app.name}</strong><span className="text-sm text-bambu-gray">{app.enabled ? t('connectedApps.enabled') : t('connectedApps.disabled')}</span></div>
          <p className="text-sm break-all">{app.redirect_uri}</p><p className="text-xs text-bambu-gray break-all">{t('connectedApps.clientId')}: {app.client_id}</p>
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
  </section>;
}
