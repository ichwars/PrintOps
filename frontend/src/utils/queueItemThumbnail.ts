import { api, type PrintQueueItem } from '../api/client';

type ThumbnailItem = Pick<
  PrintQueueItem, 'archive_id' | 'archive_thumbnail' | 'library_file_id' | 'library_file_thumbnail' | 'plate_id'
>;

export function queueItemThumbnailUrl(item: ThumbnailItem): string | null {
  if (item.archive_id != null && item.archive_thumbnail) {
    return item.plate_id == null
      ? api.getArchiveThumbnail(item.archive_id)
      : api.getArchivePlateThumbnail(item.archive_id, item.plate_id);
  }
  if (item.library_file_id != null && item.library_file_thumbnail) {
    return item.plate_id == null
      ? api.getLibraryFileThumbnailUrl(item.library_file_id)
      : api.getLibraryFilePlateThumbnail(item.library_file_id, item.plate_id);
  }
  return null;
}
