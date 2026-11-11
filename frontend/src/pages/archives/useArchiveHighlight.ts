import { useCallback, useEffect, useRef, useState } from 'react';
import { api, type Archive } from '../../api/client';

export function useArchiveHighlight(
  archives: Archive[] | undefined,
  highlight: string | null,
  setPending: (archiveId: number) => void,
  setHighlighted: (archiveId: number) => void,
  setView: (view: 'grid') => void,
) {
  const [requested, setRequested] = useState<number | null>(null);
  const openedLink = useRef<string | null>(null);
  useEffect(() => {
    if (openedLink.current === highlight) return;
    openedLink.current = highlight;
    const id = Number(highlight);
    if (Number.isSafeInteger(id) && id > 0) {
      setView('grid');
      setRequested(id);
    }
  }, [highlight, setView]);

  useEffect(() => {
    if (!archives || requested === null) return;
    let current = true;
    const show = (id: number) => {
      if (!current) return;
      setPending(id);
      setHighlighted(id);
      setRequested(null);
    };
    if (archives.some(({ id }) => id === requested)) show(requested);
    else void api.getArchive(requested).then(({ id }) => show(id), () => show(requested));
    return () => { current = false; };
  }, [archives, requested, setPending, setHighlighted]);

  return useCallback((archiveId: number) => setRequested(archiveId), []);
}
