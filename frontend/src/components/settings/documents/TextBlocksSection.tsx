import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { DocumentConfigurationDraft, DocumentType, PlaceholderCatalogResponse, PolicyFinding } from '../../../api/documentManagement';
import { Select, TextArea } from '../../ui';

type TextBlock = DocumentConfigurationDraft['text_blocks'][number];

interface TextBlocksSectionProps {
  documentType: DocumentType;
  blocks: TextBlock[];
  catalog: PlaceholderCatalogResponse;
  findings: PolicyFinding[];
  disabled: boolean;
  onChange: (blocks: TextBlock[]) => void;
}

const PAYMENT_TYPES = new Set<DocumentType>(['quotation', 'order_confirmation', 'advance_invoice', 'progress_invoice', 'final_invoice', 'invoice', 'cancellation_invoice', 'invoice_correction', 'commercial_credit_note', 'payment_reminder', 'dunning_notice', 'self_billing']);
const TAX_TYPES = new Set<DocumentType>(['quotation', 'order_confirmation', 'advance_invoice', 'progress_invoice', 'final_invoice', 'invoice', 'cancellation_invoice', 'invoice_correction', 'commercial_credit_note', 'self_billing']);

function allowedPurpose(purpose: string, type: DocumentType): boolean {
  if (['intro', 'closing', 'footer'].includes(purpose)) return true;
  if (purpose === 'delivery_terms') return ['quotation', 'order_confirmation', 'delivery_note'].includes(type);
  if (purpose === 'payment_terms') return PAYMENT_TYPES.has(type) && type !== 'delivery_note';
  if (purpose === 'tax_note') return TAX_TYPES.has(type);
  if (purpose === 'dunning_notice') return ['payment_reminder', 'dunning_notice'].includes(type);
  return false;
}

function allowedPlaceholder(placeholder: string, type: DocumentType): boolean {
  if (placeholder.startsWith('dunning.') || ['OPEN_AMOUNT', 'DUNNING_LEVEL'].includes(placeholder)) return ['payment_reminder', 'dunning_notice'].includes(type);
  if (placeholder.startsWith('payment.') || placeholder === 'DUE_DATE') return PAYMENT_TYPES.has(type) && type !== 'delivery_note';
  if (placeholder.includes('tax') || placeholder.includes('vat')) return TAX_TYPES.has(type);
  if (placeholder === 'VALID_UNTIL') return type === 'quotation';
  if (placeholder === 'ORIGINAL_DOCUMENT_NUMBER') return ['cancellation_invoice', 'invoice_correction', 'commercial_credit_note'].includes(type);
  return true;
}

export function TextBlocksSection({ documentType, blocks, catalog, findings, disabled, onChange }: TextBlocksSectionProps) {
  const { t } = useTranslation();
  const refs = useRef<Record<string, HTMLTextAreaElement | null>>({});
  const purposes = useMemo(() => catalog.text_block_purposes.filter((purpose) => allowedPurpose(purpose, documentType)), [catalog.text_block_purposes, documentType]);
  const [activePurpose, setActivePurpose] = useState(purposes[0] ?? 'intro');
  const [placeholder, setPlaceholder] = useState('');
  const materialized = purposes.map((purpose, position) => blocks.find((block) => block.purpose === purpose) ?? { purpose, body: '', condition: null, position });
  const options = catalog.placeholders.filter((item) => allowedPlaceholder(item, documentType)).map((item) => ({ value: item, label: t(`settings.documents.placeholders.${item.replaceAll('.', '_')}`, item) }));

  const updateBody = (purpose: string, body: string) => onChange(materialized.map((block) => block.purpose === purpose ? { ...block, body } : block));
  const insertPlaceholder = (value: string) => {
    setPlaceholder(value);
    const block = materialized.find((item) => item.purpose === activePurpose) ?? materialized[0];
    if (!block) return;
    const textarea = refs.current[block.purpose];
    const cursor = textarea?.selectionStart ?? block.body.length;
    const token = value.includes('.') ? `{{${value}}}` : `{${value}}`;
    updateBody(block.purpose, `${block.body.slice(0, cursor)}${token}${block.body.slice(cursor)}`);
    queueMicrotask(() => textarea?.focus());
  };

  return (
    <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4" aria-labelledby="document-text-blocks-heading">
      <h3 id="document-text-blocks-heading" className="font-semibold text-white">{t('settings.documents.textBlocks.title', 'Text blocks')}</h3>
      <p className="mt-1 text-sm text-gray-400">{t('settings.documents.textBlocks.description', 'Reusable wording with document-specific placeholders.')}</p>
      <div className="mt-4 max-w-xl">
        <Select ariaLabel={t('settings.documents.textBlocks.insertPlaceholder', 'Insert placeholder')} value={placeholder} placeholder={t('settings.documents.textBlocks.choosePlaceholder', 'Choose placeholder')} options={options} disabled={disabled || options.length === 0} onValueChange={insertPlaceholder} />
      </div>
      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        {materialized.map((block, index) => {
          const finding = findings.find((item) => item.field_path === `text_blocks.${index}.body` || item.field_path === `text_blocks.${block.purpose}`);
          return (
            <TextArea
              key={block.purpose}
              ref={(node) => { refs.current[block.purpose] = node; }}
              label={t(`settings.documents.textBlocks.purposes.${block.purpose}`, block.purpose)}
              value={block.body}
              disabled={disabled}
              error={finding ? t(finding.message_key, finding.message_key) : undefined}
              onFocus={() => setActivePurpose(block.purpose)}
              onValueChange={(value) => updateBody(block.purpose, value)}
            />
          );
        })}
      </div>
    </section>
  );
}
