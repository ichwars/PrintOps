import { useId, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight, FolderTree } from 'lucide-react';

interface ProjectGroupProps {
  name: string;
  color: string | null;
  visibleCount: number;
  totalCount: number;
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}

export function ProjectGroup({ name, color, visibleCount, totalCount, expanded, onToggle, children }: ProjectGroupProps) {
  const { t } = useTranslation();
  const regionId = useId();
  const Chevron = expanded ? ChevronDown : ChevronRight;
  return (
    <div className="ml-4 md:ml-8 pl-4 md:pl-6 border-l-2 rounded-l space-y-4" style={{ borderColor: color || '#6b7280' }}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={regionId}
        aria-label={t(expanded ? 'projects.collapseSubProjects' : 'projects.expandSubProjects', { name })}
        className="min-h-[44px] w-full flex flex-wrap items-center gap-2 text-left text-bambu-gray hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-bambu-green rounded px-2 py-2"
      >
        <Chevron className="w-4 h-4 shrink-0" aria-hidden="true" />
        <FolderTree className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
        <span className="min-w-0 flex-1 whitespace-normal">
          <span className="block text-xs uppercase tracking-wide break-words">{t('projects.subProjectsOf', { name })}</span>
          <span className="block text-xs">{t('projects.matchingSubProjects', { visible: visibleCount, total: totalCount })}</span>
        </span>
      </button>
      <div id={regionId} hidden={!expanded}>
        {expanded && <div className="grid grid-cols-1 md:grid-cols-2 gap-8">{children}</div>}
      </div>
    </div>
  );
}
