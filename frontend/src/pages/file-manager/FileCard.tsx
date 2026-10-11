import {
  Box, CalendarClock, Clock, Cog, Download, Eye, FileBox, Image, Info,
  Layers, Pencil, Play, Printer, Tag as TagIcon, Trash2, User,
} from 'lucide-react';
import { api } from '../../api/client';
import type { LibraryFileListItem, Permission } from '../../api/client';
import { ActionMenu } from '../../components/ui/ActionMenu';
import { formatDate, formatDuration } from '../../utils/date';
import { formatFileSize } from '../../utils/file';
import { isDesktopSliceableLibraryFile, isSliceableLibraryFile, isSlicedLibraryFile } from '../../utils/libraryFiles';
import { isUnsliceableCadFilename } from '../../utils/sliceFormats';
import type { SlicerType } from '../../utils/slicer';

type TFunction = (key: string, options?: Record<string, unknown>) => string;

// File Card
interface FileCardProps {
  file: LibraryFileListItem;
  isSelected: boolean;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
  onDownload: (id: number) => void;
  onDetails: (file: LibraryFileListItem) => void;
  onPrint?: (file: LibraryFileListItem) => void;
  onSlice?: (file: LibraryFileListItem) => void;
  onRunPipeline?: (file: LibraryFileListItem) => void;
  useSlicerApi?: boolean;
  onPreviewDocument?: (file: LibraryFileListItem) => void;
  desktopSlicer: SlicerType;
  onPreview3d?: (file: LibraryFileListItem) => void;
  onRename?: (file: LibraryFileListItem) => void;
  onGenerateThumbnail?: (file: LibraryFileListItem) => void;
  onTagClick?: (tagId: number) => void;
  thumbnailVersion?: number;
  hasPermission: (permission: Permission) => boolean;
  canModify: (resource: 'queue' | 'archives' | 'library', action: 'update' | 'delete' | 'reprint', createdById: number | null | undefined) => boolean;
  authEnabled: boolean;
  showModified: boolean;
  t: TFunction;
}

export function FileCard({ file, isSelected, onSelect, onDelete, onDownload, onDetails, onPrint, onSlice, onRunPipeline, useSlicerApi, desktopSlicer, onPreviewDocument, onPreview3d, onRename, onGenerateThumbnail, onTagClick, thumbnailVersion, hasPermission, canModify, authEnabled, showModified, t }: FileCardProps) {
  return (
    <div
      className={`group relative bg-bambu-dark-secondary rounded-lg border transition-all cursor-pointer overflow-hidden ${
        isSelected
          ? 'border-bambu-green ring-1 ring-bambu-green'
          : 'border-bambu-dark-tertiary hover:border-bambu-green/50'
      }`}
      onClick={() => onSelect(file.id)}
    >
      {/* Thumbnail */}
      <div className="aspect-square bg-bambu-dark flex items-center justify-center overflow-hidden">
        {file.thumbnail_path ? (
          <img
            src={`${api.getLibraryFileThumbnailUrl(file.id)}${thumbnailVersion ? ((api.getLibraryFileThumbnailUrl(file.id).includes('?') ? '&' : '?') + `v=${thumbnailVersion}`) : ''}`}
            alt={file.filename}
            className="w-full h-full object-cover"
          />
        ) : (
          <FileBox className="w-12 h-12 text-bambu-gray/30" />
        )}
        {/* File type badge */}
        <div className={`absolute top-2 right-2 text-xs px-1.5 py-0.5 rounded font-medium ${
          file.file_type === '3mf' ? 'bg-bambu-green/90 text-white'
          // Sliced output — share the gcode blue so users see at a glance
          // that the file is already sliced and ready to print (#1543).
          : file.file_type === 'gcode' || file.file_type === 'gcode.3mf' ? 'bg-blue-500/90 text-white'
          : file.file_type === 'stl' ? 'bg-purple-500/90 text-white'
          : 'bg-bambu-gray/90 text-white'
        }`}>
          {file.file_type.toUpperCase()}
        </div>
      </div>

      {/* Info */}
      <div className="p-3">
        <h3 className="text-sm font-medium text-white truncate" title={file.print_name || file.filename}>
          {file.print_name || file.filename}
        </h3>
        <div className="flex items-center gap-3 mt-1 text-xs text-bambu-gray">
          <span>{formatFileSize(file.file_size)}</span>
          {file.print_time_seconds && (
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatDuration(file.print_time_seconds)}
            </span>
          )}
        </div>
        {file.sliced_for_model && (
          <div className="mt-1 text-xs text-bambu-gray flex items-center gap-1">
            <Printer className="w-3 h-3" />
            {file.sliced_for_model}
          </div>
        )}
        {/* Counts the whole group, including members in other folders (#671 /
            #2570) — printing this file will offer all of them. */}
        {(file.variant_count ?? 0) > 1 && (
          <div className="mt-1 text-xs text-bambu-green flex items-center gap-1">
            <Layers className="w-3 h-3" />
            {t('fileManager.variants.badge', { count: file.variant_count })}
          </div>
        )}
        {file.print_count > 0 && (
          <div className="mt-1 text-xs text-bambu-green">
            {t('fileManager.printedCount', { count: file.print_count })}
          </div>
        )}
        {authEnabled && file.created_by_username && (
          <div className="mt-1 text-xs text-bambu-gray flex items-center gap-1">
            <User className="w-3 h-3" />
            {file.created_by_username}
          </div>
        )}
        {/* #2680: last-modified date, toggled from the toolbar. Uses the real
            on-disk mtime when known, else the DB created_at. */}
        {showModified && (
          <div className="mt-1 text-xs text-bambu-gray flex items-center gap-1" title={t('fileManager.lastModified')}>
            <CalendarClock className="w-3 h-3" />
            {formatDate(file.fs_modified_at ?? file.created_at)}
          </div>
        )}
        {(file.tags?.length ?? 0) > 0 && (
          <div className="mt-2 flex flex-wrap gap-1" onClick={(e) => e.stopPropagation()}>
            {file.tags!.map((tg) => (
              <button
                key={tg.id}
                type="button"
                onClick={() => onTagClick?.(tg.id)}
                className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] bg-bambu-green/10 text-bambu-green hover:bg-bambu-green/20 transition-colors max-w-full"
                title={tg.name}
              >
                <TagIcon className="w-2.5 h-2.5 flex-shrink-0" />
                <span className="truncate">{tg.name}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Touch actions stay visible; desktop actions also reveal on focus. */}
      <div className="absolute bottom-2 right-2 transition-opacity can-hover:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 has-[[aria-expanded=true]]:opacity-100" onClick={(e) => e.stopPropagation()}>
        <ActionMenu label={`${t('common.actions')}: ${file.print_name || file.filename}`} className="p-1.5 rounded bg-bambu-dark-secondary/90 hover:bg-bambu-dark-tertiary">
          {(close) => <>
              {onPrint && isSlicedLibraryFile(file) && (
                <button
                  role="menuitem"
                  className={`w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 ${
                    hasPermission('queue:create') ? 'text-bambu-green hover:bg-bambu-dark' : 'text-bambu-gray cursor-not-allowed'
                  }`}
                  onClick={() => { if (hasPermission('queue:create')) { close(); onPrint(file); } }}
                  disabled={!hasPermission('queue:create')}
                  title={!hasPermission('queue:create') ? t('fileManager.noPermissionAddToQueue') : undefined}
                >
                  <Printer className="w-3.5 h-3.5" />
                  {t('common.print')}
                </button>
              )}
              {onSlice && (useSlicerApi ? isSliceableLibraryFile(file) : isDesktopSliceableLibraryFile(file, desktopSlicer)) && (
                <button
                  role="menuitem"
                  className={`w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 ${
                    hasPermission('library:upload') ? 'text-white hover:bg-bambu-dark' : 'text-bambu-gray cursor-not-allowed'
                  }`}
                  onClick={() => { if (hasPermission('library:upload')) { close(); onSlice(file); } }}
                  disabled={!hasPermission('library:upload')}
                  title={!hasPermission('library:upload') ? t('fileManager.noPermissionSlice') : undefined}
                >
                  <Cog className="w-3.5 h-3.5" />
                  {t('slice.action')}
                </button>
              )}
              {useSlicerApi && isUnsliceableCadFilename(file.filename) && (
                <div
                  className="w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 text-bambu-gray cursor-help"
                  title={t('slice.stepUnsupportedHint')}
                >
                  <Cog className="w-3.5 h-3.5" />
                  {t('slice.stepUnsupported')}
                </div>
              )}
              {onRunPipeline && useSlicerApi && isSliceableLibraryFile(file) && (
                <button
                  role="menuitem"
                  className={`w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 ${
                    hasPermission('pipelines:run') ? 'text-white hover:bg-bambu-dark' : 'text-bambu-gray cursor-not-allowed'
                  }`}
                  onClick={() => { if (hasPermission('pipelines:run')) { close(); onRunPipeline(file); } }}
                  disabled={!hasPermission('pipelines:run')}
                  title={!hasPermission('pipelines:run') ? t('library.runWithPipeline.noPermission') : undefined}
                >
                  <Play className="w-3.5 h-3.5" />
                  {t('library.runWithPipeline.actionLabel')}
                </button>
              )}
              {onPreviewDocument && ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'pdf', 'csv', 'xlsx', 'ods'].includes(file.file_type) && (
                <button role="menuitem" disabled={!hasPermission('library:read')}
                  className="w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 text-white hover:bg-bambu-dark disabled:opacity-50"
                  onClick={() => { if (hasPermission('library:read')) { close(); onPreviewDocument(file); } }}>
                  <Eye className="w-3.5 h-3.5" />{t('fileManager.preview.open')}
                </button>
              )}
              {onPreview3d && (file.file_type === '3mf' || file.file_type === 'gcode' || file.file_type === 'stl' || file.file_type === 'gcode.3mf' || file.file_type === 'step' || file.file_type === 'stp') && (
                <button
                  role="menuitem"
                  className={`w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 ${
                    hasPermission('library:read') ? 'text-white hover:bg-bambu-dark' : 'text-bambu-gray cursor-not-allowed'
                  }`}
                  onClick={() => { if (hasPermission('library:read')) { close(); onPreview3d(file); } }}
                  disabled={!hasPermission('library:read')}
                  title={!hasPermission('library:read') ? t("orders.runtimeInterface.youDoNotHavePermissionToPreviewFiles") : undefined}
                >
                  <Box className="w-3.5 h-3.5" />
                  {t("archives.menu.preview3d")}
                </button>
              )}
              <button
                role="menuitem"
                className={`w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 ${
                  hasPermission('library:read') ? 'text-white hover:bg-bambu-dark' : 'text-bambu-gray cursor-not-allowed'
                }`}
                onClick={() => { if (hasPermission('library:read')) { close(); onDownload(file.id); } }}
                disabled={!hasPermission('library:read')}
                title={!hasPermission('library:read') ? t('fileManager.noPermissionDownload') : undefined}
              >
                <Download className="w-3.5 h-3.5" />
                {t('common.download')}
              </button>
              {onRename && (
                <button role="menuitem" title={t('fileManager.details.title')}
                  className="w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 text-white hover:bg-bambu-dark"
                  onClick={() => { close(); onDetails(file); }}>
                  <Info className="w-3.5 h-3.5" />{t('fileManager.details.title')}
                </button>
              )}
              {onRename && (
                <button
                  role="menuitem"
                  className={`w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 ${
                    canModify('library', 'update', file.created_by_id) ? 'text-white hover:bg-bambu-dark' : 'text-bambu-gray cursor-not-allowed'
                  }`}
                  onClick={() => { if (canModify('library', 'update', file.created_by_id)) { close(); onRename(file); } }}
                  disabled={!canModify('library', 'update', file.created_by_id)}
                  title={!canModify('library', 'update', file.created_by_id) ? t('fileManager.noPermissionRenameFile') : undefined}
                >
                  <Pencil className="w-3.5 h-3.5" />
                  {t('common.rename')}
                </button>
              )}
              {onGenerateThumbnail && ['stl', 'pdf'].includes(file.file_type) && (
                <button
                  role="menuitem"
                  className={`w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 ${
                    canModify('library', 'update', file.created_by_id) ? 'text-white hover:bg-bambu-dark' : 'text-bambu-gray cursor-not-allowed'
                  }`}
                  onClick={() => { if (canModify('library', 'update', file.created_by_id)) { close(); onGenerateThumbnail(file); } }}
                  disabled={!canModify('library', 'update', file.created_by_id)}
                  title={!canModify('library', 'update', file.created_by_id) ? t('fileManager.noPermissionGenerateThumbnail') : undefined}
                >
                  <Image className="w-3.5 h-3.5" />
                  {t('fileManager.generateThumbnail')}
                </button>
              )}
              <button
                role="menuitem"
                className={`w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 ${
                  canModify('library', 'delete', file.created_by_id) ? 'text-red-700 dark:text-red-400 hover:bg-bambu-dark' : 'text-bambu-gray cursor-not-allowed'
                }`}
                onClick={() => { if (canModify('library', 'delete', file.created_by_id)) { close(); onDelete(file.id); } }}
                disabled={!canModify('library', 'delete', file.created_by_id)}
                title={!canModify('library', 'delete', file.created_by_id) ? t('fileManager.noPermissionDeleteFile') : undefined}
              >
                <Trash2 className="w-3.5 h-3.5" />
                {t('common.delete')}
              </button>
          </>}
        </ActionMenu>
      </div>

      {/* Selection indicator follows the same pointer/focus visibility. */}
      <div className={`absolute top-2 left-2 w-5 h-5 rounded border-2 flex items-center justify-center transition-all ${
        isSelected
          ? 'bg-bambu-green border-bambu-green'
          : 'border-white/30 bg-black/30 can-hover:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100'
      }`}>
        {isSelected && <div className="w-2 h-2 bg-white rounded-sm" />}
      </div>
    </div>
  );
}
