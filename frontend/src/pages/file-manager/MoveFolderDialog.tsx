import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '../../components/Button';
import { LegacySelect, Modal } from '../../components/ui';

interface Props {
  name: string;
  allowRoot: boolean;
  destinations: { id: number; path: string }[];
  busy: boolean;
  onMove: (parent: number) => void;
  onClose: () => void;
}

export function MoveFolderDialog({ name, allowRoot, destinations, busy, onMove, onClose }: Props) {
  const { t } = useTranslation();
  const [parent, setParent] = useState('');
  return <Modal open title={t('fileManager.folderMove.title', { name })} closeLabel={t('common.close')}
    onClose={() => { if (!busy) onClose(); }} closeDisabled={busy}>
    <div className="space-y-4">
      <label className="block text-sm text-white">
        {t('fileManager.folderMove.destination')}
        <LegacySelect className="mt-1 w-full" aria-label={t('fileManager.folderMove.destination')}
          value={parent} disabled={busy} onChange={event => setParent(event.target.value)}>
          <option value="">{t('fileManager.folderMove.choose')}</option>
          {allowRoot && <option value="0">{t('fileManager.folderMove.root')}</option>}
          {destinations.map(folder => <option key={folder.id} value={folder.id}>{folder.path}</option>)}
        </LegacySelect>
      </label>
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose} disabled={busy}>{t('common.cancel')}</Button>
        <Button onClick={() => onMove(Number(parent))} disabled={busy || parent === ''}>
          {t('fileManager.folderMove.action')}
        </Button>
      </div>
    </div>
  </Modal>;
}
