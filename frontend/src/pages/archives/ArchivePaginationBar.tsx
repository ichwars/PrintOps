import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';
import { LegacySelect } from '../../components/ui';

/* Pagination bar for archives grid/list views */
export function ArchivePaginationBar({
  pageIndex, pageSize, totalRows, totalPages, onPageChange, onPageSizeChange, t,
}: {
  pageIndex: number;
  pageSize: number;
  totalRows: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  t: (key: string) => string;
}) {
  const isShowAll = pageSize === -1;
  if (totalPages <= 1 && !isShowAll) return null;
  const effectiveSize = isShowAll ? totalRows || 1 : pageSize;
  return (
    <div className="flex items-center justify-between pt-2 text-sm">
      <span className="text-bambu-gray">
        {isShowAll
          ? `${totalRows} ${t('archives.prints')}`
          : <>{t('archives.pagination.showing')} {pageIndex * effectiveSize + 1} {t('archives.pagination.to')}{' '}
              {Math.min((pageIndex + 1) * effectiveSize, totalRows)}{' '}
              {t('archives.pagination.of')} {totalRows} {t('archives.prints')}</>
        }
      </span>
      <div className="flex items-center gap-2">
        <span className="text-bambu-gray">{t('archives.pagination.show')}</span>
        <LegacySelect
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          className="px-2 py-1 bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded text-white text-sm focus:outline-none focus:border-bambu-green"
        >
          {[25, 50, 100, 200].map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
          <option value={-1}>{t('archives.pagination.all')}</option>
        </LegacySelect>
        {!isShowAll && (
          <>
            <button
              onClick={() => onPageChange(0)}
              disabled={pageIndex === 0}
              className="p-1.5 rounded text-bambu-gray hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronsLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => onPageChange(Math.max(0, pageIndex - 1))}
              disabled={pageIndex === 0}
              className="p-1.5 rounded text-bambu-gray hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-bambu-gray px-2 whitespace-nowrap">
              {t('archives.pagination.page')} {pageIndex + 1} {t('archives.pagination.of')} {totalPages}
            </span>
            <button
              onClick={() => onPageChange(Math.min(totalPages - 1, pageIndex + 1))}
              disabled={pageIndex >= totalPages - 1}
              className="p-1.5 rounded text-bambu-gray hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
            <button
              onClick={() => onPageChange(totalPages - 1)}
              disabled={pageIndex >= totalPages - 1}
              className="p-1.5 rounded text-bambu-gray hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronsRight className="w-4 h-4" />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
