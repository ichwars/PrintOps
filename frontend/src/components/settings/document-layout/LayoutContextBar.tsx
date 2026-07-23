import { useTranslation } from 'react-i18next';

import type { LayoutLanguage } from '../../../api/documentLayouts';
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
  languages = [
    { value: 'de', label: 'Deutsch' },
    { value: 'en', label: 'English' },
  ],
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
  const visibleSources = sources.filter(
    (option) => !option.requiresCommercialDocumentRead || canReadCommercialDocuments,
  );

  const selectClassName =
    'min-h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-sm text-white focus:outline-none focus:ring-2 focus:ring-bambu-green disabled:cursor-not-allowed disabled:opacity-50';

  return (
    <section
      aria-label={t('settings.documentLayout.context.title', 'Layout context')}
      className="grid gap-3 rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-3 sm:grid-cols-2 xl:grid-cols-4"
    >
      <label className="min-w-0 text-xs text-bambu-gray">
        <span className="mb-1 block">
          {t('settings.documentLayout.context.profile', 'Business profile')}
        </span>
        <select
          className={selectClassName}
          value={businessProfileId ?? ''}
          disabled={disabled || businessProfiles.length === 0}
          onChange={(event) => onBusinessProfileChange(Number(event.target.value))}
        >
          <option value="" disabled>
            {t('settings.documentLayout.context.profile', 'Business profile')}
          </option>
          {businessProfiles.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="min-w-0 text-xs text-bambu-gray">
        <span className="mb-1 block">
          {t('settings.documentLayout.context.documentType', 'Document type')}
        </span>
        <select
          className={selectClassName}
          value={documentType ?? ''}
          disabled={disabled || documentTypes.length === 0}
          onChange={(event) => onDocumentTypeChange(event.target.value)}
        >
          <option value="" disabled>
            {t('settings.documentLayout.context.documentType', 'Document type')}
          </option>
          {documentTypes.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="min-w-0 text-xs text-bambu-gray">
        <span className="mb-1 block">
          {t('settings.documentLayout.context.language', 'Language')}
        </span>
        <select
          className={selectClassName}
          value={language}
          disabled={disabled}
          onChange={(event) => onLanguageChange(event.target.value as LayoutLanguage)}
        >
          {languages.map((option) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="min-w-0 text-xs text-bambu-gray">
        <span className="mb-1 block">
          {t('settings.documentLayout.context.sample', 'Preview source')}
        </span>
        <select
          className={selectClassName}
          value={source ? sourceKey(source) : ''}
          disabled={disabled || visibleSources.length === 0}
          onChange={(event) => {
            const option = visibleSources.find(
              (candidate) => sourceKey(candidate.value) === event.target.value,
            );
            if (option) onSourceChange(option.value);
          }}
        >
          <option value="" disabled>
            {t('settings.documentLayout.context.sample', 'Preview source')}
          </option>
          {visibleSources.map((option) => (
            <option
              key={sourceKey(option.value)}
              value={sourceKey(option.value)}
            >
              {option.label}{option.detail ? ` - ${option.detail}` : ''}
            </option>
          ))}
        </select>
        {!canReadCommercialDocuments && sources.some((option) => option.requiresCommercialDocumentRead) ? (
          <span className="mt-1 block text-[11px] text-bambu-gray">
            {t(
              'settings.documentLayout.context.realDocumentHint',
              'Only the document ID is sent; each preview is audited.',
            )}
          </span>
        ) : null}
      </label>
    </section>
  );
}
