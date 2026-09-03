import { useCallback, useRef, useState } from 'react';
import { KeyRound } from 'lucide-react';
import type { BusinessProfileOption } from '../../../api/client';
import type { LexwareConnection } from '../../../api/client/lexware';
import { Modal } from '../../ui';
import { LexwareConnectionForm } from './LexwareConnectionForm';
import { useLexwareConnectionMessages } from './lexwareConnectionMessages';

interface Props {
  profiles: Pick<BusinessProfileOption, 'id' | 'name'>[];
  connection?: LexwareConnection;
  onClose: () => void;
  onSaved: () => Promise<unknown>;
}

export function LexwareConnectionDialog({ profiles, connection, onClose, onSaved }: Props) {
  const copy = useLexwareConnectionMessages();
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const onBusyChange = useCallback((pending: boolean) => {
    busyRef.current = pending;
    setBusy(pending);
  }, []);
  // Modal's closeDisabled only disables its X; also guard Escape and the backdrop.
  const close = () => { if (!busyRef.current) onClose(); };

  return (
    <Modal open onClose={close} closeDisabled={busy} closeLabel={copy.close} className="max-w-xl"
      title={<span className="flex items-center gap-2"><KeyRound className="h-5 w-5 text-bambu-green" aria-hidden="true" />
        {connection ? copy.manageKey : copy.setup}</span>}
      description={connection ? copy.keyHelp : copy.setupHelp}>
      <LexwareConnectionForm profiles={profiles} connection={connection} onBusyChange={onBusyChange} onCancel={close}
        onSaved={async () => {
          // A failed invalidation must leave the dialog open with its sanitized error.
          await onSaved();
          onClose();
        }} />
    </Modal>
  );
}
