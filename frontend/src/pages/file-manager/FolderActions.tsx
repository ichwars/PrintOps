import { Link2, Pencil, Trash2 } from 'lucide-react';
import type { LibraryFolderTree, Permission } from '../../api/client';
import { ActionMenu } from '../../components/ui/ActionMenu';

type Props = {
  folder: LibraryFolderTree;
  onRename: (folder: LibraryFolderTree) => void;
  onLink: (folder: LibraryFolderTree) => void;
  onDelete: (id: number) => void;
  hasPermission: (permission: Permission) => boolean;
  t: (key: string) => string;
};

/** Shared by the folder tree and the compact/mobile folder selector. */
export function FolderActions({ folder, onRename, onLink, onDelete, hasPermission, t }: Props) {
  const isLinked = folder.project_id || folder.archive_id;
  return (
    <ActionMenu label={`${t('common.actions')}: ${folder.name}`} className="p-1 rounded hover:bg-bambu-dark-tertiary">
      {(close) => <>
          <button
            role="menuitem"
            className={`w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 ${
              hasPermission('library:update_all') ? 'text-white hover:bg-bambu-dark' : 'text-bambu-gray cursor-not-allowed'
            }`}
            onClick={() => { if (hasPermission('library:update_all')) { close(); onRename(folder); } }}
            disabled={!hasPermission('library:update_all')}
            title={!hasPermission('library:update_all') ? t('fileManager.noPermissionRenameFolder') : undefined}
          >
            <Pencil className="w-3.5 h-3.5" />
            {t('common.rename')}
          </button>
          <button
            role="menuitem"
            className={`w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 ${
              hasPermission('library:update_all') ? 'text-white hover:bg-bambu-dark' : 'text-bambu-gray cursor-not-allowed'
            }`}
            onClick={() => { if (hasPermission('library:update_all')) { close(); onLink(folder); } }}
            disabled={!hasPermission('library:update_all')}
            title={!hasPermission('library:update_all') ? t('fileManager.noPermissionLinkFolder') : undefined}
          >
            <Link2 className="w-3.5 h-3.5" />
            {isLinked ? t('fileManager.changeLink') : t('fileManager.linkTo')}
          </button>
          <button
            role="menuitem"
            className={`w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 ${
              hasPermission('library:delete_all') ? 'text-red-700 dark:text-red-400 hover:bg-bambu-dark' : 'text-bambu-gray cursor-not-allowed'
            }`}
            onClick={() => { if (hasPermission('library:delete_all')) { close(); onDelete(folder.id); } }}
            disabled={!hasPermission('library:delete_all')}
            title={!hasPermission('library:delete_all') ? t('fileManager.noPermissionDeleteFolder') : undefined}
          >
            <Trash2 className="w-3.5 h-3.5" />
            {t('common.delete')}
          </button>
      </>}
    </ActionMenu>
  );
}
