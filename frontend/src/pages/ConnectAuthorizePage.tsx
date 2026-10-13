import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';
import { ShieldCheck } from 'lucide-react';
import { connectedAppsApi } from '../api/client/connected-apps';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/Button';

import { connectCallbackUrl } from '../utils/connectCallbackUrl';

export function ConnectAuthorizePage() {
  const { t } = useTranslation();
  const { search } = useLocation();
  const { authEnabled, loading } = useAuth();
  const params = new URLSearchParams(search);
  const clientId = params.get('client_id') ?? '';
  const callback = params.get('redirect_uri') ?? '';
  const challenge = params.get('code_challenge') ?? '';
  const state = params.get('state');
  const valid = !!clientId && !!callback && /^[A-Za-z0-9_-]{43}$/.test(challenge) && params.get('code_challenge_method') === 'S256';
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const info = useQuery({ queryKey: ['connect-consent', clientId, callback],
    queryFn: () => connectedAppsApi.info(clientId, callback), enabled: authEnabled && valid,
    retry: false, staleTime: 0, gcTime: 0 });

  const decide = async (allow: boolean) => {
    if (!info.data || pending) return;
    setPending(true);
    setError('');
    try {
      // Revalidate for denial too: registration might have changed while the screen was open.
      const validated = await connectedAppsApi.info(clientId, callback);
      if (allow) {
        const result = await connectedAppsApi.authorize({ client_id: clientId, redirect_uri: validated.redirect_uri,
          code_challenge: challenge, code_challenge_method: 'S256' });
        window.location.assign(connectCallbackUrl(result.redirect_uri, state, { code: result.code }));
      } else {
        window.location.assign(connectCallbackUrl(validated.redirect_uri, state, { error: 'access_denied' }));
      }
    } catch {
      setError(t('connectedApps.requestFailed'));
      setPending(false);
    }
  };
  return <main className="min-h-screen bg-bambu-dark flex items-center justify-center p-4">
    <section className="w-full max-w-lg rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-6 sm:p-8 space-y-5">
      <div className="flex items-center gap-3 text-bambu-green"><ShieldCheck size={28} aria-hidden /><span className="font-semibold">PrintOps</span></div>
      {loading ? <p>{t('common.loading')}</p> : !authEnabled ? <p role="alert">{t('connectedApps.authDisabled')}</p>
        : !valid || info.isError ? <p role="alert">{t('connectedApps.invalidRequest')}</p>
        : !info.data ? <p>{t('common.loading')}</p> : <>
          <h1 className="text-2xl font-semibold text-white">{t('connectedApps.signInTo', { app: info.data.app_name })}</h1>
          <p>{t('connectedApps.signedInAs', { username: info.data.username })}</p>
          <p className="text-bambu-gray">{t('connectedApps.disclosure')}</p>
          <p className="text-bambu-gray">{t('connectedApps.noApiAccess')}</p>
          <div className="rounded-lg bg-bambu-dark p-3 text-sm break-all"><span className="block text-bambu-gray mb-1">{t('connectedApps.callback')}</span>{info.data.redirect_uri}</div>
          {error && <p role="alert" className="text-red-400">{error}</p>}
          <div className="flex flex-wrap gap-3"><Button onClick={() => void decide(true)} disabled={pending}>{t('connectedApps.allow')}</Button>
            <Button variant="secondary" onClick={() => void decide(false)} disabled={pending}>{t('connectedApps.deny')}</Button></div>
        </>}
    </section>
  </main>;
}
