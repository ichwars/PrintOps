import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Eye, EyeOff, Link2, Plus, Pencil, Trash2, GripVertical, Loader2, ExternalLink as ExternalLinkIcon, RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import type { ExternalLink } from '../api/client';
import { SettingsDashboardCard } from './settings/SettingsDashboardCard';
import { IconButton } from './ui';
import { Button } from './Button';
import { Toggle } from './Toggle';
import { AddExternalLinkModal } from './AddExternalLinkModal';
import { ConfirmModal } from './ConfirmModal';
import { getIconByName } from './IconPicker';
import { defaultNavItems } from './Layout';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import {
  getHiddenSidebarSystemItemIds,
  getSidebarOrder,
  saveHiddenSidebarSystemItemIds,
  saveSidebarOrder,
} from '../utils/sidebarLayout';

type SidebarLayoutItem =
  | { type: 'system'; id: string; navItem: typeof defaultNavItems[number] }
  | { type: 'external'; id: string; link: ExternalLink };

export function ExternalLinksSettings() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { authEnabled, hasPermission } = useAuth();
  const { showToast } = useToast();
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingLink, setEditingLink] = useState<ExternalLink | null>(null);
  const [deletingLink, setDeletingLink] = useState<ExternalLink | null>(null);
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [hiddenSystemItemIds, setHiddenSystemItemIds] = useState<string[]>(getHiddenSidebarSystemItemIds);
  const [sidebarOrder, setSidebarOrder] = useState<string[]>(() => getSidebarOrder(defaultNavItems.map(i => i.id)));
  const navItemsMap = useMemo(() => new Map(defaultNavItems.map(item => [item.id, item])), []);

  const { data: links, isLoading } = useQuery({
    queryKey: ['external-links'],
    queryFn: api.getExternalLinks,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteExternalLink(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['external-links'] });
    },
  });

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: api.getSettings,
    enabled: authEnabled && hasPermission('settings:update'),
  });

  const updateDefaultSidebarMutation = useMutation({
    mutationFn: (defaultSidebarOrder: string) => api.updateSettings({ default_sidebar_order: defaultSidebarOrder }),
    onSuccess: (_data, defaultSidebarOrder) => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['default-sidebar-order'] });
      showToast(
        defaultSidebarOrder
          ? t('settings.sidebarDefaultSet')
          : t('settings.sidebarDefaultCleared'),
        'success'
      );
    },
    onError: () => {
      showToast(t('settings.sidebarDefaultFailed'), 'error');
    },
  });

  const layoutItems = useMemo<SidebarLayoutItem[]>(() => {
    const externalLinksMap = new Map((links || []).map(link => [`ext-${link.id}`, link]));
    const defaultSidebarOrder = defaultNavItems.map(item => item.id);
    const result: SidebarLayoutItem[] = [];
    const seen = new Set<string>();

    const addItem = (id: string, insertAt?: number) => {
      if (seen.has(id)) return;

      const navItem = navItemsMap.get(id);
      if (navItem) {
        const item: SidebarLayoutItem = { type: 'system', id, navItem };
        if (insertAt === undefined) {
          result.push(item);
        } else {
          result.splice(insertAt, 0, item);
        }
        seen.add(id);
        return;
      }

      const link = externalLinksMap.get(id);
      if (link) {
        const item: SidebarLayoutItem = { type: 'external', id, link };
        if (insertAt === undefined) {
          result.push(item);
        } else {
          result.splice(insertAt, 0, item);
        }
        seen.add(id);
      }
    };

    sidebarOrder.forEach(addItem);

    for (const item of defaultNavItems) {
      if (seen.has(item.id)) continue;

      const defaultIndex = defaultSidebarOrder.indexOf(item.id);
      let insertAt = result.length;
      for (let i = defaultIndex + 1; i < defaultSidebarOrder.length; i += 1) {
        const nextIndex = result.findIndex(layoutItem => layoutItem.id === defaultSidebarOrder[i]);
        if (nextIndex !== -1) {
          insertAt = nextIndex;
          break;
        }
      }
      if (insertAt === result.length) {
        for (let i = defaultIndex - 1; i >= 0; i -= 1) {
          const previousIndex = result.findIndex(layoutItem => layoutItem.id === defaultSidebarOrder[i]);
          if (previousIndex !== -1) {
            insertAt = previousIndex + 1;
            break;
          }
        }
      }

      addItem(item.id, insertAt);
    }

    (links || []).forEach(link => addItem(`ext-${link.id}`));

    return result;
  }, [links, navItemsMap, sidebarOrder]);

  const getNavItemLabel = (navItem: typeof defaultNavItems[number]) => {
    const defaultValue = i18n.resolvedLanguage?.startsWith('de')
      ? navItem.defaultLabelDe ?? navItem.defaultLabel
      : navItem.defaultLabel;
    return t(navItem.labelKey, { defaultValue });
  };

  const persistSidebarOrder = (order: string[]) => {
    setSidebarOrder(order);
    saveSidebarOrder(order);
  };

  const handleDragStart = (e: React.DragEvent, id: string) => {
    setDraggedId(id);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', id);
  };

  const handleDragOver = (e: React.DragEvent, id: string) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverId(id);
  };

  const handleDrop = (e: React.DragEvent, targetId: string) => {
    e.preventDefault();
    if (draggedId === null || draggedId === targetId) {
      setDraggedId(null);
      setDragOverId(null);
      return;
    }

    const currentOrder = layoutItems.map(item => item.id);
    const draggedIndex = currentOrder.indexOf(draggedId);
    const targetIndex = currentOrder.indexOf(targetId);

    if (draggedIndex === -1 || targetIndex === -1) {
      setDraggedId(null);
      setDragOverId(null);
      return;
    }

    currentOrder.splice(draggedIndex, 1);
    currentOrder.splice(targetIndex, 0, draggedId);
    persistSidebarOrder(currentOrder);

    setDraggedId(null);
    setDragOverId(null);
  };

  const handleDragEnd = () => {
    setDraggedId(null);
    setDragOverId(null);
  };

  const handleDelete = (link: ExternalLink) => {
    setDeletingLink(link);
  };

  const confirmDelete = () => {
    if (deletingLink) {
      deleteMutation.mutate(deletingLink.id);
      setDeletingLink(null);
    }
  };

  const resetSidebarLayout = () => {
    const resetOrder = [
      ...defaultNavItems.map(item => item.id),
      ...(links || []).map(link => `ext-${link.id}`),
    ];

    setHiddenSystemItemIds([]);
    setSidebarOrder(resetOrder);
    saveHiddenSidebarSystemItemIds([]);
    saveSidebarOrder(resetOrder);
  };

  const handleToggleDefaultSidebarOrder = (enabled: boolean) => {
    const currentOrder = layoutItems.map(item => item.id);
    updateDefaultSidebarMutation.mutate(enabled ? JSON.stringify({
      order: currentOrder,
      hiddenSystemItemIds,
    }) : '');
  };

  const toggleSystemItemVisibility = (id: string) => {
    if (id === 'settings') return;

    const isHidden = hiddenSystemItemIds.includes(id);
    const nextIds = isHidden
      ? hiddenSystemItemIds.filter(hiddenId => hiddenId !== id)
      : [...hiddenSystemItemIds, id];

    setHiddenSystemItemIds(nextIds);
    saveHiddenSidebarSystemItemIds(nextIds);
  };

  const canSetDefaultSidebarOrder = authEnabled && hasPermission('settings:update');
  const isDefaultSidebarEnabled = !!settings?.default_sidebar_order;

  return (
    <>
      <SettingsDashboardCard id="card-sidebar-links" title={t('externalLinks.sidebarLayout')} icon={Link2}>
        <p>{t('externalLinks.sidebarLayoutDescription')}</p>
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          {canSetDefaultSidebarOrder && (
            <div className="flex items-center gap-2">
              <span>{t('settings.setDefault')}</span>
              <Toggle
                checked={isDefaultSidebarEnabled}
                onChange={handleToggleDefaultSidebarOrder}
                disabled={updateDefaultSidebarMutation.isPending}
                ariaLabel={t('settings.setDefault')}
              />
            </div>
          )}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <Button variant="secondary" size="sm" onClick={resetSidebarLayout}>
              <RotateCcw className="h-4 w-4 shrink-0" />
              {t('settings.reset')}
            </Button>
            <Button size="sm" onClick={() => setShowAddModal(true)} className="text-black!">
              <Plus className="h-4 w-4 shrink-0" />
              {t('externalLinks.addLink')}
            </Button>
          </div>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 text-bambu-green animate-spin" />
          </div>
        ) : (
          <div className="space-y-2">
            {layoutItems.map((item) => {
              const isDirectlyHidden = item.type === 'system' && hiddenSystemItemIds.includes(item.id);
              const isSettings = item.id === 'settings';

              if (item.type === 'system') {
                const Icon = item.navItem.icon;
                const parentItem = item.navItem.parentId ? navItemsMap.get(item.navItem.parentId) : undefined;
                const parentLabel = parentItem ? getNavItemLabel(parentItem) : '';
                const isChildItem = Boolean(parentItem);
                const isHiddenByParent = Boolean(parentItem && hiddenSystemItemIds.includes(parentItem.id));
                const isEffectivelyHidden = isDirectlyHidden || isHiddenByParent;
                const canToggleVisibility = !isSettings && !isHiddenByParent;
                const statusLabel = isSettings
                  ? t('externalLinks.requiredInSidebar')
                  : isHiddenByParent
                    ? t('externalLinks.hiddenByParent', { parent: parentLabel })
                    : isDirectlyHidden
                      ? t('externalLinks.hiddenFromSidebar')
                      : t('externalLinks.visibleInSidebar');
                const contextLabel = isChildItem
                  ? t('externalLinks.childPageOf', { parent: parentLabel })
                  : t('externalLinks.mainPage');
                const visibilityTitle = isSettings
                  ? t('externalLinks.settingsCannotBeHidden')
                  : isHiddenByParent
                    ? t('externalLinks.showParentFirst', { parent: parentLabel })
                    : isDirectlyHidden
                      ? t('externalLinks.showPage')
                      : t('externalLinks.hidePage');

                return (
                  <div
                    key={item.id}
                    draggable
                    onDragStart={(e) => handleDragStart(e, item.id)}
                    onDragOver={(e) => handleDragOver(e, item.id)}
                    onDragLeave={() => setDragOverId(null)}
                    onDrop={(e) => handleDrop(e, item.id)}
                    onDragEnd={handleDragEnd}
                    className={`relative flex items-center gap-2 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-2 transition-colors hover:bg-bambu-dark-tertiary/30 sm:gap-3 sm:px-3 ${
                      isChildItem ? 'ml-3 border-l-bambu-green/40 sm:ml-5' : ''
                    } ${
                      draggedId === item.id ? 'opacity-50' : ''
                    } ${
                      dragOverId === item.id && draggedId !== item.id
                        ? 'before:absolute before:left-3 before:right-3 before:top-0 before:h-0.5 before:bg-bambu-green'
                        : ''
                    }`}
                  >
                    <GripVertical className="h-4 w-4 shrink-0 cursor-grab text-table-secondary" />
                    <div className="hidden shrink-0 rounded-lg bg-bambu-dark-tertiary p-2 text-table-secondary min-[400px]:block">
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className="block wrap-anywhere font-medium text-white">{getNavItemLabel(item.navItem)}</span>
                      <span className="block text-xs text-table-secondary">
                        {contextLabel} · {statusLabel}
                      </span>
                    </div>
                    <IconButton
                      size="sm"
                      icon={isEffectivelyHidden ? EyeOff : Eye}
                      label={visibilityTitle}
                      title={visibilityTitle}
                      onClick={() => toggleSystemItemVisibility(item.id)}
                      disabled={!canToggleVisibility}
                      className="disabled:hover:bg-transparent"
                    />
                  </div>
                );
              }

              const link = item.link;
              const Icon = getIconByName(link.icon);
              return (
                <div
                  key={item.id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, item.id)}
                  onDragOver={(e) => handleDragOver(e, item.id)}
                  onDragLeave={() => setDragOverId(null)}
                  onDrop={(e) => handleDrop(e, item.id)}
                  onDragEnd={handleDragEnd}
                  className={`relative flex items-center gap-2 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-2 transition-colors hover:bg-bambu-dark-tertiary/30 sm:gap-3 sm:px-3 ${
                    draggedId === item.id ? 'opacity-50' : ''
                  } ${
                    dragOverId === item.id && draggedId !== item.id
                      ? 'before:absolute before:left-3 before:right-3 before:top-0 before:h-0.5 before:bg-bambu-green'
                      : ''
                  }`}
                >
                  <GripVertical className="h-4 w-4 shrink-0 cursor-grab text-table-secondary" />
                  <div className="hidden shrink-0 rounded-lg bg-bambu-dark-tertiary p-2 text-table-secondary min-[400px]:block">
                    {link.custom_icon ? (
                      <img
                        src={api.getExternalLinkIconUrl(link.id)}
                        alt=""
                        className="w-4 h-4"
                      />
                    ) : (
                      <Icon className="w-4 h-4" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="min-w-0 wrap-anywhere font-medium text-white">{link.name}</span>
                      <ExternalLinkIcon className="h-3 w-3 shrink-0 text-table-secondary" />
                    </div>
                    <span className="block truncate text-xs text-table-secondary" title={link.url}>{link.url}</span>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <IconButton
                      size="sm"
                      icon={Pencil}
                      label={t('common.edit')}
                      title={t('common.edit')}
                      onClick={() => setEditingLink(link)}
                    />
                    <IconButton
                      size="sm"
                      icon={Trash2}
                      label={t('externalLinks.deleteLink')}
                      title={t('externalLinks.deleteLink')}
                      onClick={() => handleDelete(link)}
                      disabled={deleteMutation.isPending}
                      className="hover:bg-red-100! hover:text-red-900! dark:hover:bg-red-500/20! dark:hover:text-red-300!"
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </SettingsDashboardCard>

      {(showAddModal || editingLink) && (
        <AddExternalLinkModal
          link={editingLink}
          onClose={() => {
            setShowAddModal(false);
            setEditingLink(null);
          }}
        />
      )}

      {deletingLink && (
        <ConfirmModal
          title={t('externalLinks.deleteLink')}
          message={t('externalLinks.deleteConfirm', { name: deletingLink.name })}
          confirmText={t('common.delete')}
          cancelText={t('common.cancel')}
          variant="danger"
          onConfirm={confirmDelete}
          onCancel={() => setDeletingLink(null)}
        />
      )}
    </>
  );
}
