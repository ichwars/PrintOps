import { useTranslation } from 'react-i18next';

import type {
  BasicPolicyDraft,
  ContentPolicyDraft,
  DocumentCatalogItem,
  PolicyFinding,
  SourcedValue,
} from '../../../api/documentManagement';
import { NumberField, Select, Switch, TextField } from '../../ui';
import { InheritanceField } from './InheritanceField';

interface BasicPolicySectionProps {
  basic: BasicPolicyDraft;
  content: ContentPolicyDraft;
  capability: DocumentCatalogItem;
  effectiveBasic?: Record<string, SourcedValue<unknown>>;
  effectiveContent?: Record<string, SourcedValue<unknown>>;
  findings: PolicyFinding[];
  disabled: boolean;
  onChange: (path: string, value: unknown) => void;
}

export function BasicPolicySection({
  basic,
  content,
  capability,
  effectiveBasic = {},
  effectiveContent = {},
  findings,
  disabled,
  onChange,
}: BasicPolicySectionProps) {
  const { t } = useTranslation();
  const reset = (path: string) => onChange(path, undefined);
  const finding = (path: string) => {
    const key = findings.find((item) => item.field_path === path)?.message_key;
    return key ? t(key, key) : undefined;
  };
  const referenceOptions = ['customer_reference', 'order_reference', 'service_period'];
  const visibleContentOptions = ['print_time', 'material', 'plate_notes'];

  return (
    <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4" aria-labelledby="document-basic-policy-heading">
      <h3 id="document-basic-policy-heading" className="font-semibold text-white">{t('settings.documents.basic.title', 'Document rules')}</h3>
      <p className="mt-1 text-sm text-gray-400">{t('settings.documents.basic.description', 'Dates, references, successors, rounding and technical content.')}</p>
      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <InheritanceField path="basic.subject" sourced={effectiveBasic.subject as SourcedValue<string> | undefined} onReset={reset}>
          <TextField label={t('settings.documents.basic.subject', 'Subject')} value={basic.subject} disabled={disabled} error={finding('basic.subject')} onValueChange={(value) => onChange('basic.subject', value)} />
        </InheritanceField>
        {capability.key === 'quotation' ? (
          <InheritanceField path="basic.validity_days" sourced={effectiveBasic.validity_days as SourcedValue<number | null> | undefined} onReset={reset}>
            <NumberField label={t('settings.documents.basic.validityDays', 'Validity in days')} value={basic.validity_days ?? ''} min={0} max={3650} disabled={disabled} error={finding('basic.validity_days')} onValueChange={(value) => onChange('basic.validity_days', value === '' ? null : Number(value))} />
          </InheritanceField>
        ) : null}
        <InheritanceField path="basic.date_rule" sourced={effectiveBasic.date_rule as SourcedValue<string> | undefined} onReset={reset}>
          <Select label={t('settings.documents.basic.dateRule', 'Relevant date')} value={basic.date_rule} disabled={disabled} options={[
            { value: 'issue_date', label: t('settings.documents.basic.dates.issue', 'Issue date') },
            { value: 'service_date', label: t('settings.documents.basic.dates.service', 'Service date') },
            { value: 'delivery_date', label: t('settings.documents.basic.dates.delivery', 'Delivery date') },
          ]} onValueChange={(value) => onChange('basic.date_rule', value)} />
        </InheritanceField>
        <InheritanceField path="basic.rounding_mode" sourced={effectiveBasic.rounding_mode as SourcedValue<string> | undefined} onReset={reset}>
          <Select label={t('settings.documents.basic.rounding', 'Rounding')} value={basic.rounding_mode} disabled={disabled} options={[
            { value: 'half_up', label: t('settings.documents.basic.roundingModes.commercial', 'Commercial') },
            { value: 'half_even', label: t('settings.documents.basic.roundingModes.bankers', 'Banker’s rounding') },
            { value: 'down', label: t('settings.documents.basic.roundingModes.down', 'Always down') },
          ]} onValueChange={(value) => onChange('basic.rounding_mode', value)} />
        </InheritanceField>
      </div>

      <div className="mt-5 border-t border-bambu-dark-tertiary pt-4">
        <h4 className="text-sm font-medium text-white">{t('settings.documents.basic.references', 'Required references')}</h4>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {referenceOptions.map((key) => (
            <Switch key={key} checked={Boolean(basic.reference_requirements[key])} disabled={disabled} label={t(`settings.documents.basic.reference.${key}`, key)} onCheckedChange={(checked) => onChange(`basic.reference_requirements.${key}`, checked)} />
          ))}
        </div>
      </div>

      {capability.allowed_successors.length ? (
        <div className="mt-5 border-t border-bambu-dark-tertiary pt-4">
          <h4 className="text-sm font-medium text-white">{t('settings.documents.basic.successors', 'Allowed follow-up documents')}</h4>
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {capability.allowed_successors.map((type) => (
              <Switch key={type} checked={basic.allowed_successors.includes(type)} disabled={disabled} label={t(`settings.documents.documentTypes.${type}`, type)} onCheckedChange={(checked) => onChange('basic.allowed_successors', checked ? [...basic.allowed_successors, type] : basic.allowed_successors.filter((item) => item !== type))} />
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-5 border-t border-bambu-dark-tertiary pt-4">
        <h4 className="text-sm font-medium text-white">{t('settings.documents.basic.technicalContent', 'Technical content')}</h4>
        <InheritanceField path="content.include_calculation_data" sourced={effectiveContent.include_calculation_data as SourcedValue<boolean> | undefined} onReset={reset}>
          <Switch checked={content.include_calculation_data} disabled={disabled} label={t('settings.documents.basic.includeCalculation', 'Include calculation and print data')} onCheckedChange={(checked) => onChange('content.include_calculation_data', checked)} />
        </InheritanceField>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {visibleContentOptions.map((key) => (
            <Switch key={key} checked={Boolean(content.visible_content[key])} disabled={disabled} label={t(`settings.documents.basic.content.${key}`, key)} onCheckedChange={(checked) => onChange(`content.visible_content.${key}`, checked)} />
          ))}
        </div>
      </div>
    </section>
  );
}
