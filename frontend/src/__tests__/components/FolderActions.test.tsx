import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { LibraryFolderTree, Permission } from '../../api/client';
import { FolderActions } from '../../pages/file-manager/FolderActions';

const folder = { id: 42, name: 'Models', children: [], project_id: 12 } as unknown as LibraryFolderTree;

describe('FolderActions permissions (tree and mobile selector)', () => {
  for (const granted of [[], ['library:update_all'], ['library:delete_all']]) {
    it(`retains permission checks for ${granted.join(',') || 'read only'}`, async () => {
      const onRename = vi.fn();
      const onLink = vi.fn();
      const onDelete = vi.fn();
      const user = userEvent.setup();
      render(<FolderActions folder={folder} t={key => key}
        hasPermission={(permission: Permission) => granted.includes(permission)}
        onRename={onRename} onLink={onLink} onDelete={onDelete} />);
      for (const [label, permission, callback, argument] of [
        ['common.rename', 'library:update_all', onRename, folder],
        ['fileManager.changeLink', 'library:update_all', onLink, folder],
        ['common.delete', 'library:delete_all', onDelete, 42],
      ] as const) {
        const trigger = screen.getByRole('button', { name: 'common.actions: Models' });
        if (!screen.queryByRole('menu')) await user.click(trigger);
        const item = screen.getByRole('menuitem', { name: label });
        if (granted.includes(permission)) {
          expect(item).toBeEnabled();
          await user.click(item);
          expect(callback).toHaveBeenCalledWith(argument);
          expect(trigger).toHaveFocus();
        } else {
          expect(item).toBeDisabled();
          await user.click(item);
          expect(callback).not.toHaveBeenCalled();
        }
      }
    });
  }
});
