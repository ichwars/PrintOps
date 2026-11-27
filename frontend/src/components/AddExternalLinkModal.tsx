import { useState, useId, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Save, Loader2, Upload, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import type { ExternalLink, ExternalLinkCreate, ExternalLinkUpdate } from '../api/client';
import { Button } from './Button';
import { IconPicker, getIconByName } from './IconPicker';
import { FileInput, IconButton, Modal, Switch, TextField } from './ui';
interface AddExternalLinkModalProps {
  link?: ExternalLink | null;
  onClose: () => void;
}

export function AddExternalLinkModal({ link, onClose }: AddExternalLinkModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const isEditing = !!link;
  const formId = useId();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [name, setName] = useState(link?.name || '');
  const [url, setUrl] = useState(link?.url || '');
  const [icon, setIcon] = useState(link?.icon || 'link');
  const [openInNewTab, setOpenInNewTab] = useState(link?.open_in_new_tab || false);
  const [useCustomIcon, setUseCustomIcon] = useState(!!link?.custom_icon);
  const [customIconPreview, setCustomIconPreview] = useState<string | null>(
    link?.custom_icon ? api.getExternalLinkIconUrl(link.id) : null
  );
  const [pendingIconFile, setPendingIconFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Create mutation
  const createMutation = useMutation({
    mutationFn: async (data: ExternalLinkCreate) => {
      const created = await api.createExternalLink(data);
      // If there's a pending icon file, upload it
      if (pendingIconFile) {
        return await api.uploadExternalLinkIcon(created.id, pendingIconFile);
      }
      return created;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['external-links'] });
      onClose();
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: async (data: ExternalLinkUpdate) => {
      let updated = await api.updateExternalLink(link!.id, data);
      // Handle icon changes
      if (pendingIconFile) {
        // Upload new icon
        updated = await api.uploadExternalLinkIcon(link!.id, pendingIconFile);
      } else if (!useCustomIcon && link?.custom_icon) {
        // Remove custom icon if switching to preset
        updated = await api.deleteExternalLinkIcon(link!.id);
      }
      return updated;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['external-links'] });
      onClose();
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      // Validate file type
      const validTypes = ['image/png', 'image/jpeg', 'image/gif', 'image/svg+xml', 'image/webp', 'image/x-icon'];
      if (!validTypes.includes(file.type)) {
        setError('Please select a valid image file (PNG, JPG, GIF, SVG, WebP, or ICO)');
        return;
      }

      // Validate file size (max 1MB)
      if (file.size > 1024 * 1024) {
        setError('Image file must be less than 1MB');
        return;
      }

      setPendingIconFile(file);
      setUseCustomIcon(true);

      // Create preview
      const reader = new FileReader();
      reader.onload = (e) => {
        setCustomIconPreview(e.target?.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleRemoveCustomIcon = () => {
    setPendingIconFile(null);
    setCustomIconPreview(null);
    setUseCustomIcon(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError('Name is required');
      return;
    }

    if (!url.trim()) {
      setError('URL is required');
      return;
    }

    // Validate URL
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      setError('URL must start with http:// or https://');
      return;
    }

    const data = {
      name: name.trim(),
      url: url.trim(),
      icon, // Keep preset icon as fallback
      open_in_new_tab: openInNewTab,
    };

    if (isEditing) {
      updateMutation.mutate(data);
    } else {
      createMutation.mutate(data);
    }
  };

  const isPending = createMutation.isPending || updateMutation.isPending;
  const PresetIcon = getIconByName(icon);

  return (
    <Modal
      open
      onClose={onClose}
      closeLabel={t('common.close')}
      className="max-w-md"
      title={(
        <span className="flex items-center gap-2">
          {useCustomIcon && customIconPreview ? (
            <img src={customIconPreview} alt="" className="h-5 w-5 shrink-0 rounded" />
          ) : (
            <PresetIcon className="h-5 w-5 shrink-0 text-bambu-green" aria-hidden="true" />
          )}
          {isEditing ? t('orders.runtimeInterface.editLink') : t('orders.runtimeInterface.addExternalLink')}
        </span>
      )}
      footer={(
        <>
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" form={formId} disabled={isPending} className="text-black!">
            {isPending ? (
              <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
            ) : isEditing ? (
              <Save className="h-4 w-4 shrink-0" />
            ) : (
              <Plus className="h-4 w-4 shrink-0" />
            )}
            {isEditing ? t('common.save') : t('common.add')}
          </Button>
        </>
      )}
    >
      <form id={formId} onSubmit={handleSubmit} className="space-y-4 text-sm text-table-secondary">
        {error && (
          <p role="alert" className="wrap-anywhere rounded-lg border border-red-300 bg-red-100 p-3 text-red-800 dark:border-red-500/50 dark:bg-red-500/20 dark:text-red-300">
            {error}
          </p>
        )}

        <TextField
          type="text"
          label={t('smartPlugs.nameLabel')}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('externalLinks.placeholders.linkName')}
          maxLength={50}
        />
        <TextField
          type="text"
          label={t('orders.runtimeInterface.uRL')}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com"
        />

        <div className="flex items-center justify-between gap-3 border-y border-bambu-dark-tertiary py-2">
          <p>{t('externalLinks.openInNewTab')}</p>
          <Switch
            ariaLabel={t('externalLinks.openInNewTab')}
            checked={openInNewTab}
            onCheckedChange={setOpenInNewTab}
          />
        </div>

        <div className="space-y-3">
          <h3 className="font-medium text-white">{t('maintenance.icon')}</h3>
          <div className="space-y-2 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium text-white">{t('orders.runtimeInterface.customIcon')}</span>
              <FileInput
                ref={fileInputRef}
                accept="image/png,image/jpeg,image/gif,image/svg+xml,image/webp,image/x-icon"
                className="hidden"
                onChange={handleFileSelect}
              />
              {useCustomIcon && customIconPreview ? (
                <div className="flex items-center gap-2">
                  <img src={customIconPreview} alt={t('orders.runtimeInterface.customIcon2')} className="h-8 w-8 rounded border border-bambu-dark-tertiary" />
                  <IconButton
                    size="sm"
                    icon={Trash2}
                    onClick={handleRemoveCustomIcon}
                    label={t('externalLinks.removeCustomIcon')}
                    title={t('externalLinks.removeCustomIcon')}
                    className="hover:bg-red-100! hover:text-red-900! dark:hover:bg-red-500/20! dark:hover:text-red-300!"
                  />
                </div>
              ) : (
                <Button type="button" variant="secondary" size="sm" onClick={() => fileInputRef.current?.click()}>
                  <Upload className="h-4 w-4 shrink-0" />
                  {t('common.upload')}
                </Button>
              )}
            </div>
            <p className="text-xs">{t('orders.runtimeInterface.pNGJPGGIFSVGWebPOrICOMax1MB')}</p>
          </div>

          {!useCustomIcon && (
            <div className="space-y-1">
              <p className="text-sm">{t('orders.runtimeInterface.orChooseAPresetIcon')}</p>
              <IconPicker value={icon} onChange={setIcon} />
            </div>
          )}
        </div>
      </form>
    </Modal>
  );
}
