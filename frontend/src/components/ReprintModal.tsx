import { useTranslation } from 'react-i18next';
import type { Archive, PrintQueueItem } from '../api/client';
import { queueItemDisplayName } from '../utils/queueItemName';
import { PrintModal } from './PrintModal';

type ArchiveSource = Pick<Archive, 'id' | 'filename' | 'print_name' | 'plate_id'>;

export function ArchiveReprintModal({ archive, onClose, projectId }: {
  archive: ArchiveSource; onClose: () => void; projectId?: number;
}) {
  return <PrintModal mode="create" archiveId={archive.id} archiveName={archive.print_name || archive.filename}
    preselectPlateId={archive.plate_id} projectId={projectId} onClose={onClose} />;
}

export function QueueReprintModal({ item, onClose }: { item: PrintQueueItem; onClose: () => void }) {
  const { t } = useTranslation();
  return <PrintModal mode="create" archiveId={item.archive_id ?? undefined} libraryFileId={item.library_file_id ?? undefined}
    archiveName={queueItemDisplayName(item, (n) => t('common.plusNMore', { count: n }))}
    preselectPlateId={item.plate_id} onClose={onClose} />;
}
