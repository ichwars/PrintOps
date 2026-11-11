import { useId, useLayoutEffect, useRef, useState } from 'react';
import { Tag, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { LibraryTag } from '../api/client';
import { TextField } from './ui';

const COLLAPSED_HEIGHT = 52;
const SEARCH_THRESHOLD = 12;

interface Props {
  tags: LibraryTag[];
  selectedIds: number[];
  onToggle: (id: number) => void;
  onClear: () => void;
}

function TagChip({ tag, selected, onToggle }: {
  tag: LibraryTag; selected: boolean; onToggle: (id: number) => void;
}) {
  return <button type="button" aria-pressed={selected} title={tag.name} onClick={() => onToggle(tag.id)}
    className={`inline-flex h-6 max-w-full items-center gap-1 rounded-full border px-2 text-xs transition-colors ${
      selected
        ? 'border-bambu-green/40 bg-bambu-green/20 text-bambu-green hover:bg-bambu-green/30'
        : 'border-bambu-dark-tertiary bg-bambu-dark text-bambu-gray hover:border-bambu-green/40 hover:text-white'
    }`}>
    <Tag className="h-3 w-3 shrink-0" />
    <span className="truncate">{tag.name}</span>
    {selected && <X className="h-3 w-3 shrink-0" />}
  </button>;
}

export function LibraryTagFilterRail({ tags, selectedIds, onToggle, onClear }: Props) {
  const { t } = useTranslation();
  const listId = useId();
  const viewport = useRef<HTMLDivElement>(null);
  const grid = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [overflow, setOverflow] = useState(false);
  const tagsById = new Map(tags.map(tag => [tag.id, tag]));
  const selected = new Set(selectedIds);
  const searchable = tags.length >= SEARCH_THRESHOLD;
  const needle = searchable ? query.trim().toLocaleLowerCase() : '';
  const remaining = tags.filter(tag => !selected.has(tag.id) && tag.name.toLocaleLowerCase().includes(needle));

  useLayoutEffect(() => {
    const node = grid.current;
    if (!node) return;
    const measure = () => setOverflow(node.scrollHeight > COLLAPSED_HEIGHT + 1);
    measure();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure);
      return () => window.removeEventListener('resize', measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [remaining.length]);

  if (!tags.length) return null;
  return <div className="mb-3 min-w-0 space-y-2 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary p-2 sm:p-3">
    <div className="flex flex-wrap items-center gap-2">
      <span className="shrink-0 text-xs font-medium text-bambu-gray">{t('fileManager.tags.filterLabel')}</span>
      {selectedIds.map(id => {
        const tag = tagsById.get(id);
        return tag && <TagChip key={tag.id} tag={tag} selected onToggle={onToggle} />;
      })}
      {searchable && <div className="w-full sm:w-44">
        <TextField type="search" aria-label={t('fileManager.tags.searchTags')}
          placeholder={t('fileManager.tags.searchTags')} value={query} className="text-xs"
          onChange={event => { setQuery(event.target.value); setExpanded(false); }} />
      </div>}
      {selectedIds.length > 0 && <button type="button" onClick={onClear}
        className="ml-auto shrink-0 text-xs text-bambu-gray hover:text-white">
        {t('fileManager.tags.clearAll')}
      </button>}
    </div>
    {remaining.length > 0 && <div id={listId} ref={viewport}
      className={expanded ? 'max-h-48 overflow-y-auto' : 'overflow-hidden'}
      style={expanded ? undefined : { maxHeight: COLLAPSED_HEIGHT }}
      onFocusCapture={event => {
        const button = event.target.closest('button');
        if (!expanded && button && button.offsetTop + button.offsetHeight > COLLAPSED_HEIGHT) setExpanded(true);
      }}>
      <div ref={grid} className="relative flex flex-wrap gap-1">
        {remaining.map(tag => <TagChip key={tag.id} tag={tag} selected={false} onToggle={onToggle} />)}
      </div>
    </div>}
    {needle && remaining.length === 0 && <p className="text-xs text-bambu-gray" role="status">
      {t('fileManager.tags.noTagsMatch')}
    </p>}
    {remaining.length > 0 && overflow && <button type="button" aria-expanded={expanded} aria-controls={listId}
      className="text-xs text-bambu-green hover:underline" onClick={() => {
        if (viewport.current) viewport.current.scrollTop = 0;
        setExpanded(previous => !previous);
      }}>
      {expanded ? t('fileManager.tags.showFewerTags') : t('fileManager.tags.showAllTags', { count: remaining.length })}
    </button>}
  </div>;
}
