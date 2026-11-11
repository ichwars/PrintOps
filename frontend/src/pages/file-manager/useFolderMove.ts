import { useMemo, useState, type DragEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api, type LibraryFolderTree } from '../../api/client';
import { useToast } from '../../contexts/ToastContext';

const FOLDER_DRAG_TYPE = 'application/x-printops-library-folder';

function moveDestinations(folders: LibraryFolderTree[], source: LibraryFolderTree) {
  const destinations: { id: number; path: string }[] = [];
  function addBranches(branches: LibraryFolderTree[], prefix: string) {
    for (const folder of branches) {
      if (folder.id === source.id || folder.is_external) continue;
      const path = prefix ? `${prefix} / ${folder.name}` : folder.name;
      if (folder.id !== source.parent_id) destinations.push({ id: folder.id, path });
      addBranches(folder.children, path);
    }
  }
  addBranches(folders, '');
  return destinations;
}

export function useFolderMove(folders: LibraryFolderTree[] | undefined, canMove: boolean) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const [picker, setPicker] = useState<LibraryFolderTree | null>(null);
  const [dragged, setDragged] = useState<LibraryFolderTree | null>(null);
  const [hovered, setHovered] = useState<number>();
  const from = picker ?? dragged;
  const destinations = useMemo(() => folders && from ? moveDestinations(folders, from) : [], [folders, from]);
  const mutation = useMutation({
    mutationFn: ({ id, parent }: { id: number; parent: number }) => api.updateLibraryFolder(id, { parent_id: parent }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['library-folders'] });
      void queryClient.invalidateQueries({ queryKey: ['library-files'] });
      setPicker(null);
      showToast(t('fileManager.folderMove.done'), 'success');
    },
    onError: error => showToast(error.message, 'error'),
  });
  function canDrop(parent: number) {
    if (!canMove || mutation.isPending || !from || from.is_external) return false;
    return parent === 0 ? from.parent_id != null : destinations.some(folder => folder.id === parent);
  }
  function move(parent: number) {
    if (from && canDrop(parent)) mutation.mutate({ id: from.id, parent });
  }
  function clearDrag() {
    setDragged(null);
    setHovered(undefined);
  }
  function rowProps(folder: LibraryFolderTree) {
    if (!canMove || folder.is_external || mutation.isPending) return {};
    return {
      draggable: true,
      onDragStart: (event: DragEvent) => {
        event.stopPropagation();
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData(FOLDER_DRAG_TYPE, String(folder.id));
        setDragged(folder);
      },
      onDragEnd: clearDrag,
    };
  }
  function dropProps(parent: number) {
    function dragOver(event: DragEvent) {
      if (!dragged || !event.dataTransfer.types.includes(FOLDER_DRAG_TYPE)) return;
      event.stopPropagation();
      if (!canDrop(parent)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      setHovered(parent);
    }
    return {
      onDragOver: dragOver,
      onDragLeave: (event: DragEvent) => {
        if (event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget)) return;
        setHovered(previous => previous === parent ? undefined : previous);
      },
      onDrop: (event: DragEvent) => {
        if (!dragged || !event.dataTransfer.types.includes(FOLDER_DRAG_TYPE)) return;
        event.stopPropagation();
        if (canDrop(parent) && event.dataTransfer.getData(FOLDER_DRAG_TYPE) === String(dragged.id)) {
          event.preventDefault();
          move(parent);
        }
        clearDrag();
      },
    };
  }
  return {
    picker, setPicker, destinations, hovered, move, rowProps, dropProps, isPending: mutation.isPending,
  };
}
