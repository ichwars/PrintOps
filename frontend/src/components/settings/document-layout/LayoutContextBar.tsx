import { useTranslation } from 'react-i18next';

import type { LayoutLanguage } from '../../../api/documentLayouts';
import { Select } from '../../ui';
import type { PdfPreviewSource } from './PdfPreviewPane';

export interface LayoutContextOption<T extends string | number> {
  value: T;
  label: string;
  disabled?: boolean;
}

export interface LayoutPreviewSourceOption {
  value: PdfPreviewSource;
  label: string;
  detail?: string;
  requiresCommercialDocumentRead?: boolean;
}

export interface LayoutContextBarProps {
  businessProfileId: number | null;
  businessProfiles: Array<LayoutContextOption<number>>;
  documentType: string | null;
  documentTypes: Array<LayoutContextOption<string>>;
  language: LayoutLanguage;
  languages?: Array<LayoutContextOption<LayoutLanguage>>;
  source: PdfPreviewSource | null;
  sources: LayoutPreviewSourceOption[];
  canReadCommercialDocuments: boolean;
  disabled?: boolean;
  onBusinessProfileChange: (profileId: number) => void;
  onDocumentTypeChange: (documentType: string) => void;
  onLanguageChange: (language: LayoutLanguage) => void;
  onSourceChange: (source: PdfPreviewSource) => void;
}

function sourceKey(source: PdfPreviewSource): string {
  return `${source.kind}:${source.id}`;
}

export function LayoutContextBar({
  businessProfileId,
  businessProfiles,
  documentType,
  documentTypes,
  language,
  languages = [{ value: 'de', label: 'Deutsch' }, { value: 'en', label: 'English' }],
  source,
  sources,
  canReadCommercialDocuments,
  disabled = false,
  onBusinessProfileChange,
  onDocumentTypeChange,
  onLanguageChange,
  onSourceChange,
}: LayoutContextBarProps) {
  const { t } = useTranslation();
  const visibleSources = sources.filter((option) => !option.requiresCommercialDocumentRead || canReadCommercialDocuments);
  const sourceOptions = visibleSources.map((option) => ({
    value: sourceKey(option.value),
    label: option.detail ? `${option.label} - ${option.detail}` : option.label,
  }));

  return <section aria-label={t('settings.documentLayout.context.title', 'Layout context')} className="grid gap-3 rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-3 sm:grid-cols-2 xl:grid-cols-4">
    <Select
      value={businessProfileId ?? ''}
      options={businessProfiles}
      label={t('settings.documentLayout.context.profile', 'Business profile')}
      ariaLabel={t('settings.documentLayout.context.profile', 'Business profile')}
      placeholder={t('settings.documentLayout.context.profile', 'Business profile')}
      disabled={disabled || businessProfiles.length === 0}
      onValueChange={(value) => onBusinessProfileChange(Number(value))}
    />
    <Select
      value={documentType ?? ''}
      options={documentTypes}
      label={t('settings.documentLayout.context.documentType', 'Document type')}
      ariaLabel={t('settings.documentLayout.context.documentType', 'Document type')}
      placeholder={t('settings.documentLayout.context.documentType', 'Document type')}
      disabled={disabled || documentTypes.length === 0}
      onValueChange={(value) => onDocumentTypeChange(String(value))}
    />
    <Select
      value={language}
      options={languages}
      label={t('settings.documentLayout.context.language', 'Language')}
      ariaLabel={t('settings.documentLayout.context.language', 'Language')}
      disabled={disabled}
      onValueChange={(value) => onLanguageChange(value as LayoutLanguage)}
    />
    <Select
      value={source ? sourceKey(source) : ''}
      options={sourceOptions}
      label={t('settings.documentLayout.context.sample', 'Preview source')}
      ariaLabel={t('settings.documentLayout.context.sample', 'Preview source')}
      placeholder={t('settings.documentLayout.context.sample', 'Preview source')}
      helperText={!canReadCommercialDocuments && sources.some((option) => option.requiresCommercialDocumentRead)
        ? t('settings.documentLayout.context.realDocumentHint', 'Only the document ID is sent; each preview is audited.')
        : undefined}
      disabled={disabled || visibleSources.length === 0}
      onValueChange={(value) => {
        const option = visibleSources.find((candidate) => sourceKey(candidate.value) === value);
        if (option) onSourceChange(option.value);
      }}
    />
  </section>;
}
