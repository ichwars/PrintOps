import { useRef, useState } from 'react';
import { CircleCheck, LockKeyhole } from 'lucide-react';
import type { BusinessProfileOption } from '../../../api/client';
import { lexwareApi, type LexwareConnection, type LexwareOrganization } from '../../../api/client/lexware';
import { useToast } from '../../../contexts/ToastContext';
import { Button, Select, TextField } from '../../ui';
import { lexwareError, useLexwareMessages } from './lexwareMessages';
import { useLexwareConnectionMessages } from './lexwareConnectionMessages';

interface Props {
  profiles: Pick<BusinessProfileOption, 'id' | 'name'>[];
  connection?: LexwareConnection;
  onSaved: () => Promise<unknown>;
  onBusyChange?: (busy: boolean) => void;
  onCancel?: () => void;
}

export function LexwareConnectionForm({ profiles, connection, onSaved, onBusyChange, onCancel }: Props) {
  const { text } = useLexwareMessages();
  const copy = useLexwareConnectionMessages();
  const { showToast } = useToast();
  const [profileId, setProfileId] = useState(connection?.business_profile_id ?? 0);
  const [apiKey, setApiKey] = useState('');
  const [verified, setVerified] = useState<LexwareOrganization | null>(null);
  const [busy, setBusy] = useState<'test' | 'save' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);

  const changeBusy = (operation: 'test' | 'save' | null) => {
    busyRef.current = operation !== null;
    setBusy(operation);
    onBusyChange?.(operation !== null);
  };

  // Keep the key out of react-query's mutation/query caches, URLs and browser storage.
  const test = async () => {
    if (busyRef.current || !profileId || !apiKey.trim()) return;
    setVerified(null);
    setError(null);
    changeBusy('test');
    try {
      const result = await lexwareApi.test(apiKey.trim());
      if (connection && result.organization_id !== connection.organization_id) {
        setError(text.wrongOrganization);
      } else setVerified(result);
    } catch (cause) { setError(lexwareError(cause, text)); }
    finally { changeBusy(null); }
  };

  const save = async () => {
    if (busyRef.current || !verified || !profileId || !apiKey.trim()) return;
    changeBusy('save');
    setError(null);
    try {
      if (connection) await lexwareApi.update(connection.id, { api_key: apiKey.trim(), ...(!connection.connected ? { enabled: true } : {}) });
      else await lexwareApi.create({ business_profile_id: profileId, api_key: apiKey.trim(), organization_id: verified.organization_id });
      setApiKey('');
      setVerified(null);
      showToast(text.saved, 'success');
      try { await onSaved(); }
      catch { setError(copy.savedRefreshFailed); }
    } catch (cause) { setError(lexwareError(cause, text)); }
    finally { changeBusy(null); }
  };

  return (
    <form className="space-y-5" aria-busy={busy !== null} onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <Select label={text.profile} value={profileId} disabled={Boolean(connection) || busy !== null}
        options={[{ value: 0, label: text.selectProfile }, ...profiles.map((profile) => ({ value: profile.id, label: profile.name }))]}
        onValueChange={(id) => { setProfileId(id); setVerified(null); setError(null); }} />
      <TextField type="password" label={text.key} value={apiKey} autoComplete="off" spellCheck={false}
        disabled={busy !== null}
        onValueChange={(value) => { setApiKey(value); setVerified(null); setError(null); }} />
      <div className="flex gap-3 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-3 text-sm">
        <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-bambu-green" aria-hidden="true" />
        <div className="min-w-0"><p className="font-medium text-white">{copy.secure}</p><p className="mt-1 leading-relaxed text-bambu-gray">{text.keyHelp}</p></div>
      </div>
      {connection && <div className="text-sm text-bambu-gray"><p>{text.expectedOrganization}</p>
        <p className="mt-1 break-all text-white">{connection.company_name} · {connection.organization_id}</p></div>}
      {verified && <div role="status" className="flex gap-3 rounded-lg border border-bambu-green/30 bg-bambu-green/5 p-3 text-sm">
        <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-bambu-green" aria-hidden="true" />
        <div className="min-w-0"><p className="font-medium text-bambu-green">{copy.verified}</p>
          <p className="mt-1 break-words text-white">{text.organization}: {verified.company_name}</p>
          <p className="mt-1 break-all text-bambu-gray">{verified.organization_id}</p></div>
      </div>}
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
      <div className="flex flex-wrap items-center gap-2 border-t border-bambu-dark-tertiary pt-4">
        {onCancel && <Button type="button" variant="ghost" className="mr-auto" disabled={busy !== null} onClick={onCancel}>{copy.cancel}</Button>}
        <Button type="button" variant="secondary" disabled={!profileId || !apiKey.trim() || busy !== null}
          loading={busy === 'test'} onClick={() => void test()}>{busy === 'test' ? text.testing : text.test}</Button>
        <Button type="submit" disabled={!verified || !profileId || !apiKey.trim() || busy !== null} loading={busy === 'save'}>{text.save}</Button>
      </div>
    </form>
  );
}
