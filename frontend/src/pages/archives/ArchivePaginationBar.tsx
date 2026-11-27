import { TablePagination } from '../../components/ui/TablePagination';

export function ArchivePaginationBar({
  pageIndex, pageSize, totalRows, onPageChange, onPageSizeChange, t,
}: {
  pageIndex: number;
  pageSize: number;
  totalRows: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  t: (key: string) => string;
}) {
  return <TablePagination offset={pageSize === -1 ? 0 : pageIndex * pageSize} pageSize={pageSize} total={totalRows}
    onOffsetChange={offset => onPageChange(offset / pageSize)} onPageSizeChange={onPageSizeChange}
    sizes={[15, 25, 30, 50, 100, 200, -1]} itemLabel={t('archives.prints')} />;
}
