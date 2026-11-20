import { useState } from 'react';
import { Loader2, FolderSymlink } from 'lucide-react';
import type { ExternalFolderCreate } from '../api/client';
import { Button } from '../components/Button';
import { Checkbox, TextField } from '../components/ui';

type TFunction = (key: string, options?: Record<string, unknown>) => string;

// External Folder Modal
interface ExternalFolderModalProps {
  onClose: () => void;
  onSave: (data: ExternalFolderCreate) => void;
  isLoading: boolean;
  t: TFunction;
}

export function ExternalFolderModal({ onClose, onSave, isLoading, t }: ExternalFolderModalProps) {
  const [name, setName] = useState('');
  const [path, setPath] = useState('');
  const [readonly, setReadonly] = useState(true);
  const [showHidden, setShowHidden] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      name: name.trim(),
      external_path: path.trim(),
      readonly,
      show_hidden: showHidden,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-bambu-dark-secondary rounded-lg w-full max-w-md border border-bambu-dark-tertiary">
        <div className="p-4 border-b border-bambu-dark-tertiary">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <FolderSymlink className="w-5 h-5 text-bambu-green" />
            {t('fileManager.linkExternalFolder')}
          </h2>
          <p className="text-sm text-bambu-gray mt-1">{t('fileManager.linkExternalFolderDescription')}</p>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-white mb-1">
              {t('fileManager.folderName')}
            </label>
            <TextField
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-bambu-dark border border-bambu-dark-tertiary rounded px-3 py-2 text-white placeholder-bambu-gray focus:outline-none focus:border-bambu-green"
              placeholder={t('fileManager.externalFolderNamePlaceholder')}
              autoFocus
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-white mb-1">
              {t('fileManager.externalPath')}
            </label>
            <TextField
              type="text"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              className="w-full bg-bambu-dark border border-bambu-dark-tertiary rounded px-3 py-2 text-white placeholder-bambu-gray focus:outline-none focus:border-bambu-green font-mono text-sm"
              placeholder="/mnt/nas/3d-prints"
              required
            />
            <p className="text-xs text-bambu-gray mt-1">{t('fileManager.externalPathHelp')}</p>
          </div>
          <div className="space-y-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <Checkbox
                checked={readonly}
                onChange={(e) => setReadonly(e.target.checked)}
              />
              <span className="text-sm text-white">{t('fileManager.readOnly')}</span>
              <span className="text-xs text-bambu-gray">({t('fileManager.readOnlyHelp')})</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <Checkbox
                checked={showHidden}
                onChange={(e) => setShowHidden(e.target.checked)}
              />
              <span className="text-sm text-white">{t('fileManager.showHiddenFiles')}</span>
            </label>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={!name.trim() || !path.trim() || isLoading}>
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : t('fileManager.linkFolder')}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
