import { useState, useRef } from 'react';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Save, Loader2, RotateCcw, Plus, Eye } from 'lucide-react';
import { api } from '../api/client';
import type { NotificationTemplate, NotificationTemplateUpdate } from '../api/client';
import { Button } from './Button';
import { Modal, TextArea, TextField } from './ui';

interface NotificationTemplateEditorProps {
  template: NotificationTemplate;
  onClose: () => void;
}

export function NotificationTemplateEditor({ template, onClose }: NotificationTemplateEditorProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  const [titleTemplate, setTitleTemplate] = useState(template.title_template);
  const [bodyTemplate, setBodyTemplate] = useState(template.body_template);
  const [error, setError] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(true);

  // Fetch variables for this event type
  const { data: variablesData } = useQuery({
    queryKey: ['template-variables'],
    queryFn: api.getTemplateVariables,
  });

  // Get variables for this template's event type
  const eventVariables = variablesData?.find(v => v.event_type === template.event_type);

  // Live preview
  const { data: preview, isLoading: previewLoading } = useQuery({
    queryKey: ['template-preview', template.event_type, titleTemplate, bodyTemplate],
    queryFn: () => api.previewTemplate({
      event_type: template.event_type,
      title_template: titleTemplate,
      body_template: bodyTemplate,
    }),
    enabled: showPreview && titleTemplate.length > 0 && bodyTemplate.length > 0,
  });

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: NotificationTemplateUpdate) => api.updateNotificationTemplate(template.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notification-templates'] });
      onClose();
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  // Reset mutation
  const resetMutation = useMutation({
    mutationFn: () => api.resetNotificationTemplate(template.id),
    onSuccess: (resetTemplate) => {
      setTitleTemplate(resetTemplate.title_template);
      setBodyTemplate(resetTemplate.body_template);
      queryClient.invalidateQueries({ queryKey: ['notification-templates'] });
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!titleTemplate.trim()) {
      setError(t('notifications.titleRequired'));
      return;
    }
    if (!bodyTemplate.trim()) {
      setError(t('notifications.bodyRequired'));
      return;
    }

    updateMutation.mutate({
      title_template: titleTemplate,
      body_template: bodyTemplate,
    });
  };

  const insertVariable = (variable: string) => {
    const textarea = bodyRef.current;
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = bodyTemplate;
    const before = text.substring(0, start);
    const after = text.substring(end);
    const newValue = before + `{${variable}}` + after;

    setBodyTemplate(newValue);

    // Restore focus and cursor position
    setTimeout(() => {
      textarea.focus();
      const newCursor = start + variable.length + 2;
      textarea.setSelectionRange(newCursor, newCursor);
    }, 0);
  };

  const hasChanges = titleTemplate !== template.title_template || bodyTemplate !== template.body_template;

  return (
    <Modal
      open
      title={t('notifications.editTemplate', { name: template.name })}
      onClose={onClose}
      closeLabel={t('common.close')}
      closeOnBackdrop={false}
      footer={
        <>
          <Button
            type="button"
            variant="ghost"
            onClick={() => resetMutation.mutate()}
            disabled={resetMutation.isPending}
            className="mr-auto text-orange-800 dark:text-orange-300"
          >
            {resetMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
            {t('notifications.resetToDefault')}
          </Button>
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('notifications.cancel')}
          </Button>
          <Button className="text-black!" onClick={handleSubmit} disabled={updateMutation.isPending || !hasChanges}>
            {updateMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {t('notifications.save')}
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="min-w-0 space-y-4 text-sm text-table-secondary">
          {error && (
            <div className="p-3 bg-red-100 dark:bg-red-500/20 border border-red-300 dark:border-red-500/50 rounded text-red-700 dark:text-red-300 text-sm">
              {error}
            </div>
          )}

          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-table-secondary mb-1">
              {t('notifications.titleLabel')}
            </label>
            <TextField
              type="text"
              value={titleTemplate}
              onChange={(e) => setTitleTemplate(e.target.value)}
              className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white focus:outline-none focus:ring-1 focus:ring-bambu-green"
              placeholder={t('notifications.titlePlaceholder')}
            />
          </div>

          {/* Body */}
          <div>
            <label className="block text-sm font-medium text-table-secondary mb-1">
              {t('notifications.bodyLabel')}
            </label>
            <TextArea
              ref={bodyRef}
              value={bodyTemplate}
              onChange={(e) => setBodyTemplate(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded text-white focus:outline-none focus:ring-1 focus:ring-bambu-green font-mono text-sm resize-none"
              placeholder={t('notifications.bodyPlaceholder')}
            />
          </div>

          {/* Available Variables */}
          {eventVariables && (
            <div>
              <label className="block text-sm font-medium text-table-secondary mb-2">
                {t('notifications.availableVariables')}
              </label>
              <div className="flex flex-wrap gap-2">
                {eventVariables.variables.map((variable) => (
                  <Button variant="unstyled"
                    key={variable}
                    type="button"
                    onClick={() => insertVariable(variable)}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-bambu-dark hover:bg-bambu-dark-tertiary border border-bambu-dark-tertiary rounded text-xs text-table-secondary hover:text-white transition-colors"
                  >
                    <Plus className="w-3 h-3" />
                    {variable}
                  </Button>
                ))}
              </div>
              <p className="text-xs text-table-secondary mt-1">
                {t('notifications.clickToInsert')}
              </p>
            </div>
          )}

          {/* Preview */}
          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <label className="text-sm font-medium text-table-secondary flex items-center gap-2">
                <Eye className="w-4 h-4" />
                {t('notifications.livePreview')}
              </label>
              <Button variant="unstyled"
                type="button"
                onClick={() => setShowPreview(!showPreview)}
                className="text-xs text-accent-foreground hover:underline"
              >
                {showPreview ? t('notifications.hide') : t('notifications.show')}
              </Button>
            </div>
            {showPreview && (
              <div className="bg-bambu-dark border border-bambu-dark-tertiary rounded p-3 space-y-2">
                {previewLoading ? (
                  <div className="flex items-center gap-2 text-table-secondary text-sm">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {t('notifications.loadingPreview')}
                  </div>
                ) : preview ? (
                  <>
                    <div>
                      <span className="text-xs text-table-secondary">{t('notifications.titlePreview')}</span>
                      <div className="text-white font-medium">{preview.title}</div>
                    </div>
                    <div>
                      <span className="text-xs text-table-secondary">{t('notifications.bodyPreview')}</span>
                      <div className="text-white whitespace-pre-wrap text-sm">{preview.body}</div>
                    </div>
                  </>
                ) : (
                  <div className="text-table-secondary text-sm">
                    {t('notifications.enterTemplateContent')}
                  </div>
                )}
              </div>
            )}
          </div>
      </form>
    </Modal>
  );
}
