import { FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { BusinessProfileOption } from '../../../api/client';
import type {
  DocumentCatalogItem,
  DocumentConfigurationDetail,
  DocumentType,
  ReadinessStatus,
} from '../../../api/documentManagement';
import { availableLanguages } from '../../../i18n';
import { Select } from '../../ui';
import type { DocumentContext } from './documentSettingsState';

interface DocumentContextHeaderProps {
  context: DocumentContext;
  profiles: BusinessProfileOption[];
  catalog: DocumentCatalogItem[];
  configuration: DocumentConfigurationDetail | null;
  readiness: ReadinessStatus | null;
  disabled?: boolean;
  onChange: (context: DocumentContext) => void;
}

const documentTypeFallbacks: Record<DocumentType, string> = {
  quotation: 'Quotation',
  order_confirmation: 'Order confirmation',
  delivery_note: 'Delivery note',
  advance_invoice: 'Advance invoice',
  progress_invoice: 'Progress invoice',
  final_invoice: 'Final invoice',
  invoice: 'Invoice',
  cancellation_invoice: 'Cancellation invoice',
  invoice_correction: 'Invoice correction',
  commercial_credit_note: 'Commercial credit note',
  payment_reminder: 'Payment reminder',
  dunning_notice: 'Dunning notice',
  self_billing: 'Self-billing invoice',
};

export function DocumentContextHeader({
  context,
  profiles,
  catalog,
  configuration,
  readiness,
  disabled = false,
  onChange,
}: DocumentContextHeaderProps) {
  const { t } = useTranslation();
  const status = configuration?.status ?? null;
  const statusClass = readiness === 'blocked'
    ? 'border-red-500/40 bg-red-500/10 text-red-200'
    : readiness === 'warnings'
      ? 'border-amber-500/40 bg-amber-500/10 text-amber-200'
      : 'border-bambu-green/40 bg-bambu-green/10 text-bambu-green-light';

  return (
    <header className="sticky top-0 z-10 rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary/95 p-4 shadow-lg backdrop-blur">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-bambu-green" aria-hidden="true" />
          <p className="text-lg font-semibold text-white">
            {t('settings.documents.title', 'Document settings')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
          {configuration ? (
            <span className="rounded-full border border-bambu-dark-tertiary bg-bambu-dark px-3 py-1.5 text-gray-200">
              {t(`settings.documents.status.${status}`, status ?? '')} · {t('settings.documents.version', { version: configuration.version, defaultValue: `Version ${configuration.version}` })}
            </span>
          ) : null}
          {readiness ? (
            <span className={`rounded-full border px-3 py-1.5 ${statusClass}`}>
              {t(`settings.documents.readiness.${readiness}`, readiness)}
            </span>
          ) : null}
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Select
          value={context.profileId}
          label={t('settings.documents.profile', 'Business profile')}
          options={profiles.filter((profile) => profile.is_active).map((profile) => ({ value: profile.id, label: profile.name }))}
          disabled={disabled || profiles.length === 0}
          onValueChange={(profileId) => {
            const profile = profiles.find((item) => item.id === profileId);
            onChange({ ...context, profileId, language: profile?.default_locale || context.language });
          }}
        />
        <Select
          value={context.documentType}
          label={t('settings.documents.documentType', 'Document type')}
          options={catalog.map((item) => ({
            value: item.key,
            label: t(`settings.documents.documentTypes.${item.key}`, documentTypeFallbacks[item.key]),
          }))}
          disabled={disabled || catalog.length === 0}
          onValueChange={(documentType) => onChange({ ...context, documentType })}
        />
        <Select
          value={context.language}
          label={t('settings.documents.language', 'Language')}
          options={availableLanguages.map((language) => ({ value: language.code, label: language.nativeName }))}
          disabled={disabled}
          onValueChange={(language) => onChange({ ...context, language })}
        />
      </div>
    </header>
  );
}
