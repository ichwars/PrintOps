import { Film } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export function ArchiveVideosButton({
  count, onOpen, compact = false,
}: {
  count: number;
  onOpen: () => void;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  if (count === 0) return null;
  const label = count > 1 ? t('archives.card.viewTimelapses', { count }) : t('archives.card.viewTimelapse');
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      className={compact
        ? 'flex items-center gap-1 text-bambu-green'
        : 'absolute bottom-2 right-12 p-1.5 rounded bg-black/60 hover:bg-black/80 transition-colors text-bambu-green'}
      onClick={(event) => {
        event.stopPropagation();
        onOpen();
      }}
    >
      <Film className={compact ? 'w-3.5 h-3.5 flex-shrink-0' : 'w-4 h-4'} />
      {count > 1 && <span className={compact ? 'text-xs' : 'absolute -top-1 -right-1 min-w-4 px-0.5 h-4 bg-bambu-green rounded-full text-[10px] text-black'}>{count}</span>}
    </button>
  );
}
