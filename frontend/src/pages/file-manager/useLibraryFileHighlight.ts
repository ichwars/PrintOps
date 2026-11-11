import { useEffect, useEffectEvent, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api, type LibraryFile, type LibraryFileListItem } from '../../api/client';
import { useToast } from '../../contexts/ToastContext';

interface Options {
  value: string | null;
  folderId: number | null;
  visibleFiles: LibraryFileListItem[];
  filesUpdatedAt: number;
  filesError: boolean;
  reveal: (file: LibraryFile) => void;
}

export function useLibraryFileHighlight({ value, folderId, visibleFiles, filesUpdatedAt, filesError, reveal }: Options) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<{ id: number; folder: number | null; since: number } | null>(null);
  const [highlight, setHighlight] = useState<number | null>(null);
  const currentFolder = useEffectEvent(() => folderId);
  const onReveal = useEffectEvent((file: LibraryFile) => reveal(file));
  const notFound = useEffectEvent(() => showToast(t('fileManager.highlightedFileNotFound'), 'warning'));

  useEffect(() => {
    if (!value || !/^\d+$/.test(value)) return;
    const id = Number(value);
    if (!Number.isSafeInteger(id) || id <= 0) return;
    let cancelled = false;
    const initialFolder = currentFolder();
    setPending(null);
    setHighlight(null);
    queryClient.fetchQuery({ queryKey: ['library-file-highlight', id], queryFn: () => api.getLibraryFile(id), retry: false })
      .then(file => {
        if (cancelled || currentFolder() !== initialFolder) return;
        const since = Date.now();
        onReveal(file);
        setPending({ id: file.id, folder: file.folder_id, since });
        void queryClient.invalidateQueries({ queryKey: ['library-files'] });
      }, () => { if (!cancelled) notFound(); });
    return () => { cancelled = true; };
  }, [queryClient, value]);

  useEffect(() => {
    if (!pending) return;
    if (folderId !== pending.folder) {
      setPending(null);
      return;
    }
    if (filesUpdatedAt < pending.since && !filesError) return;
    setPending(null);
    if (visibleFiles.some(file => file.id === pending.id)) setHighlight(pending.id);
    else notFound();
  }, [pending, folderId, filesUpdatedAt, filesError, visibleFiles]);

  useEffect(() => {
    if (highlight === null) return;
    const frame = requestAnimationFrame(() => {
      document.querySelector(`[data-library-file-id="${highlight}"]`)?.scrollIntoView?.({ block: 'center' });
    });
    const timer = setTimeout(() => setHighlight(null), 5000);
    return () => { cancelAnimationFrame(frame); clearTimeout(timer); };
  }, [highlight]);

  return highlight;
}
